"""Slow-tier integration test for the Add Repository "not configured" CTA.

Uses ``sculptor_instance_factory_`` so we can spawn a backend whose PATH
*excludes* the real gh/glab binaries — the dialog's
NotConfiguredSection branch is unreachable when gh is on PATH and authed
because the dependency status atom (driven by both the initial GET and a
WebSocket stream) ends up reporting installed=true.

This is the only slow-tier test in the add-repo group; everything else
uses the shared ``sculptor_instance_`` fixture.
"""

import os
from pathlib import Path

from playwright.sync_api import expect

from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story


def _set_path_without_gh(factory: SculptorInstanceFactory) -> None:
    """Remove every PATH entry that contains a real gh binary so the backend
    can't find it. Matches the pattern used by ``test_pr_button_errors.py``."""
    current_path = os.environ.get("PATH", "")
    filtered = [d for d in current_path.split(":") if not (Path(d) / "gh").exists()]
    factory._delegate.environment["PATH"] = ":".join(filtered)


@user_story("to see a Configure GitHub CTA in the dialog footer when gh isn't installed")
def test_not_configured_shows_configure_cta(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """gh missing from PATH → the GitHub form mounts NotConfiguredSection and
    the dialog footer swaps the Add Repository submit button for a
    "Configure GitHub" CTA that deep-links to the dependencies settings."""
    _set_path_without_gh(sculptor_instance_factory_)

    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        settings_page = navigate_to_settings_page(page=page)
        repos_settings = settings_page.click_on_repositories()
        add_repo_dialog = repos_settings.open_add_repo_dialog()

        add_repo_dialog.get_source_github_card().click()

        # The not-configured section replaces the combobox in the form.
        expect(add_repo_dialog.get_not_configured_section()).to_be_visible()

        # The footer's submit button is replaced by the Configure CTA.
        configure_cta = add_repo_dialog.get_configure_cta_button()
        expect(configure_cta).to_be_visible()
        expect(configure_cta).to_contain_text("Configure GitHub")
        # The normal submit button must be absent in this state — the CTA
        # is the only primary footer button.
        expect(add_repo_dialog.get_submit_button()).to_have_count(0)
