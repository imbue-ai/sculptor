"""Integration coverage for a repository's jj controls in Settings > Repositories.

Each test spawns its own instance, so a test that colocates its repository with jj
leaves no `.jj` behind for another.

jj is given to the backend as a CUSTOM path to the pinned binary, so nothing is
downloaded. The `jj_isolated_env` fixture gives the test process an empty jj user
config and a test identity; the backend inherits that environment when it is spawned,
so neither the test's jj nor the backend's reads or writes the developer's own jj
config, and JJ_AVAILABLE does not depend on the machine running the tests.
"""

from pathlib import Path

from playwright.sync_api import Route
from playwright.sync_api import expect

from sculptor.services.user_config.user_config import load_config
from sculptor.services.user_config.user_config import save_config
from sculptor.testing.elements.settings_repositories import PlaywrightRepositoriesSettingsElement
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjIsolatedEnv
from sculptor.testing.jj_repos import colocate_with_jj
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

_COLOCATE_ENDPOINT_GLOB = "**/api/v1/projects/*/jj/colocate"


def _use_jj_binary(factory: SculptorInstanceFactory, jj_binary: JjBinary) -> None:
    """Point the backend at the pinned jj as a CUSTOM path, before it starts."""
    config_path = factory._delegate.sculptor_folder / "internal" / "config.toml"
    config = load_config(config_path)
    dependency_paths = config.dependency_paths.model_copy(update={"jj": str(jj_binary.path)})
    save_config(config.model_copy(update={"dependency_paths": dependency_paths}), config_path)


def _open_repo_config(instance: SculptorInstance) -> PlaywrightRepositoriesSettingsElement:
    repos_settings = navigate_to_settings_page(page=instance.page).click_on_repositories()
    repos_settings.expand_repo_config()
    return repos_settings


