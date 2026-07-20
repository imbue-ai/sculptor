"""Declarative description of the demo state we seed into the QA harness.

Editing this file is how we iterate on the demo: change a workspace's title,
branch, scripted turn, or PR fixture here, re-run `seed_all.py`, and re-shoot.
Each spec is realized idempotently (repos are re-cloned fresh and workspaces
recreated), so the seed is fully repeatable.

Repos are referenced by name; `repos.py` clones each available one under the
demo directory (the sculptor repo always resolves to this checkout, the others
are opt-in via SCULPTOR_DEMO_REPO_<NAME>). PR pills come from PR_FIXTURES,
served through the real PR-polling pipeline by the gh shim.
"""

from __future__ import annotations

import shlex

from fakeclaude import bash, directive, multi_step_prompt, task_create, task_update, text, write_file
from seed_hero import build_prompt as hero_prompt

REPO_NAMES = ["sculptor", "openhost", "mngr"]

# Canned PR status served by marketing/gh_shim/gh, keyed by head branch. An
# OPEN entry renders the open-PR pill (with checks/reviews); a MERGED entry
# renders the merged pill via the poller's per-workspace fallback lookup.
PR_FIXTURES: dict = {
    "branches": {
        "feat/semantic-command-palette": {
            "repo": "sculptor",
            "number": 1342,
            "title": "Add semantic search to the command palette",
            "state": "OPEN",
            "checks": "SUCCESS",
            "approvals": [{"login": "imbue-review", "approved": True}],
        },
        "feat/stream-terminal-output": {
            "repo": "sculptor",
            "number": 1338,
            "title": "Stream terminal output incrementally",
            "state": "MERGED",
        },
    },
}

# Workspaces to mark read after seeding, so the sidebar shows a believable mix of
# read and unread (green-dot) rows instead of every workspace looking unread.
READ_BRANCHES = {
    "feat/stream-terminal-output",
    "feat/opt-in-telemetry",
    "ops/tls-auto-renewal",
    "feat/first-deploy-wizard",
    "feat/dashboard-metrics",
}

# A follow-up turn sent after the content turn settles, to flip a workspace into
# a transient agent state (in-progress / waiting-on-question / error) so the
# sidebar shows the full range of states, not just done+read/unread. These
# directives block or error, so they can't be baked into the content multi_step.
STATE_TURNS = {
    # In progress: keeps thinking on top of its completed work.
    "feat/file-tree-keyboard-nav": directive("hang", seconds=3600),
    # Waiting on a question: posts a decision and blocks for the answer. The
    # long timeout holds the amber waiting state across captures instead of
    # flipping to an error when the default wait expires.
    "fix/flaky-reconnect-test": directive(
        "ask_user_question",
        timeout_seconds=86400,
        questions=[
            {
                "question": "The reconnect test can assert on socket OPEN or on the first heartbeat. Which is safer?",
                "header": "Reconnect assertion",
                "options": [
                    {"label": "Socket OPEN", "description": "Assert as soon as readyState is OPEN"},
                    {"label": "First heartbeat", "description": "Wait for the first server ping"},
                ],
                "multiSelect": False,
            }
        ],
    ),
    # Error: surfaces a transient API failure block.
    "perf/nginx-proxy-cache": directive("api_error"),
}


def commit(message: str) -> dict:
    # The demo clones carry a neutral committer identity (repos.py), so a plain
    # commit never puts the user's real name in a screenshot. shlex.quote keeps
    # quotes/$/backticks in a message from breaking the scripted shell line.
    return bash(f"git add -A && git commit -q -m {shlex.quote(message)}", f"Commit: {message}")


def light_turn(intro: str, files: list[tuple[str, str]], summary: str, commit_msg: str | None = None) -> str:
    """A short, believable agent turn: intro text, a few file writes, optional
    commit, and a closing summary. Enough to make a workspace look worked-in."""
    steps: list[dict] = [text(intro)]
    for path, content in files:
        steps.append(write_file(path, content))
    if commit_msg:
        steps.append(commit(commit_msg))
    steps.append(text(summary))
    return multi_step_prompt(steps)


# --- sculptor: 5 workspaces (the two heroes are richest) --------------------

