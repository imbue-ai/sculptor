"""Integration coverage for what Sculptor gives an agent it launches in a jj workspace.

An agent finds jj on its PATH even when the backend has none, because Sculptor puts
the jj it resolved first on the agent's PATH. A chat agent is told to load the jj
skill on its first turn: FakeClaude echoes the system prompt and the prompt it was
given, and FakePi says which skill its first prompt invoked. See
`sculptor.testing.jj_sculptor_instance` for the setup.
"""

import os
import re
import shlex
import shutil
from pathlib import Path

from playwright.sync_api import expect

from sculptor.agents.testing.fake_claude import ECHO_PROMPTS_ENV_VAR
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.fake_pi import install_fake_pi_binary
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjIsolatedEnv
from sculptor.testing.jj_sculptor_instance import bash_step
from sculptor.testing.jj_sculptor_instance import colocate_base_repo_with_origin
from sculptor.testing.jj_sculptor_instance import create_jj_workspace
from sculptor.testing.jj_sculptor_instance import get_active_project_id
from sculptor.testing.jj_sculptor_instance import multi_step_prompt
from sculptor.testing.jj_sculptor_instance import open_jj_workspace_agent
from sculptor.testing.jj_sculptor_instance import open_new_agent_in_workspace
from sculptor.testing.jj_sculptor_instance import set_use_jj_for_new_workspaces
from sculptor.testing.jj_sculptor_instance import use_jj_binary
from sculptor.testing.jj_sculptor_instance import write_file_step
from sculptor.testing.playwright_utils import settle_first_run_offer
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

_BOOKMARK = "jj-launch"
_JJ_SKILL_RULE = "skill is required for version control in this workspace"
_JJ_SKILL_REMINDER = 'skill="sculptor-jj:jujutsu"'
_JJ_SKILL_REMINDER_IN_PROMPT = re.compile(r"\[FakeClaude\] prompt:[\s\S]*" + re.escape(_JJ_SKILL_REMINDER))
_INTERPRETER_WRAPPER = '#!/bin/sh\nexec {interpreter} "$@"\n'


def _path_without_jj(shadow_root: Path) -> str:
    """The test process's PATH with every jj taken out of it.

    Each directory that holds a jj is replaced by a copy of it without the jj. The
    copy links to the other entries, except the interpreters, which it wraps,
    because a linked venv interpreter starts outside its venv.
    """
    directories: list[str] = []
    for index, directory in enumerate(os.environ["PATH"].split(os.pathsep)):
        if not (Path(directory) / "jj").exists():
            directories.append(directory)
            continue
        shadow = shadow_root / str(index)
        shadow.mkdir(parents=True)
        for entry in Path(directory).iterdir():
            if entry.name == "jj":
                continue
            if entry.name.startswith("python"):
                (shadow / entry.name).write_text(_INTERPRETER_WRAPPER.format(interpreter=shlex.quote(str(entry))))
                (shadow / entry.name).chmod(0o755)
            else:
                (shadow / entry.name).symlink_to(entry)
        directories.append(str(shadow))
    path = os.pathsep.join(directories)
    assert shutil.which("jj", path=path) is None, f"a jj is still on {path}"
    return path


