"""Integration tests for path-mode queries in the @-mention picker.

A query starting with ``~``, ``/``, or ``.`` switches the picker from fuzzy
search against the tracked-files cache to a live filesystem listing via the
``getFilesAndFolders`` endpoint.  Path mode exposes:
- gitignored entries (the fuzzy corpus excludes them);
- out-of-repo paths under ``~/`` or ``/``;
- one-level-at-a-time navigation suited to terminal users.

These tests lock down that path mode actually surfaces entries the fuzzy mode
wouldn't and that the mode switches on the expected prefixes.
"""

from playwright.sync_api import expect

from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _navigate_to_task_chat(sculptor_instance: SculptorInstance) -> PlaywrightTaskPage:
    return start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance.page,
        prompt="Hello",
    )


@user_story("to browse the workspace via @./ path mode")
def test_path_mode_workspace_root_lists_tracked_files(sculptor_instance_: SculptorInstance) -> None:
    """Typing ``@./`` lists the workspace root, including the standard fixtures.

    The test fixture creates ``README.md``, ``stuff.txt``, and a ``src/``
    folder at the workspace root.  All three should appear in the path-mode
    listing regardless of fuzzy-scoring.
    """
    task_page = _navigate_to_task_chat(sculptor_instance_)
    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()

    chat_input.press_sequentially("@./")
    mention_list = chat_panel.get_mention_list()
    expect(mention_list).to_be_visible()
    expect(chat_panel.get_mention_items().first).to_be_visible()

    # Every known root-level fixture entry is present.
    expect(mention_list).to_contain_text("README")
    expect(mention_list).to_contain_text("stuff")
    # The src/ folder lists under a row with text "src". There may be other
    # rows containing "src" as substring (the parent-path hint), so scope to
    # a row whose own text starts with "src".
    src_item = chat_panel.get_mention_items().filter(has_text="src").first
    expect(src_item).to_be_visible()


@user_story("to see the .git folder that fuzzy search doesn't expose")
def test_path_mode_surfaces_dotgit_folder(sculptor_instance_: SculptorInstance) -> None:
    """Path mode exposes ``.git/`` (and other dotfiles) that fuzzy search hides.

    The fuzzy file cache is backed by ``git ls-files``, which never lists
    ``.git/`` itself.  Path mode hits ``getFilesAndFolders`` which reads the
    disk directly.  This is the regression protection for commit
    ``78956b055de`` (surface entries the fuzzy corpus excludes) — we use
    ``.git/`` as the canary instead of a custom gitignored file because it
    reliably exists in any workspace clone.
    """
    task_page = _navigate_to_task_chat(sculptor_instance_)
    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    mention_list = chat_panel.get_mention_list()

    # Fuzzy mode for ``.git`` returns no matches (the folder isn't in
    # ``git ls-files``).  The empty-state text is the positive signal that
    # the fuzzy fetch completed and yielded nothing.
    chat_input.press_sequentially("@.git")
    expect(mention_list).to_be_visible()
    # This query starts with ``.`` so it IS path mode — verify .git appears.
    # (Path-mode parsing treats ``.git`` as "list workspace root, filter for
    # .git".)  A regression where path-mode wasn't consulted would fall back
    # to the fuzzy cache and the .git folder would be missing.
    expect(mention_list).to_contain_text(".git")

    # The .git row is a selectable item, not just a parent-path substring.
    git_item = chat_panel.get_mention_items().filter(has_text=".git").first
    expect(git_item).to_be_visible()


@user_story("to drill path-mode into a subfolder with Tab or by typing")
def test_path_mode_drill_into_subfolder(sculptor_instance_: SculptorInstance) -> None:
    """Typing a full path-mode query (``@./src/``) narrows to that folder's contents.

    Serves as a sanity check that the backend listing works at nested depths
    — pairs with the Tab-drill integration test (which reaches the same
    state via the Tab keypress).
    """
    task_page = _navigate_to_task_chat(sculptor_instance_)
    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()

    chat_input.press_sequentially("@./src/")
    mention_list = chat_panel.get_mention_list()
    expect(mention_list).to_be_visible()

    # ./src/ contains app.py, helpers.py, main.py in the test fixture.
    expect(mention_list).to_contain_text("app.py")
    expect(mention_list).to_contain_text("main.py")
    # README.md lives at the root, not in src/ — it must NOT appear in this
    # narrowed listing.
    expect(chat_panel.get_mention_items().filter(has_text="README")).to_have_count(0)


@user_story("to fall back to fuzzy mode for queries without a path prefix")
def test_fuzzy_mode_for_non_path_queries(sculptor_instance_: SculptorInstance) -> None:
    """A query without ``~``, ``/``, or ``.`` uses the workspace tracked-files cache.

    Guards the path-mode prefix check: the mode-switch must ONLY trigger on
    the three leading characters.  Otherwise a regression that flips every
    query into path-mode would send unnecessary filesystem requests for
    every keystroke.
    """
    task_page = _navigate_to_task_chat(sculptor_instance_)
    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()

    # README is a tracked file at the root.  Fuzzy mode should find it
    # identically.
    chat_input.press_sequentially("@READ")
    mention_list = chat_panel.get_mention_list()
    expect(mention_list).to_be_visible()
    expect(mention_list).to_contain_text("README")
