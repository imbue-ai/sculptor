import time
from collections.abc import Sequence
from typing import Any

from loguru import logger
from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect
from tenacity import retry
from tenacity import retry_if_exception_type
from tenacity import stop_after_attempt
from tenacity import wait_fixed

from sculptor.constants import ElementIDs


def wait_for_tiptap_ready(page: Page, *, timeout_ms: int = 10_000) -> None:
    """Best-effort wait for the Tiptap editor to initialize on the chat input.

    After page reloads (e.g. ``_reset_browser_state``), the contenteditable DOM
    element can be visible and clickable before TipTap has mounted the editor.
    Editor.tsx stamps ``data-editor-ready="true"`` on the contenteditable once
    the editor instance exists, so we wait on that deterministic attribute rather
    than polling React internals.  This gives the editor a head start before
    ``type_into_tiptap`` runs.

    This is non-fatal: if the editor isn't ready within ``timeout_ms``, we log
    and return.  ``type_into_tiptap`` re-resolves the chat input and retries on
    its own (up to ``_TIPTAP_EDITOR_FIND_TIMEOUT_MS``) as a fallback.
    """
    chat_input = page.get_by_test_id(ElementIDs.CHAT_INPUT)
    if chat_input.count() == 0:
        return
    try:
        expect(chat_input).to_have_attribute("data-editor-ready", "true", timeout=timeout_ms)
    except Exception as exc:
        logger.debug("wait_for_tiptap_ready timed out after {}ms: {}", timeout_ms, exc)


class PlaywrightIntegrationTestElement(Locator):
    """
    Represents an element on the page. This subclasses Locator for tooltips/type inference, but all calls are
    caught by __getattr__ and rerouted the self._locator, which is the real object. Internal locator methods or instance
    vars should never reach the actual Locator class being extended here.
    """

    def __init__(self, locator: Locator, page: Page) -> None:
        # Playwright page object stored for when HTML outside this element need to be accessed (e.g. dropdowns)
        self._page = page
        self._locator = locator

    def __getattr__(self, attr: str) -> Any:
        return getattr(self._locator, attr)


# The JS snippet shared by type_into_tiptap, clear_tiptap, etc. to find the
# TipTap editor instance for a contenteditable element. Prefers the
# ``__tiptapEditor`` handle that Editor.tsx stashes on the editor's own DOM node
# (stable, per-node), and falls back to walking the React fiber tree for any
# editor that predates the handle. The fiber walk reads private ``__reactFiber$``
# fields whose names can change across React/TipTap upgrades, so the handle is
# the preferred path.
_FIND_TIPTAP_EDITOR_JS = """
    let node = el;
    while (node) {
        if (node.__tiptapEditor?.commands) {
            return node.__tiptapEditor;
        }
        node = node.parentElement;
    }
    node = el;
    while (node) {
        const key = Object.keys(node).find(k => k.startsWith('__reactFiber$'));
        if (key) {
            let fiber = node[key];
            while (fiber) {
                const editor = fiber.memoizedProps?.editor;
                if (editor?.commands) {
                    return editor;
                }
                fiber = fiber.return;
            }
        }
        node = node.parentElement;
    }
    throw new Error('Could not find Tiptap editor instance');
""".strip()


# Total budget for type_into_tiptap to land its insert, across re-resolutions of
# the chat-input locator. After an agent/workspace switch the input remounts, so
# a single bind can land on the old, detaching editor; we re-resolve and retry
# within this window. A genuinely missing editor still fails, just later.
_TIPTAP_EDITOR_FIND_TIMEOUT_MS = 15_000