@user_story("to have my agents run Sculptor's jj in a jj workspace, whatever jj the rest of my machine has")
def test_an_agent_runs_the_jj_sculptor_resolved_when_the_backend_has_no_jj_on_its_path(
    sculptor_instance_factory_: SculptorInstanceFactory,
    jj_binary: JjBinary,
    jj_isolated_env: JjIsolatedEnv,
    tmp_path: Path,
) -> None:
    use_jj_binary(sculptor_instance_factory_, jj_binary)
    colocate_base_repo_with_origin(sculptor_instance_factory_, jj_binary, tmp_path / "origin.git")
    sculptor_instance_factory_.update_environment(PATH=_path_without_jj(tmp_path / "path_without_jj"))
    report_path = tmp_path / "agent_jj.txt"

    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        settle_first_run_offer(page)
        task_page, _ = open_jj_workspace_agent(page, _BOOKMARK)
        chat_panel = task_page.get_chat_panel()

        send_chat_message(
            chat_panel=chat_panel,
            message=multi_step_prompt(
                [
                    bash_step(f"{{ command -v jj; jj --version; }} > '{report_path}' 2>&1"),
                    write_file_step("notes.md", "first notes\n"),
                    bash_step("jj describe -m 'Add notes'"),
                ]
            ),
        )
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)

        # The agent's own `jj describe` worked, so Sculptor could bookmark the change it described.
        expect(task_page.get_jj_identity_pill()).to_have_attribute("aria-label", f"Copy bookmark {_BOOKMARK}")
        found_path, version = report_path.read_text().splitlines()
        assert Path(found_path).parent.name == "jj-bin", f"the agent ran the jj at {found_path}"
        assert Path(found_path).resolve() == jj_binary.path.resolve(), f"{found_path} is not {jj_binary.path}"
        assert version.startswith(f"jj {jj_binary.version}"), f"the agent's jj reports {version}"


@user_story("to have a Claude agent in a jj workspace load the jj skill before it does anything else")
def test_a_claude_agent_is_told_to_load_the_jj_skill_on_its_first_turn_only(
    sculptor_instance_factory_: SculptorInstanceFactory,
    jj_binary: JjBinary,
    jj_isolated_env: JjIsolatedEnv,
    tmp_path: Path,
) -> None:
    use_jj_binary(sculptor_instance_factory_, jj_binary)
    colocate_base_repo_with_origin(sculptor_instance_factory_, jj_binary, tmp_path / "origin.git")
    sculptor_instance_factory_.update_environment(**{ECHO_PROMPTS_ENV_VAR: "1"})

    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        settle_first_run_offer(page)
        task_page, _ = open_jj_workspace_agent(page, _BOOKMARK)
        chat_panel = task_page.get_chat_panel()

        send_chat_message(chat_panel=chat_panel, message="hello")
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)

        first_answer = chat_panel.get_assistant_messages().nth(0)
        expect(first_answer).to_contain_text("jj workspace mode")
        expect(first_answer).to_contain_text(_JJ_SKILL_RULE)
        expect(first_answer).to_contain_text(_JJ_SKILL_REMINDER_IN_PROMPT)
        expect(first_answer).to_contain_text(
            re.compile(rf"Sculptor names this workspace's work with the jj bookmark `?{re.escape(_BOOKMARK)}`?")
        )

        send_chat_message(chat_panel=chat_panel, message="hello again")
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4, timeout=60_000)

        second_answer = chat_panel.get_assistant_messages().nth(1)
        expect(second_answer).to_contain_text(_JJ_SKILL_RULE)
        expect(second_answer).not_to_contain_text(_JJ_SKILL_REMINDER_IN_PROMPT)


@user_story("to have a pi agent in a jj workspace invoke the jj skill on its first turn")
def test_a_pi_agent_invokes_the_jj_skill_on_its_first_turn(
    sculptor_instance_factory_: SculptorInstanceFactory,
    jj_binary: JjBinary,
    jj_isolated_env: JjIsolatedEnv,
    tmp_path: Path,
) -> None:
    use_jj_binary(sculptor_instance_factory_, jj_binary)
    colocate_base_repo_with_origin(sculptor_instance_factory_, jj_binary, tmp_path / "origin.git")
    install_fake_pi_binary(sculptor_instance_factory_.fake_bin_dir)

    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        settle_first_run_offer(page)
        project_id = get_active_project_id(page)
        set_use_jj_for_new_workspaces(page, project_id, True)
        task_page = open_new_agent_in_workspace(page, create_jj_workspace(page, project_id, _BOOKMARK), "pi")
        chat_panel = task_page.get_chat_panel()

        send_chat_message(chat_panel=chat_panel, message="hello pi")
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)

        expect(chat_panel.get_assistant_messages().nth(0)).to_contain_text("[FakePi] followed skill: jujutsu")
