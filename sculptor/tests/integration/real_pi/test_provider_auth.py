"""Real pi conformance for Sculptor's provider-auth interop with auth.json.

These prove against the real pinned ``pi`` binary that Sculptor's auth.json writes
and authenticated-set read interoperate with pi: a Sculptor-written auth.json is
honored by real pi (its provider's models appear), the merge preserves pre-existing
entries at mode 0600, and the authenticated set agrees with what pi exposes.

auth.json is always isolated via ``PI_CODING_AGENT_DIR`` pointed at a temp dir, so
these never touch the developer's real ``~/.pi/agent/auth.json``.

Manual conformance (not automated here): the full interactive ``/login`` round-trip
(provider selector -> key entry -> pi writes auth.json) and per-provider ``/logout``
removal are driven through pi's TUI selector, which is too fragile to keystroke-drive
deterministically; they are verified by hand against the real binary. The automated
coverage below exercises the same "pi honors the Sculptor-written file" guarantee via
the paste-key write path.
"""

import json
import os
from pathlib import Path

import pytest
from playwright.sync_api import expect

from sculptor.agents.pi_agent.authenticated_providers import compute_authenticated_provider_ids
from sculptor.agents.pi_agent.authenticated_providers import resolve_pi_auth_json_path
from sculptor.agents.pi_agent.authenticated_providers import write_auth_json_entry
from sculptor.constants import ElementIDs
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from tests.integration.real_pi.helpers import real_pi


@real_pi
def test_write_auth_json_merges_preserves_and_is_0600(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A Sculptor paste-key write merges into auth.json, preserving other entries, at 0600."""
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    (tmp_path / "auth.json").write_text(
        json.dumps({"some-oauth-provider": {"type": "oauth", "token": "preexisting"}}), encoding="utf-8"
    )

    # Store the $ENV reference form so no literal secret lands even in the temp file.
    write_auth_json_entry("anthropic", "$ANTHROPIC_API_KEY")

    auth_json_path = resolve_pi_auth_json_path()
    data = json.loads(auth_json_path.read_text(encoding="utf-8"))
    assert data["some-oauth-provider"] == {"type": "oauth", "token": "preexisting"}
    assert data["anthropic"] == {"type": "api_key", "key": "$ANTHROPIC_API_KEY"}
    assert (auth_json_path.stat().st_mode & 0o777) == 0o600


@real_pi
def test_authenticated_set_matches_written_auth_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The authenticated set reflects the written provider and excludes unconfigured ones."""
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    write_auth_json_entry("anthropic", "$ANTHROPIC_API_KEY")

    authenticated = compute_authenticated_provider_ids()
    assert "anthropic" in authenticated
    # A provider with neither an auth.json entry nor an env var is not authenticated.
    assert "deepseek" not in authenticated


@real_pi
@pytest.mark.timeout(300)
def test_real_pi_honors_written_auth_json(
    sculptor_instance_factory_: SculptorInstanceFactory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real pi returns a non-empty catalog given a Sculptor-written auth.json.

    Writing the anthropic credential (as a $ENV reference pi resolves) and pointing
    pi at the same isolated config dir, a real pi agent surfaces its models — never
    the empty-state CTA — proving pi honors the Sculptor-written file end-to-end.
    """
    agent_dir = tmp_path / "pi-agent"
    agent_dir.mkdir()
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(agent_dir))
    assert os.environ.get("ANTHROPIC_API_KEY"), "real_pi tests require ANTHROPIC_API_KEY"
    write_auth_json_entry("anthropic", "$ANTHROPIC_API_KEY")

    sculptor_instance_factory_.update_environment(PI_CODING_AGENT_DIR=str(agent_dir))
    with sculptor_instance_factory_.spawn_instance() as instance:
        task_page = start_task_and_wait_for_ready(
            sculptor_page=instance.page,
            workspace_name="Real Pi Auth",
            model_name=None,
            agent_type="pi",
        )
        chat_panel = task_page.get_chat_panel()
        # pi honored the auth.json: the picker is populated, not the no-providers CTA.
        expect(chat_panel.get_model_selector()).to_be_visible(timeout=60_000)
        expect(instance.page.get_by_test_id(ElementIDs.PI_PICKER_EMPTY_STATE)).to_have_count(0)
