#!/usr/bin/env python3
"""Block a release until a maintainer approves it in a Slack thread.

Posts a message to a Slack channel announcing a release that is awaiting
approval, then polls the message thread until an authorized approver replies
`approve` (exit 0) or `reject` (exit 1). On approval, rejection, or timeout it
edits the original message to a green check / red cross and posts a short
thread reply so the channel sees the outcome.

This is a stopgap for GitHub Environment required-reviewers, which is not
available on the org's current private-repo plan (see SCU-1423). It needs only
a write-and-read bot token + the channel-history scope — no Socket Mode, no
app-level token, no signing secret, and no public endpoint.

Secrets / context (environment, never argv — argv is visible in process lists):
  SLACK_RELEASE_BOT_TOKEN
                     Bot token (xoxb-) with chat:write + a *history scope for
                     the target channel (channels:history / groups:history).
                     The bot must be a member of the channel.
  SLACK_CHANNEL_ID   Channel to post the approval request in.
  SLACK_APPROVERS    Comma-separated workspace-local Slack member IDs (U…, the
                     profile "Copy member ID" value), matched against each
                     reply's `user`. IDs, not handles. Use --debug to discover
                     the exact IDs a reply carries.
  GITHUB_*           REF_NAME / SERVER_URL / REPOSITORY / RUN_ID / ACTOR, used
                     only to render the message. Derived, not required.

Tunables: see --help. The job's `timeout-minutes` must exceed --timeout-minutes
so this script can post the red cross and exit cleanly before the runner is
killed.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import AbstractSet
from collections.abc import Mapping
from collections.abc import Sequence

SLACK_API = "https://slack.com/api/"

APPROVE_WORDS = {"approve", "approved", "approves", "lgtm", "ship", "shipit"}
REJECT_WORDS = {"reject", "rejected", "rejects", "no", "abort", "cancel"}


class ApprovalAborted(Exception):
    """Raised on SIGTERM/SIGINT so the finally-block can mark the message."""


def slack_call(method: str, token: str, params: Mapping[str, str], retries: int = 4) -> dict:
    """POST to a Slack Web API method (form-encoded) and return the JSON body.

    Retries on 429 (honoring Retry-After) and transient network errors. Raises
    on a Slack-level `ok: false` so config errors surface loudly at startup.
    """
    data = urllib.parse.urlencode(params).encode()
    request = urllib.request.Request(
        SLACK_API + method,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        },
    )
    last_error = ""
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            if error.code == 429:
                time.sleep(int(error.headers.get("Retry-After", "5")))
                continue
            last_error = f"HTTP {error.code}"
        except urllib.error.URLError as error:
            last_error = str(error.reason)
        else:
            if not body.get("ok"):
                detail = body.get("error", "unknown")
                # missing_scope responses carry the exact scope mismatch.
                if body.get("needed"):
                    detail += f" (needed={body['needed']!r}, provided={body.get('provided')!r})"
                raise RuntimeError(f"Slack API {method} failed: {detail}")
            return body
        time.sleep(2**attempt)
    raise RuntimeError(f"Slack API {method} unreachable after {retries} tries ({last_error})")


def normalize_first_word(text: str) -> str:
    """Lowercased first alphanumeric token of a reply, e.g. 'Approve!' -> 'approve'."""
    stripped = text.strip().lower()
    token = stripped.split(maxsplit=1)[0] if stripped else ""
    return "".join(ch for ch in token if ch.isalnum())


def scan_for_decision(
    messages: Sequence[Mapping[str, str]], parent_ts: str, approvers: AbstractSet[str], minimum: int
) -> tuple[str, str] | None:
    """Return (decision, user_id) for the thread, or None if undecided.

    Reject by any approver wins immediately (fail-closed). Otherwise, once
    `minimum` distinct approvers have said an approve-word, it's approved.
    """
    approving: set[str] = set()
    for message in messages:
        if message.get("ts") == parent_ts:  # the parent message itself, not a reply
            continue
        user = message.get("user", "")
        if user not in approvers:
            continue
        word = normalize_first_word(message.get("text", ""))
        if word in REJECT_WORDS:
            return ("rejected", user)
        if word in APPROVE_WORDS:
            approving.add(user)
    if len(approving) >= minimum:
        return ("approved", sorted(approving)[0])
    return None


def finalize(token: str, channel_id: str, parent_ts: str, parent_text: str, reply_text: str) -> None:
    """Edit the original message to its outcome and post a thread reply as a ping."""
    slack_call("chat.update", token, {"channel": channel_id, "ts": parent_ts, "text": parent_text})
    slack_call(
        "chat.postMessage",
        token,
        {"channel": channel_id, "thread_ts": parent_ts, "text": reply_text},
    )


def _raise_aborted(_signum: int, _frame: object) -> None:
    """SIGTERM/SIGINT handler: surface as ApprovalAborted so main() can mark the message."""
    raise ApprovalAborted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout-minutes", type=float, default=60.0)
    parser.add_argument("--poll-seconds", type=float, default=15.0)
    parser.add_argument("--min-approvals", type=int, default=1)
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Log each thread reply's author id + first word — use this to discover the U… member IDs to put in SLACK_APPROVERS.",
    )
    args = parser.parse_args()

    token = os.environ["SLACK_RELEASE_BOT_TOKEN"]
    channel = os.environ["SLACK_CHANNEL_ID"]
    approvers = {uid.strip() for uid in os.environ["SLACK_APPROVERS"].split(",") if uid.strip()}
    if not approvers:
        print("SLACK_APPROVERS is empty; refusing to run an ungated approval.", file=sys.stderr)
        return 2
    if args.min_approvals > len(approvers):
        print(
            f"min-approvals ({args.min_approvals}) exceeds approver count ({len(approvers)}).",
            file=sys.stderr,
        )
        return 2

    # Message context, derived from the GitHub Actions environment.
    ref_name = os.environ.get("GITHUB_REF_NAME", "")
    version = ref_name.removeprefix("sculptor-v") or "release"
    actor = os.environ.get("GITHUB_ACTOR", "someone")
    run_url = "{server}/{repo}/actions/runs/{run}".format(
        server=os.environ.get("GITHUB_SERVER_URL", "https://github.com"),
        repo=os.environ.get("GITHUB_REPOSITORY", ""),
        run=os.environ.get("GITHUB_RUN_ID", ""),
    )
    mentions = " ".join(f"<@{uid}>" for uid in sorted(approvers))
    timeout_minutes = args.timeout_minutes

    ask = "\n".join(
        [
            f":hourglass_flowing_sand: *Release approval needed — Sculptor {version}*",
            f"<{run_url}|Pipeline run> triggered by `{actor}`.",
            f"Reply *approve* or *reject* in this thread. Authorized: {mentions}",
            f"_Auto-rejects in {timeout_minutes:g} min if no one responds._",
        ]
    )
    posted = slack_call("chat.postMessage", token, {"channel": channel, "text": ask})
    parent_ts = posted["ts"]
    channel_id = posted.get("channel", channel)  # resolve a channel name to its id

    signal.signal(signal.SIGTERM, _raise_aborted)
    signal.signal(signal.SIGINT, _raise_aborted)

    deadline = time.monotonic() + timeout_minutes * 60
    try:
        while True:
            try:
                thread = slack_call(
                    "conversations.replies",
                    token,
                    {"channel": channel_id, "ts": parent_ts, "limit": "200"},
                )
                messages = thread.get("messages", [])
                if args.debug:
                    for msg in messages:
                        if msg.get("ts") != parent_ts:
                            print(
                                f"[debug] reply author={msg.get('user')!r} text={msg.get('text', '')!r}",
                                file=sys.stderr,
                            )
                decision = scan_for_decision(messages, parent_ts, approvers, args.min_approvals)
            except RuntimeError as error:
                # A transient read failure shouldn't abort the release; try again
                # next tick. (A bad token would have failed the initial post.)
                print(f"poll error (will retry): {error}", file=sys.stderr)
                decision = None

            if decision is not None:
                verdict, user = decision
                if verdict == "approved":
                    finalize(
                        token,
                        channel_id,
                        parent_ts,
                        f":white_check_mark: *Sculptor {version} approved* by <@{user}>. Publishing…",
                        f":white_check_mark: Approved by <@{user}> — release proceeding.",
                    )
                    print(f"Approved by {user}.")
                    return 0
                finalize(
                    token,
                    channel_id,
                    parent_ts,
                    f":x: *Sculptor {version} rejected* by <@{user}>. Release aborted.",
                    f":x: Rejected by <@{user}> — release aborted.",
                )
                print(f"Rejected by {user}.", file=sys.stderr)
                return 1

            if time.monotonic() >= deadline:
                finalize(
                    token,
                    channel_id,
                    parent_ts,
                    f":x: *Sculptor {version} approval timed out* after {timeout_minutes:g} min. Release aborted.",
                    ":x: No approval within the window — release aborted.",
                )
                print("Timed out waiting for approval.", file=sys.stderr)
                return 1

            time.sleep(args.poll_seconds)
    except ApprovalAborted:
        finalize(
            token,
            channel_id,
            parent_ts,
            f":x: *Sculptor {version} approval cancelled* (job interrupted). Release aborted.",
            ":x: Job interrupted — release aborted.",
        )
        print("Interrupted before approval.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
