"""Integration coverage for the Jujutsu settings page: JJ_AVAILABLE, managed install, identity.

Hermetic / no-network strategy, as for pi (see test_pi_managed_install.py):

- Installed: pre-stage the pinned jj as the managed binary at ``jj/version-<pin>/jj``
  before the backend starts. jj never installs on startup, and the staged copy
  means nothing is downloaded.
- Too old: point a CUSTOM path at a stub script that reports an older jj.
- Not installed: the shared test config's pathless CUSTOM value resolves to nothing.
- Install failure: intercept the install POST in the browser.

The backend probes jj's identity with the environment agents get, which overlays the
instance's ``.env``. Each test writes ``JJ_CONFIG`` there, so the identity comes from
a file the test owns rather than from the machine running the tests.
"""

import json
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import Route
from playwright.sync_api import expect

from sculptor.services.dependency_management_service import DEPENDENCIES_DIR_NAME
from sculptor.services.dependency_management_service import _VERSION_DIR_PREFIX
from sculptor.services.jj_version import JJ_PINNED_VERSION
from sculptor.services.user_config.user_config import load_config
from sculptor.services.user_config.user_config import save_config
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

_INSTALL_ENDPOINT_GLOB = "**/api/v1/dependencies/install*"
_CHECKSUM_ERROR = "Checksum mismatch: pinned sha256 did not match the downloaded artifact"


def _sculptor_folder(factory: SculptorInstanceFactory) -> Path:
    return factory._delegate.sculptor_folder


def _set_jj_config(factory: SculptorInstanceFactory, jj_value: str) -> None:
    config_path = _sculptor_folder(factory) / "internal" / "config.toml"
    config = load_config(config_path)
    new_dependency_paths = config.dependency_paths.model_copy(update={"jj": jj_value})
    save_config(config.model_copy(update={"dependency_paths": new_dependency_paths}), config_path)


def _use_jj_user_config(factory: SculptorInstanceFactory, content: str) -> Path:
    """Give the backend's jj probes a user config file the test owns, via the instance's ``.env``."""
    jj_config_path = _sculptor_folder(factory) / "jj-user-config.toml"
    jj_config_path.write_text(content)
    (_sculptor_folder(factory) / ".env").write_text(f"JJ_CONFIG={jj_config_path}\n")
    return jj_config_path


def _stage_managed_jj(factory: SculptorInstanceFactory, jj_binary: JjBinary) -> None:
    """Stage the pinned jj where ``_find_managed_binary(JJ)`` looks, so MANAGED needs no download."""
    version_dir = (
        _sculptor_folder(factory)
        / "internal"
        / DEPENDENCIES_DIR_NAME
        / "jj"
        / f"{_VERSION_DIR_PREFIX}{JJ_PINNED_VERSION}"
    )
    version_dir.mkdir(parents=True)
    (version_dir / "jj").symlink_to(jj_binary.path)


@user_story("to see that Sculptor can use jj, and which jj it uses")
def test_jj_settings_report_a_managed_jj_with_an_identity_as_available(
    sculptor_instance_factory_: SculptorInstanceFactory, jj_binary: JjBinary
) -> None:
    _set_jj_config(sculptor_instance_factory_, "MANAGED")
    _stage_managed_jj(sculptor_instance_factory_, jj_binary)
    _use_jj_user_config(sculptor_instance_factory_, '[user]\nname = "Ada Lovelace"\nemail = "ada@example.com"\n')

    with sculptor_instance_factory_.spawn_instance() as instance:
        jj_section = navigate_to_settings_page(page=instance.page).click_on_jj()

        expect(jj_section.get_availability()).to_contain_text(
            f"jj {JJ_PINNED_VERSION} is available, managed by Sculptor"
        )
        expect(jj_section.get_mode_selector()).to_contain_text("Managed")
        expect(jj_section.get_up_to_date()).to_contain_text("Managed")
        expect(jj_section.get_identity()).to_have_text("Ada Lovelace <ada@example.com>")


@user_story("to be told when my own jj is too old for Sculptor")
def test_jj_settings_report_an_old_jj_as_unsupported(
    sculptor_instance_factory_: SculptorInstanceFactory, tmp_path: Path
) -> None:
    old_jj = tmp_path / "jj"
    old_jj.write_text(f'#!/bin/bash\necho "jj 0.45.0-{uuid4().hex}"\n')
    old_jj.chmod(0o755)
    _set_jj_config(sculptor_instance_factory_, str(old_jj))

    with sculptor_instance_factory_.spawn_instance() as instance:
        jj_section = navigate_to_settings_page(page=instance.page).click_on_jj()

        expect(jj_section.get_availability()).to_contain_text(f"{old_jj} reports jj 0.45.0")
        expect(jj_section.get_availability()).to_contain_text(f"Sculptor needs jj {JJ_PINNED_VERSION} or later")
        expect(jj_section.get_status()).to_contain_text(f"Needs {JJ_PINNED_VERSION} or later")


@user_story("to set the author identity jj needs with one click")
def test_jj_identity_form_fixes_a_missing_identity(
    sculptor_instance_factory_: SculptorInstanceFactory, jj_binary: JjBinary
) -> None:
    _set_jj_config(sculptor_instance_factory_, "MANAGED")
    _stage_managed_jj(sculptor_instance_factory_, jj_binary)
    jj_config_path = _use_jj_user_config(sculptor_instance_factory_, "")

    with sculptor_instance_factory_.spawn_instance() as instance:
        jj_section = navigate_to_settings_page(page=instance.page).click_on_jj()

        expect(jj_section.get_availability()).to_contain_text("jj has no author identity")
        jj_section.get_identity_name_input().fill("Grace Hopper")
        jj_section.get_identity_email_input().fill("grace@example.com")
        jj_section.get_identity_submit().click()

        expect(jj_section.get_identity()).to_have_text("Grace Hopper <grace@example.com>")
        expect(jj_section.get_availability()).to_contain_text("is available")
        assert "Grace Hopper" in jj_config_path.read_text()


@user_story("to retry a managed jj install after it fails")
def test_jj_settings_report_not_installed_and_surface_an_install_failure(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        jj_section = navigate_to_settings_page(page=page).click_on_jj()

        # The shared test config resolves jj to nothing.
        expect(jj_section.get_availability()).to_contain_text("jj is not installed")

        jj_section.get_mode_selector().click()
        jj_section.get_mode_option_managed().click()
        install_button = jj_section.get_install_button()
        expect(install_button).to_have_text("Install jj")

        install_requests: list[str] = []

        def _fail_install(route: Route) -> None:
            install_requests.append(route.request.url)
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"success": False, "error": _CHECKSUM_ERROR}),
            )

        page.route(_INSTALL_ENDPOINT_GLOB, _fail_install)
        try:
            install_button.click()
            expect(install_button).to_have_text("Retry")
        finally:
            page.unroute(_INSTALL_ENDPOINT_GLOB, _fail_install)

        assert any("tool=JJ" in url for url in install_requests), install_requests