MERGED_TERMINAL_STREAM = '''\
export interface TerminalChunk {
  stream: "stdout" | "stderr";
  data: string;
  at: number;
}

/**
 * Incrementally flushes terminal output to subscribers as it arrives, instead of
 * buffering the whole command. Keeps the UI responsive for long-running builds.
 */
export function streamChunks(
  onChunk: (chunk: TerminalChunk) => void,
): (stream: TerminalChunk["stream"], data: string) => void {
  return (stream, data) => {
    for (const line of data.split(/(?<=\\n)/)) {
      if (line.length > 0) {
        onChunk({ stream, data: line, at: Date.now() });
      }
    }
  };
}
'''


def sculptor_specs() -> list[dict]:
    return [
        {
            "repo": "sculptor",
            "branch": "feat/semantic-command-palette",
            "name": "Semantic command palette",
            "prompt": hero_prompt(),
        },
        {
            "repo": "sculptor",
            "branch": "feat/stream-terminal-output",
            "name": "Stream terminal output incrementally",
            "prompt": multi_step_prompt(
                [
                    text(
                        "Terminal output currently buffers until the command exits. I'll stream it "
                        "chunk-by-chunk so long builds render live."
                    ),
                    task_create("1", "Add incremental chunk streamer", "in_progress", "Adding chunk streamer"),
                    write_file("sculptor/frontend/src/components/terminal/streamChunks.ts", MERGED_TERMINAL_STREAM),
                    commit("Stream terminal output incrementally"),
                    task_update("1", "completed"),
                    text(
                        "Done — terminal output now flushes per line as it arrives. Verified against a "
                        "30s build; first output appears in under 50ms instead of at exit."
                    ),
                ]
            ),
        },
        {
            "repo": "sculptor",
            "branch": "feat/file-tree-keyboard-nav",
            "name": "Keyboard navigation for the file tree",
            "prompt": light_turn(
                "Adding arrow-key navigation and type-ahead to the file tree so it's fully keyboard-driven.",
                [
                    (
                        "sculptor/frontend/src/components/fileTree/useTreeKeyboard.ts",
                        'import { useCallback } from "react";\n\n'
                        "/** Arrow-key + type-ahead navigation for the file tree. */\n"
                        "export function useTreeKeyboard(onMove: (delta: number) => void) {\n"
                        "  return useCallback(\n"
                        '    (e: KeyboardEvent) => {\n'
                        '      if (e.key === "ArrowDown") onMove(1);\n'
                        '      if (e.key === "ArrowUp") onMove(-1);\n'
                        "    },\n"
                        "    [onMove],\n"
                        "  );\n"
                        "}\n",
                    )
                ],
                "Arrow keys and type-ahead now move focus through the tree. Working through edge cases "
                "for collapsed folders next.",
            ),
        },
        {
            "repo": "sculptor",
            "branch": "feat/opt-in-telemetry",
            "name": "Opt-in usage metrics",
            "prompt": light_turn(
                "Wiring an opt-in usage-metrics client so we can see which panels people actually use.",
                [
                    (
                        "sculptor/frontend/src/common/telemetry/track.ts",
                        "type Event = { name: string; props?: Record<string, string> };\n\n"
                        "/** No-ops unless the user has opted in; batches events on a short timer. */\n"
                        "export function track(event: Event, enabled: boolean): void {\n"
                        "  if (!enabled) return;\n"
                        "  queue.push({ ...event, at: Date.now() });\n"
                        "}\n\n"
                        "const queue: Array<Event & { at: number }> = [];\n",
                    )
                ],
                "Metrics client is in behind the opt-in flag. Adding the settings toggle and a flush-on-idle "
                "scheduler next.",
            ),
        },
        {
            "repo": "sculptor",
            "branch": "fix/flaky-reconnect-test",
            "name": "Fix flaky websocket reconnect test",
            "prompt": multi_step_prompt(
                [
                    text(
                        "The reconnect test flakes because it asserts on a fixed timeout. I'll make it wait on "
                        "the socket state instead."
                    ),
                    task_create("1", "Reproduce the flake", "completed", "Reproducing the flake"),
                    task_create("2", "Replace timeout with state wait", "in_progress", "Replacing the timeout"),
                    write_file(
                        "sculptor/frontend/src/common/state/hooks/waitForSocketOpen.ts",
                        'import type { ReconnectingSocket } from "./types";\n\n'
                        "/**\n"
                        " * Resolves once the socket reaches OPEN, or rejects on timeout. Tests await\n"
                        " * this instead of a fixed sleep, which is what made the reconnect test flake.\n"
                        " */\n"
                        "export function waitForSocketOpen(socket: ReconnectingSocket, timeoutMs = 5000): "
                        "Promise<void> {\n"
                        "  return new Promise((resolve, reject) => {\n"
                        "    if (socket.readyState === socket.OPEN) return resolve();\n"
                        "    const timer = setTimeout(() => reject(new Error(\"socket did not open\")), timeoutMs);\n"
                        '    socket.addEventListener("open", () => {\n'
                        "      clearTimeout(timer);\n"
                        "      resolve();\n"
                        "    });\n"
                        "  });\n"
                        "}\n",
                    ),
                    text("Reproduced it 3/10 runs on main; the state-based wait passes 50/50 locally."),
                ]
            ),
        },
    ]