@user_story("to be told that the repository jj controls need jj, and where to set it up")
def test_repo_jj_controls_are_disabled_without_jj(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    # The shared test config resolves jj to nothing.
    with sculptor_instance_factory_.spawn_instance() as instance:
        repos_settings = _open_repo_config(instance)

        expect(repos_settings.get_jj_colocation_switch()).to_be_disabled()
        expect(repos_settings.get_jj_colocation_switch()).not_to_be_checked()
        expect(repos_settings.get_use_jj_for_new_workspaces_switch()).to_be_disabled()
        expect(repos_settings.get_jj_badge()).to_have_count(0)
        expect(
            repos_settings.get_jj_unavailable_reason(
                "jj is not installed: install it or set its path on the Jujutsu settings page"
            )
        ).to_be_visible()

        jj_section = repos_settings.open_jj_settings()

        expect(jj_section.get_availability()).to_contain_text("jj is not installed")


@user_story("to fix jj outside Sculptor and have the repository jj controls notice")
def test_repo_jj_controls_recheck_a_jj_identity_set_outside_sculptor(
    sculptor_instance_factory_: SculptorInstanceFactory, jj_binary: JjBinary
) -> None:
    _use_jj_binary(sculptor_instance_factory_, jj_binary)
    # The backend reads jj's identity with the environment agents get, which overlays
    # the instance's .env, so the identity comes from a file this test owns.
    sculptor_folder = sculptor_instance_factory_._delegate.sculptor_folder
    jj_config_path = sculptor_folder / "jj-user-config.toml"
    jj_config_path.write_text("")
    (sculptor_folder / ".env").write_text(f"JJ_CONFIG={jj_config_path}\n")
    no_identity_reason = "jj has no author identity"

    with sculptor_instance_factory_.spawn_instance() as instance:
        repos_settings = _open_repo_config(instance)
        colocation_switch = repos_settings.get_jj_colocation_switch()
        expect(colocation_switch).to_be_disabled()
        expect(repos_settings.get_jj_unavailable_reason(no_identity_reason)).to_be_visible()

        jj_config_path.write_text('[user]\nname = "Ada Lovelace"\nemail = "ada@example.com"\n')
        repos_settings.get_jj_recheck_button().click()

        expect(colocation_switch).to_be_enabled()
        expect(repos_settings.get_jj_unavailable_reason(no_identity_reason)).to_be_hidden()

        # Opening the Repositories section checks again by itself. The Git section
        # is the way back because the Jujutsu section also checks when it opens.
        jj_config_path.write_text("")
        settings_page = navigate_to_settings_page(page=instance.page)
        settings_page.click_on_git()
        repos_settings = settings_page.click_on_repositories()
        repos_settings.expand_repo_config()

        expect(repos_settings.get_jj_colocation_switch()).to_be_disabled()
        expect(repos_settings.get_jj_unavailable_reason(no_identity_reason)).to_be_visible()


@user_story("to make a plain git repository a jj colocation from Settings")
def test_initializing_a_colocation_shows_loading_then_locks_on(
    sculptor_instance_factory_: SculptorInstanceFactory, jj_binary: JjBinary, jj_isolated_env: JjIsolatedEnv
) -> None:
    _use_jj_binary(sculptor_instance_factory_, jj_binary)
    repo_path: Path = sculptor_instance_factory_.base_repo.base_path

    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        repos_settings = _open_repo_config(instance)
        colocation_switch = repos_settings.get_jj_colocation_switch()
        use_jj_switch = repos_settings.get_use_jj_for_new_workspaces_switch()
        expect(colocation_switch).to_be_enabled()
        expect(colocation_switch).not_to_be_checked()
        expect(use_jj_switch).to_be_disabled()

        # Hold the colocate request in the browser until released, so the loading
        # state is observed however fast jj colocates a small repository.
        state = {"release": False, "post_count": 0}

        def hold_colocate(route: Route) -> None:
            state["post_count"] += 1
            while not state["release"]:
                page.wait_for_timeout(50)
            route.continue_()

        page.route(_COLOCATE_ENDPOINT_GLOB, hold_colocate)
        try:
            colocation_switch.click()
            expect(repos_settings.get_jj_colocation_dialog()).to_be_visible()
            confirm = repos_settings.get_jj_colocation_dialog_confirm()
            expect(confirm).to_be_enabled()
            confirm.click()

            expect(repos_settings.get_jj_colocation_dialog()).to_be_hidden()
            expect(repos_settings.get_jj_colocation_initializing()).to_be_visible()
            expect(colocation_switch).to_be_disabled()
            expect(colocation_switch).not_to_be_checked()

            state["release"] = True
            expect(colocation_switch).to_be_checked()
            assert state["post_count"] == 1, f"expected a single colocate request, saw {state['post_count']}"
        finally:
            # Release in case an assertion above failed while the request was still
            # held, and give the handler a beat to reach route.continue_().
            state["release"] = True
            page.wait_for_timeout(100)
            page.unroute(_COLOCATE_ENDPOINT_GLOB, hold_colocate)

        expect(colocation_switch).to_be_checked()
        expect(colocation_switch).to_be_disabled()
        expect(repos_settings.get_jj_colocation_initializing()).to_be_hidden()
        expect(use_jj_switch).to_be_checked()
        expect(use_jj_switch).to_be_enabled()
        expect(repos_settings.get_jj_badge()).to_be_visible()
        assert (repo_path / ".jj").is_dir()

        use_jj_switch.click()
        expect(use_jj_switch).not_to_be_checked()
        expect(repos_settings.get_jj_badge()).to_have_count(0)


@user_story("to see that a repository I colocated with jj myself is a jj colocation")
def test_a_repository_colocated_before_startup_shows_locked_on(
    sculptor_instance_factory_: SculptorInstanceFactory, jj_binary: JjBinary, jj_isolated_env: JjIsolatedEnv
) -> None:
    _use_jj_binary(sculptor_instance_factory_, jj_binary)
    colocate_with_jj(jj_binary, sculptor_instance_factory_.base_repo.base_path)

    with sculptor_instance_factory_.spawn_instance() as instance:
        repos_settings = _open_repo_config(instance)
        colocation_switch = repos_settings.get_jj_colocation_switch()
        use_jj_switch = repos_settings.get_use_jj_for_new_workspaces_switch()

        expect(colocation_switch).to_be_checked()
        expect(colocation_switch).to_be_disabled()
        # Colocating outside Sculptor leaves the repository's own choice of jj workspaces off.
        expect(use_jj_switch).not_to_be_checked()
        expect(use_jj_switch).to_be_enabled()
        expect(repos_settings.get_jj_badge()).to_have_count(0)

        use_jj_switch.click()

        expect(use_jj_switch).to_be_checked()
        expect(repos_settings.get_jj_badge()).to_be_visible()