# NOTE: This is an exception to our rule to not use page.evaluate().
# Normally we prefer Playwright's built-in locator methods, but Tiptap/ProseMirror
# editors don't work with fill() (bypasses editor state) or type() for long strings
# (times out at ~150 chars/sec).  Using ProseMirror's transaction API is the
# only reliable way to set text in these editors regardless of length or content.
def type_into_tiptap(page: Page, locator: Locator, text: str) -> None:
    """Insert text into a Tiptap editor element.

    Uses ProseMirror's ``tr.insertText()`` via ``page.evaluate()`` to insert
    plain text directly into the editor's internal state.  This avoids the
    limitations of Playwright's built-in methods for contenteditable elements:

    - ``type()`` simulates individual keystrokes (~150 chars/sec), timing out
      for long strings like FakeClaude JSON commands.
    - ``fill()`` sets the DOM directly but bypasses ProseMirror's transaction
      system, so the editor overwrites the value on its next render.
    - ``insertContent(string)`` parses the string as HTML, so angle brackets
      in the text (e.g. ``<div>``) create DOM elements instead of literal text.
    - Clipboard paste (Cmd-V) goes through Tiptap's markdown parser, which
      mangles backticks, and also interferes with the user's system clipboard.
    """
    # Retry at the Python level, re-resolving the locator each attempt.
    #
    # After an agent/workspace switch the chat input remounts: the old editor
    # detaches and a new one mounts a beat later. A one-shot ``locator.evaluate``
    # binds whichever element ``get_by_test_id`` resolved at call time -- which
    # can be the *old, detaching* editor, whose React fiber never regains an
    # ``editor`` prop. An in-JS ``requestAnimationFrame`` loop on that captured
    # element would then spin until timeout while the new editor mounts unseen.
    # Re-invoking ``locator.click`` / ``locator.evaluate`` re-runs the locator,
    # so a stale bind is replaced by the live element on the next attempt; the
    # short in-JS poll still absorbs the ordinary "editor prop not wired yet"
    # case once we are on the right element.
    deadline = time.monotonic() + _TIPTAP_EDITOR_FIND_TIMEOUT_MS / 1000.0
    while True:
        locator.click()
        try:
            locator.evaluate(
                f"""(el, text) => new Promise((resolve, reject) => {{
                    const deadline = Date.now() + 1000;
                    const findEditor = (el) => {{ {_FIND_TIPTAP_EDITOR_JS} }};
                    const tryInsert = () => {{
                        try {{
                            const editor = findEditor(el);
                            const {{ tr }} = editor.state;
                            tr.insertText(text);
                            editor.view.dispatch(tr);
                            resolve();
                        }} catch (e) {{
                            if (Date.now() < deadline) {{
                                requestAnimationFrame(tryInsert);
                            }} else {{
                                reject(e);
                            }}
                        }}
                    }};
                    tryInsert();
                }})""",
                text,
            )
            return
        except Exception as exc:  # noqa: BLE001 — retried below until the budget is spent
            if "Could not find Tiptap editor instance" in str(exc) and time.monotonic() < deadline:
                continue
            raise


def insert_mention_into_tiptap(locator: Locator, mention_id: str, suggestion_char: str) -> None:
    """Insert a mention node into a TipTap editor element.

    Uses TipTap's ``insertContent()`` API to insert a mention node directly,
    bypassing the autocomplete UI.  This is useful for testing how mention
    nodes are serialized and stored without depending on the suggestion
    popover's keyboard interactions.
    """
    locator.evaluate(
        f"""(el, args) => {{
            const findEditor = (el) => {{ {_FIND_TIPTAP_EDITOR_JS} }};
            const editor = findEditor(el);
            editor.commands.focus("end");
            editor.commands.insertContent({{
                type: 'mention',
                attrs: {{ id: args.id, mentionSuggestionChar: args.char }},
            }});
        }}""",
        {"id": mention_id, "char": suggestion_char},
    )


def clear_tiptap(locator: Locator) -> None:
    """Clear all content from a TipTap editor element.

    Uses TipTap's ``clearContent()`` API via ``page.evaluate()`` to reset the
    editor. Useful before ``type_into_tiptap`` when existing content must be
    replaced rather than appended to.
    """
    locator.evaluate(
        f"""(el) => {{
            const findEditor = (el) => {{ {_FIND_TIPTAP_EDITOR_JS} }};
            findEditor(el).commands.clearContent();
        }}""",
    )


def get_tiptap_doc(locator: Locator) -> Any:
    """Return the editor's document as a ProseMirror JSON node tree.

    Pairs with ``set_tiptap_doc`` to snapshot and restore editor content
    losslessly — including entity-mention chips, which a markdown round-trip
    would flatten back to ``+[…]`` tokens.
    """
    return locator.evaluate(
        f"""(el) => {{
            const findEditor = (el) => {{ {_FIND_TIPTAP_EDITOR_JS} }};
            return findEditor(el).getJSON();
        }}""",
    )