# --- openhost: 3 workspaces (sidebar dressing) ------------------------------


def openhost_specs() -> list[dict]:
    return [
        {
            "repo": "openhost",
            "branch": "ops/tls-auto-renewal",
            "name": "Automate TLS certificate renewal",
            "prompt": light_turn(
                "Adding a scheduled job to renew TLS certs 30 days before expiry and reload nginx.",
                [
                    (
                        "scripts/renew_certs.sh",
                        "#!/usr/bin/env bash\nset -euo pipefail\ncertbot renew --quiet\nnginx -s reload\n",
                    )
                ],
                "Renewal script and cron entry added. Testing the dry-run path against staging next.",
            ),
        },
        {
            "repo": "openhost",
            "branch": "perf/nginx-proxy-cache",
            "name": "Tune nginx proxy cache",
            "prompt": light_turn(
                "Tuning the proxy cache so static assets stop hitting the origin on every request.",
                [
                    (
                        "nginx/cache.conf",
                        "proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=assets:64m inactive=7d;\n",
                    )
                ],
                "Cache zone configured with a 7-day inactive window. Measuring origin offload before rollout.",
            ),
        },
        {
            "repo": "openhost",
            "branch": "feat/first-deploy-wizard",
            "name": "Streamline first-deploy flow",
            "prompt": light_turn(
                "Collapsing the first-deploy wizard from five steps to two with smart defaults.",
                [
                    (
                        "web/onboarding/steps.ts",
                        'export const steps = ["connect-repo", "confirm-and-deploy"] as const;\n',
                    )
                ],
                "Reduced to connect + confirm. Wiring the smart-default detection for framework and port next.",
            ),
        },
    ]


# --- mngr: 2 workspaces (sidebar dressing) ----------------------------------


def mngr_specs() -> list[dict]:
    return [
        {
            "repo": "mngr",
            "branch": "feat/job-retry-queue",
            "name": "Add retry queue for failed jobs",
            "prompt": light_turn(
                "Adding a bounded retry queue with exponential backoff for jobs that fail transiently.",
                [
                    (
                        "mngr/jobs/retry.py",
                        "import time\n\n\ndef backoff(attempt: int) -> float:\n    return min(2 ** attempt, 60)\n",
                    )
                ],
                "Retry queue with capped exponential backoff is in. Adding a dead-letter path for exhausted jobs.",
            ),
        },
        {
            "repo": "mngr",
            "branch": "feat/dashboard-metrics",
            "name": "Manager dashboard metrics",
            "prompt": light_turn(
                "Adding throughput and queue-depth tiles to the manager dashboard.",
                [("mngr/web/metrics.py", "def queue_depth(q) -> int:\n    return len(q.pending)\n")],
                "Queue-depth and throughput tiles render from live counters. Adding a 24h sparkline next.",
            ),
        },
    ]


def all_specs() -> list[dict]:
    return [*sculptor_specs(), *openhost_specs(), *mngr_specs()]