def set_tiptap_doc(locator: Locator, doc: Any) -> None:
    """Replace the editor content with a ProseMirror JSON doc from ``get_tiptap_doc``."""
    locator.evaluate(
        f"""(el, doc) => {{
            const findEditor = (el) => {{ {_FIND_TIPTAP_EDITOR_JS} }};
            findEditor(el).commands.setContent(doc);
        }}""",
        doc,
    )


def set_tiptap_markdown(locator: Locator, markdown: str) -> None:
    """Replace the editor content with markdown source.

    Drives Tiptap's ``setContent`` with ``contentType: 'markdown'``, which is
    the same path used when restoring a draft from localStorage or pasting
    markdown text. This is the canonical way to load structured markdown
    (e.g. nested lists, code blocks) into the editor in a test, because
    ``type_into_tiptap`` uses ``tr.insertText`` and bypasses the markdown
    parser entirely.
    """
    locator.evaluate(
        f"""(el, md) => {{
            const findEditor = (el) => {{ {_FIND_TIPTAP_EDITOR_JS} }};
            const editor = findEditor(el);
            editor.commands.setContent(md, {{ contentType: 'markdown' }});
        }}""",
        markdown,
    )


def type_paragraphs_into_tiptap(locator: Locator, paragraphs: Sequence[str]) -> None:
    """Insert multiple paragraphs separated by real paragraph breaks.

    Unlike ``type_into_tiptap`` (which uses ``tr.insertText`` and creates hard
    breaks for ``\\n``), this helper uses ``editor.commands.enter()`` between
    paragraphs.  This creates actual ProseMirror paragraph nodes — including
    empty paragraphs for blank strings — matching what happens when a user
    presses Enter in the editor.
    """
    locator.click()
    # Build JS that inserts each paragraph with enter() between them
    js_parts = []
    for para in paragraphs:
        if para:
            js_parts.append(f"editor.commands.insertContent({_js_string(para)});")
        js_parts.append("editor.commands.enter();")
    # Remove the trailing enter() — we don't want a trailing paragraph break
    if js_parts:
        js_parts.pop()
    js_body = "\n            ".join(js_parts)
    locator.evaluate(
        f"""(el) => {{
            const findEditor = (el) => {{ {_FIND_TIPTAP_EDITOR_JS} }};
            const editor = findEditor(el);
            {js_body}
        }}""",
    )


def _js_string(s: str) -> str:
    """Escape a Python string for safe embedding in JS source."""
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


# NOTE: These are exceptions to our rule against using .type() in tests.
# Some UI behaviors (mention popups, slash command menus, debounce) are
# triggered by the keyDown/keyUp event sequence that only .type() produces;
# .fill() and insertContent() bypass keyboard events entirely.


def type_trigger_char(locator: Locator, char: str) -> None:
    """Type a single character into an input to trigger a UI popup.

    Some UI elements (e.g. TipTap ``@`` mention suggestions, ``/`` slash
    command menus) are activated by typing specific trigger characters through
    the keyboard event pipeline.  Playwright's ``fill()`` bypasses keyboard
    events entirely, so ``.type()`` is required.

    The locator is focused automatically before typing.
    """
    locator.type(char)


def type_with_delay(locator: Locator, text: str, delay: int) -> None:
    """Type text character by character with a delay between keystrokes.

    Used to test behaviors that depend on timing between individual keystrokes,
    such as debounce logic in search inputs.  Playwright's ``fill()`` sets the
    value instantly, bypassing the debounce entirely.
    """
    locator.type(text, delay=delay)


# NOTE: This is an exception to our rule against using .type() in tests.
# TipTap's ordered list input rule triggers on "1. " being typed through
# keyboard events — .fill() and insertText() bypass this entirely.
def type_ordered_list_then_text(page: Page, locator: Locator, items: Sequence[str], trailing_text: str) -> None:
    """Type an ordered list followed by text using real keyboard input.

    Types ``1. <first item>`` to trigger TipTap's ordered list input rule,
    then continues with Enter-separated items.  Two Enters exit the list,
    then types the trailing text.  This matches the real user interaction.
    """
    locator.click()
    page.keyboard.type(f"1. {items[0]}")
    for item in items[1:]:
        page.keyboard.press("Enter")
        page.keyboard.type(item)
    # Exit the list: Enter creates empty item, Enter again exits
    page.keyboard.press("Enter")
    page.keyboard.press("Enter")
    page.keyboard.type(trailing_text)


def tiptap_has_placeholder(locator: Locator, placeholder_text: str) -> bool:
    """Check whether any paragraph in a TipTap editor displays the given placeholder.

    The Placeholder extension sets a ``data-placeholder`` attribute on empty
    nodes.  This helper inspects the DOM directly via ``locator.evaluate()``
    so that tests don't need raw CSS-selector locators.
    """
    return locator.evaluate(
        """(el, text) => {
            const ps = el.querySelectorAll('p[data-placeholder]');
            return Array.from(ps).some(p => p.getAttribute('data-placeholder') === text);
        }""",
        placeholder_text,
    )


def get_tiptap_placeholder_paragraphs(locator: Locator, placeholder_text: str) -> Locator:
    """Return the ``<p>`` nodes showing the given TipTap placeholder text.

    The Placeholder extension sets ``data-placeholder`` on empty nodes; an empty
    result means the placeholder is hidden. Returning a Locator (rather than the
    snapshot bool of ``tiptap_has_placeholder``) lets callers use
    ``expect(...).to_have_count(0)`` so Playwright auto-retries.
    """
    return locator.locator(f'p[data-placeholder="{placeholder_text}"]')


# NOTE: This is an exception to our rule to not use page.evaluate().
# There is no Playwright API to wait for a single animation frame.
# page.wait_for_timeout(N) is the alternative, but requires guessing a
# millisecond value that is either too large (slow tests) or too small (flaky).
# requestAnimationFrame guarantees exactly one render cycle (~16 ms).
def wait_for_one_frame(page: Page) -> None:
    """Wait for one browser animation frame to allow React to re-render.

    Use after programmatically updating editor content (e.g. via
    ``type_into_tiptap``) when the test needs a React component to have
    re-rendered with the new Jotai atom value before the next interaction.
    """
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(resolve))")


@retry(
    retry=retry_if_exception_type(AssertionError),
    stop=stop_after_attempt(5),
    wait=wait_fixed(0.25),
    reraise=True,
)
def dismiss_with_escape(dialog: Locator) -> None:
    """Press Escape on a Radix dialog and retry until it closes.

    Radix's ``DismissableLayer`` attaches its Escape keydown listener in a
    ``useEffect``, so an Escape that lands before that effect runs is dropped.
    Retry until the dialog closes.

    The 2 s per-attempt timeout is intentional: combined with the 5-attempt
    retry budget (~11 s total) it replaces a single 30 s ``expect`` wait
    rather than tightening it.
    """
    dialog.press("Escape")
    expect(dialog).not_to_be_visible(timeout=2_000)


# Budget for open_radix_toggle. The 2 s per-attempt timeout combined with the
# 5-attempt retry budget replaces a single 30 s ``expect`` wait rather than
# tightening it (mirrors dismiss_with_escape).
_RADIX_OPEN_ATTEMPTS = 5
_RADIX_OPEN_TIMEOUT_MS = 2_000
_RADIX_OPEN_RETRY_INTERVAL_MS = 250


def open_radix_toggle(page: Page, trigger: Locator) -> None:
    """Click a Radix toggle trigger and retry until it reports open.

    Idempotent and verified: a Radix trigger toggles, so clicking one that is
    already open would close it. Gate on the trigger's ``data-state`` and wait
    until it is actually open, so repeated open/read/close cycles (e.g. flipping
    a checkbox menu item then re-reading) stay reliable. Radix can also swallow
    the click in the brief settle window right after a previous close, so retry
    until ``data-state`` flips to open.
    """
    expect(trigger).to_be_visible()
    for _attempt in range(_RADIX_OPEN_ATTEMPTS):
        if trigger.get_attribute("data-state") == "open":
            return
        trigger.click()
        try:
            expect(trigger).to_have_attribute("data-state", "open", timeout=_RADIX_OPEN_TIMEOUT_MS)
            return
        except AssertionError:
            page.wait_for_timeout(_RADIX_OPEN_RETRY_INTERVAL_MS)
    expect(trigger).to_have_attribute("data-state", "open")
