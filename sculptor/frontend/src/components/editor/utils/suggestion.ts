import { computePosition, flip, offset, shift, size } from "@floating-ui/dom";
import type { Editor } from "@tiptap/core";
import { PluginKey, type Transaction } from "@tiptap/pm/state";
import { ReactRenderer } from "@tiptap/react";
import type { SuggestionOptions, SuggestionProps } from "@tiptap/suggestion";
import type { ForwardRefExoticComponent, RefAttributes } from "react";

import { getFilesAndFolders } from "~/api";
import { ensureWorkspaceFiles } from "~/common/state/hooks/useWorkspaceFiles";
import { CHAT_INPUT_ELEMENT_ID } from "~/common/utils/elementIds";

import { MentionList } from "../MentionList.jsx";
import { dismissTrigger, isPositionDismissed } from "../suggestionDismissalPlugin";
import type { SuggestionAction, SuggestionListRef } from "../SuggestionListContainer";
import { fuzzySearchFiles, scoreFilePath } from "./fuzzyFileScorer";

export class SuggestionItem {
  id: string;
  label: string;
  /** Parent directory path (e.g. "src/components/"), shown as secondary text. */
  parentPath: string;

  constructor(id: string, label: string, parentPath: string = "") {
    this.id = id;
    this.label = label;
    this.parentPath = parentPath;
  }
}

/** The slice of the `@tiptap/suggestion` plugin state this guard reads. */
type SuggestionPluginState = { active: boolean };

/**
 * Builds a `shouldShow` predicate that stops a suggestion popover from
 * *opening* purely because the caret moved into pre-existing text that
 * happens to contain the trigger character.
 *
 * The `@tiptap/suggestion` plugin re-evaluates its trigger match on every
 * transaction — including the selection-only transactions produced by
 * arrow-key navigation or a mouse click. Without this guard, moving the
 * caret into a path like `/Users/foo` (whose leading `/` is a valid trigger)
 * springs the menu open even though the user never typed a command
 * (SCU-1298). The same applies to the `@` file and `+` prefilter triggers.
 *
 * The popover may open only while the user is actively typing (a doc-changing
 * transaction). An already-open popover is left alone so an in-query edit or
 * selection change doesn't tear it down.
 */
export const showSuggestionOnlyWhenTyping =
  (pluginKey: PluginKey<SuggestionPluginState>) =>
  ({ editor, transaction }: { editor: Editor; transaction: Transaction }): boolean => {
    if (transaction.docChanged) {
      return true;
    }
    // Inside the suggestion plugin's `apply`, `editor.state` is still the
    // pre-transaction state, so this reads the *previous* active flag: a
    // popover that is already open stays open across a pure cursor move,
    // while a closed one is not allowed to spring open from one.
    return pluginKey.getState(editor.state)?.active ?? false;
  };

type SuggestionListComponent = ForwardRefExoticComponent<SuggestionProps & RefAttributes<SuggestionListRef>>;

/**
 * Number of TipTap suggestion popover sessions currently rendered across
 * every editor (file `@`-mention, skill `/`-mention, entity-mention
 * `+`-picker). Each `renderSuggestion` factory increments on `onBeforeStart`
 * and decrements on `closePopover`, gated by the factory's own `isActive`
 * flag so duplicate lifecycle calls (e.g. `closePopover` invoked from both
 * `handleDocumentPointerDown` and `onExit`) don't drift the count.
 *
 * Read by `Editor` (`editorProps.handleKeyDown`) to short-circuit the parent
 * `onKeyDown` for Enter while a popover is open. ProseMirror calls
 * `editorProps` before plugin `handleKeyDown` (see `someProp` in
 * prosemirror-view), so a ChatInput configured with `send_message = Enter`
 * would otherwise submit the typed text before the suggestion plugin had a
 * chance to accept the highlighted row. Deferring to the plugin restores the
 * documented contract: Enter accepts the suggestion whenever the popover is
 * visible, regardless of the configured keybinding (SCU-1134).
 */
let activeSuggestionPopoverCount = 0;

export const isAnySuggestionPopoverActive = (): boolean => activeSuggestionPopoverCount > 0;

const POPOVER_VIEWPORT_MARGIN = 8;
const POPOVER_INPUT_OVERLAP = 8;
// Fallback for --space-9 at default scaling. Reserves room above the popover
// so it never crowds the workspace tab bar / header — clamps the popover
// height when the input sits far down the screen.
const POPOVER_TOP_MARGIN_FALLBACK = 64;

const getPopoverTopMargin = (element: HTMLElement): number =>
  parseFloat(getComputedStyle(element).getPropertyValue("--space-9")) || POPOVER_TOP_MARGIN_FALLBACK;

/**
 * Attributes that Radix Theme sets on the root element to scope CSS variables.
 * Note: `data-has-background` is intentionally excluded — it would give the
 * wrapper an opaque background that shows through the rounded corners of the
 * inner suggestion list.
 */
const THEME_ATTRIBUTES = [
  "data-accent-color",
  "data-gray-color",
  "data-panel-background",
  "data-radius",
  "data-scaling",
] as const;

/**
 * Append an element to document.body while preserving Radix theme CSS variable
 * inheritance and ensuring it remains interactive above modal dialogs.
 *
 * The root Radix `<Theme>` element (`[data-is-root-theme]`) creates a stacking
 * context with `z-index: 0`, so elements inside it cannot paint above Radix
 * Dialog portals (which are appended directly to `document.body`). To allow
 * suggestion popovers to float above dialogs, we append them to `document.body`
 * and copy the theme class + data attributes so that the Radix CSS variables
 * (e.g. `--gold-1`, `--radius-3`) remain available.
 *
 * When a modal Radix Dialog is open, its DismissableLayer sets
 * `document.body.style.pointerEvents = "none"` to block interactions outside
 * the dialog. It also listens for `pointerdown` on `document` to detect
 * "outside" clicks and dismiss the dialog. We counteract both:
 *   1. `pointer-events: auto` on the element overrides the body's `none`.
 *   2. Stopping `pointerdown` propagation prevents the DismissableLayer's
 *      document-level listener from seeing the event as an outside click.
 */
const appendToBodyWithTheme = (element: HTMLElement): void => {
  const rootTheme = document.querySelector("[data-is-root-theme]");
  if (rootTheme instanceof HTMLElement) {
    element.classList.add("radix-themes");
    for (const attr of THEME_ATTRIBUTES) {
      const value = rootTheme.getAttribute(attr);
      if (value !== null) {
        element.setAttribute(attr, value);
      }
    }

    // Copy light/dark class for appearance-dependent variables.
    if (rootTheme.classList.contains("light")) {
      element.classList.add("light");
    } else if (rootTheme.classList.contains("dark")) {
      element.classList.add("dark");
    }
  }

  // Override `pointer-events: none` that Radix Dialog sets on document.body
  // when a modal dialog is open. Without this, clicks on the popover are
  // silently swallowed.
  element.style.pointerEvents = "auto";

  // Prevent pointer events from bubbling to document, where Radix's
  // DismissableLayer listens for "outside" clicks to dismiss the dialog.
  // Without this, clicking a suggestion item would first dismiss the dialog,
  // destroying the editor and the popover along with it.
  element.addEventListener("pointerdown", (e) => e.stopPropagation());

  document.body.appendChild(element);
};

const MIN_POPOVER_WIDTH = 300;
const POPOVER_INPUT_HORIZONTAL_INSET = 32;
const POPOVER_MAX_HEIGHT_RATIO = 0.45;
const POPOVER_MAX_HEIGHT_PX = 600;

/**
 * Anchor for the suggestion popover. Two modes:
 *
 * - `inputBox`: anchored to the rounded chat-input container (`#chat-input`).
 *   Used in the chat input, where the popover overlays the small input box.
 *   The whole input rect is the anchor so width/height calculations match the
 *   visible chrome.
 *
 * - `cursor`: anchored to the caret's bounding rect (TipTap's `clientRect`).
 *   Used in the Notes panel and any other large editor — pinning the popover
 *   to the editor's outer rect would float it far from where the user is
 *   typing and shrink it off-screen when the editor scrolls.
 */
type AnchorMode = "inputBox" | "cursor";
type Anchor = { mode: AnchorMode; rect: DOMRect };

const resolveAnchor = (editorViewDom: Element, clientRect: () => DOMRect | null): Anchor => {
  const promptContainer = editorViewDom.closest(`#${CHAT_INPUT_ELEMENT_ID}`);
  if (promptContainer) {
    return { mode: "inputBox", rect: promptContainer.getBoundingClientRect() };
  }
  const cursorRect = clientRect();
  if (cursorRect) {
    return { mode: "cursor", rect: cursorRect };
  }
  // Detached editor in tests / pre-mount: fall back to the editor DOM box.
  return { mode: "cursor", rect: editorViewDom.getBoundingClientRect() };
};

/**
 * Dispatch popover positioning by anchor mode. See `resolveAnchor` for how
 * the mode is chosen.
 */
const positionPopover = (anchor: Anchor, element: HTMLElement): Promise<void> => {
  if (anchor.mode === "inputBox") {
    return positionAboveInput(anchor.rect, element);
  }
  return positionAtCursor(anchor.rect, element);
};

/**
 * Position the popover so its bottom edge sits just above the caret. Uses
 * floating-ui's `flip` middleware to fall back to opening below the caret
 * when there is no room above (cursor near the top of the panel), and
 * `size` to clamp the inner list's max-height to the available viewport
 * space so the popover can never extend off-screen.
 */
const positionAtCursor = (cursorRect: DOMRect, element: HTMLElement): Promise<void> => {
  const virtualElement = { getBoundingClientRect: (): DOMRect => cursorRect };

  const scrollChild = element.firstElementChild;
  const contentMinWidth =
    scrollChild instanceof HTMLElement ? parseFloat(getComputedStyle(scrollChild).minWidth) || 0 : 0;
  element.style.width = `${Math.max(MIN_POPOVER_WIDTH, contentMinWidth)}px`;

  const heightCap = Math.min(window.innerHeight * POPOVER_MAX_HEIGHT_RATIO, POPOVER_MAX_HEIGHT_PX);

  return computePosition(virtualElement, element, {
    placement: "top-start",
    strategy: "fixed",
    middleware: [
      offset(POPOVER_VIEWPORT_MARGIN),
      flip({ padding: POPOVER_VIEWPORT_MARGIN }),
      shift({ padding: POPOVER_VIEWPORT_MARGIN }),
      size({
        padding: POPOVER_VIEWPORT_MARGIN,
        apply({ availableHeight }): void {
          if (!(scrollChild instanceof HTMLElement)) return;
          const maxHeight = Math.max(0, Math.min(heightCap, availableHeight));
          scrollChild.style.maxHeight = `${maxHeight}px`;
          // Clamp any CSS min-height that would override max-height (e.g. the
          // skill picker's detail-pane floor). Reset first so getComputedStyle
          // reflects the CSS rule, not the previous clamp.
          scrollChild.style.minHeight = "";
          const cssMinHeight = parseFloat(getComputedStyle(scrollChild).minHeight) || 0;
          if (cssMinHeight > maxHeight) {
            scrollChild.style.minHeight = `${maxHeight}px`;
          }
        },
      }),
    ],
  }).then(({ x, y, strategy }) => {
    element.style.position = strategy;
    element.style.left = `${x}px`;
    element.style.top = `${y}px`;
    element.style.bottom = "auto";
  });
};

/**
 * Position the popover centered horizontally above the prompt input, with its
 * bottom edge overlapping the top of the input by `POPOVER_INPUT_OVERLAP`
 * pixels. Width tracks the input (floored at 300px); height is capped at
 * `min(POPOVER_MAX_HEIGHT_RATIO · vh, POPOVER_MAX_HEIGHT_PX)` and then further
 * clamped so the popover fits in the space above the input. The popover
 * always opens upward — no flip.
 */
const positionAboveInput = (anchorRect: DOMRect, element: HTMLElement): Promise<void> => {
  const virtualElement = { getBoundingClientRect: (): DOMRect => anchorRect };

  const scrollChild = element.firstElementChild;

  // Bubble the inner list's computed min-width up to the outer wrapper so
  // floating-ui's shift() — which measures the outer element — can see the
  // true rendered width. Without this, inline `style.width` on the wrapper
  // is smaller than the visible content (the inner pane's min-width wins),
  // shift() sees no overflow, and the popover runs past the viewport edge.
  const contentMinWidth =
    scrollChild instanceof HTMLElement ? parseFloat(getComputedStyle(scrollChild).minWidth) || 0 : 0;
  const width = Math.max(MIN_POPOVER_WIDTH, anchorRect.width - POPOVER_INPUT_HORIZONTAL_INSET, contentMinWidth);
  element.style.width = `${width}px`;

  // Popover top = anchorRect.top - height + POPOVER_INPUT_OVERLAP. For the top
  // to stay below the reserved top margin, height ≤ anchorRect.top + overlap − margin.
  const availableAbove = anchorRect.top + POPOVER_INPUT_OVERLAP - getPopoverTopMargin(element);
  const maxHeight = Math.max(
    0,
    Math.min(window.innerHeight * POPOVER_MAX_HEIGHT_RATIO, POPOVER_MAX_HEIGHT_PX, availableAbove),
  );
  if (scrollChild instanceof HTMLElement) {
    scrollChild.style.maxHeight = `${maxHeight}px`;
    // Clamp any CSS-declared min-height (e.g. the detail-pane floor on the
    // skill picker) to the vertical budget. Without this, min-height would
    // override max-height and push the top edge above the viewport. Reset
    // the inline override first so getComputedStyle reflects the CSS rule,
    // not a previous clamp.
    scrollChild.style.minHeight = "";
    const cssMinHeight = parseFloat(getComputedStyle(scrollChild).minHeight) || 0;
    if (cssMinHeight > maxHeight) {
      scrollChild.style.minHeight = `${maxHeight}px`;
    }
  }

  return computePosition(virtualElement, element, {
    placement: "top",
    strategy: "fixed",
    middleware: [
      // Negative offset pulls the popover down into the input so it overlaps.
      offset(-POPOVER_INPUT_OVERLAP),
      // Keep the popover within the viewport along the main (horizontal) axis
      // so it doesn't run off the edge when the input sits near a screen
      // boundary or the popover is wider than the input's enclosing pane.
      shift({ padding: POPOVER_VIEWPORT_MARGIN }),
    ],
  }).then(({ x, strategy }) => {
    element.style.position = strategy;
    element.style.left = `${x}px`;
    // Anchor the bottom edge (not the top) so the popover grows upward when
    // its contents resize after mount — e.g. the skill picker swapping
    // detail-pane content on hover. Pinning `top` would keep the top edge
    // fixed and let the bottom edge extend into the input below.
    //
    // Floor the bottom at POPOVER_VIEWPORT_MARGIN so that if the input is
    // off-screen (scrolled out / partially visible), the popover still
    // stays anchored above the visible viewport edge — never flipping
    // downward or sliding below it.
    element.style.top = "auto";
    const bottomPx = Math.max(POPOVER_VIEWPORT_MARGIN, window.innerHeight - anchorRect.top - POPOVER_INPUT_OVERLAP);
    element.style.bottom = `${bottomPx}px`;
  });
};

/**
 * Creates a TipTap suggestion render lifecycle that anchors a popover to the
 * prompt input: centered horizontally over the input, sitting just above it.
 *
 * Shared by the @-mention (file), /-skill, and entity-mention suggestion features.
 */
export const renderSuggestion =
  (ListComponent: SuggestionListComponent, onSessionStart?: () => void) =>
  (): {
    onBeforeStart: (props: SuggestionProps) => void;
    onStart: (props: SuggestionProps) => void;
    onUpdate: (props: SuggestionProps) => void;
    onKeyDown: ({ event }: { event: KeyboardEvent }) => boolean;
    onExit: () => void;
  } => {
    let reactRenderer: ReactRenderer<SuggestionListRef, SuggestionProps> | undefined;
    let isActive = false;
    let lastEditorView: SuggestionProps["editor"]["view"] | undefined;
    // Trigger position of the current session, captured from the lifecycle
    // props. Used by closePopover() to dispatch a dismissal so the popover
    // does not reopen if the user later cursors back into the same range.
    let lastTriggerPos: number | undefined;
    // Caret-rect getter from the latest suggestion props. Re-evaluated on
    // every reposition so the cursor-anchored popover tracks the caret as
    // the user types or scrolls the editor.
    let lastClientRect: (() => DOMRect | null) | undefined;
    let contentResizeObserver: ResizeObserver | undefined;

    // Reposition the popover against the current anchor (input box or caret).
    // Used by onStart/onUpdate (prop-driven), the resize listener, and the
    // content resize observer.
    const reposition = (): void => {
      if (!reactRenderer || !lastEditorView || !lastClientRect) return;
      if (!(reactRenderer.element instanceof HTMLElement)) return;
      const anchor = resolveAnchor(lastEditorView.dom, lastClientRect);
      positionPopover(anchor, reactRenderer.element);
    };

    const handleResize = (): void => {
      if (!isActive) return;
      reposition();
    };

    // Observe the inner popover element's size. React renders the detail
    // pane asynchronously after mount (onActiveItemChange fires from a
    // useEffect), so the popover grows after the first positionPopover
    // call. Without this, the initial shift() math is done with the
    // pre-grown width and the post-grown popover runs off the viewport.
    const attachContentObserver = (): void => {
      if (!reactRenderer?.element) return;
      const scrollChild = reactRenderer.element.firstElementChild;
      if (!(scrollChild instanceof HTMLElement)) return;
      contentResizeObserver?.disconnect();
      contentResizeObserver = new ResizeObserver(() => {
        if (isActive) reposition();
      });
      contentResizeObserver.observe(scrollChild);
    };

    // Close the popover whenever the user presses the pointer down outside
    // its DOM. Capture phase so we still see the event even if a nested
    // bubble-phase handler stops propagation (e.g. the popover element's
    // own stopPropagation that shields it from Radix DismissableLayer).
    const handleDocumentPointerDown = (event: PointerEvent): void => {
      if (!isActive || !(reactRenderer?.element instanceof HTMLElement)) return;
      const target = event.target;
      if (target instanceof Node && reactRenderer.element.contains(target)) return;
      closePopover();
    };

    const closePopover = (): void => {
      // Record the trigger position as dismissed so that simply moving the
      // cursor back into the matched range doesn't reopen the popover. The
      // dismissal entry is auto-pruned by the plugin once the trigger char
      // is removed (e.g. after a successful insertion replaces it with a
      // chip) or when the user edits content at-or-after the trigger.
      if (lastEditorView !== undefined && lastTriggerPos !== undefined) {
        dismissTrigger(lastEditorView, lastTriggerPos);
      }

      // Gate the global count on the local flag so the second of paired
      // `closePopover` invocations (e.g. `handleDocumentPointerDown` racing
      // with `onExit`) doesn't double-decrement.
      if (isActive) {
        activeSuggestionPopoverCount -= 1;
      }
      isActive = false;
      reactRenderer?.destroy();
      reactRenderer?.element.remove();
      reactRenderer = undefined;
      lastEditorView = undefined;
      lastTriggerPos = undefined;
      lastClientRect = undefined;
      contentResizeObserver?.disconnect();
      contentResizeObserver = undefined;
      window.removeEventListener("resize", handleResize);
      document.removeEventListener("pointerdown", handleDocumentPointerDown, true);
    };

    return {
      // onBeforeStart fires immediately when the trigger character is typed,
      // before the items() fetch begins. Create the renderer but keep it
      // hidden — positioning is deferred to onStart so the popover measures
      // against the real item list, avoiding a visible placement jump.
      onBeforeStart: (props): void => {
        // Symmetric to the gate in `closePopover`: only count this session
        // once, even if `onBeforeStart` were ever to fire twice without an
        // intervening close.
        if (!isActive) {
          activeSuggestionPopoverCount += 1;
        }
        isActive = true;
        lastEditorView = props.editor.view;
        lastTriggerPos = props.range.from;
        lastClientRect = props.clientRect ?? undefined;
        onSessionStart?.();

        if (!props.clientRect) {
          return;
        }

        reactRenderer = new ReactRenderer(ListComponent, {
          props,
          editor: props.editor,
        });

        if (!(reactRenderer.element instanceof HTMLElement)) {
          return;
        }

        reactRenderer.element.style.position = "fixed";
        reactRenderer.element.style.visibility = "hidden";
        appendToBodyWithTheme(reactRenderer.element);
        // Keep the popover fitted when the viewport or enclosing pane
        // resizes while it's open (window resize, splitter drag, etc).
        window.addEventListener("resize", handleResize);
        document.addEventListener("pointerdown", handleDocumentPointerDown, true);
      },

      onStart: (props): void => {
        if (reactRenderer === undefined) {
          return;
        }
        lastClientRect = props.clientRect ?? undefined;
        reactRenderer.updateProps(props);
        if (reactRenderer.element instanceof HTMLElement && lastClientRect) {
          const anchor = resolveAnchor(props.editor.view.dom, lastClientRect);
          positionPopover(anchor, reactRenderer.element).then(() => {
            if (reactRenderer?.element instanceof HTMLElement) {
              reactRenderer.element.style.visibility = "";
            }
          });
          // Start observing AFTER the first position so we don't fight the
          // initial layout; subsequent content-driven size changes (e.g. the
          // skill picker's detail pane mounting asynchronously) will trigger
          // a reposition via the observer.
          attachContentObserver();
        }
      },

      onUpdate: (props): void => {
        if (!isActive || reactRenderer === undefined) {
          return;
        }
        // The trigger char position can shift mid-session if the user
        // types text *before* the trigger in the same textblock. Keep
        // lastTriggerPos in sync so a dismissal records the correct
        // current position.
        lastTriggerPos = props.range.from;
        lastClientRect = props.clientRect ?? lastClientRect;
        reactRenderer.updateProps(props);
        if (props.clientRect && reactRenderer.element instanceof HTMLElement) {
          const anchor = resolveAnchor(props.editor.view.dom, props.clientRect);
          positionPopover(anchor, reactRenderer.element);
        }
      },

      onKeyDown: ({ event }): boolean => {
        // Delegate to the list FIRST so it can pop one level for both Esc
        // and Shift+Tab. Only close on Escape when the list reports it has
        // nothing to pop (returns false). Without this short-circuit, our
        // step-back contract would never fire — Esc would always close.
        const didHandle = reactRenderer?.ref?.onKeyDown({ event }) ?? false;
        if (didHandle) return true;
        if (event.key === "Escape") {
          closePopover();
          return true;
        }
        return false;
      },

      onExit: (): void => {
        closePopover();
      },
    };
  };

const MAX_RESULTS = 200;

const entryToSuggestionItem = (path: string, isDirectory: boolean): SuggestionItem => {
  const lastSlash = path.lastIndexOf("/");
  const name = lastSlash === -1 ? path : path.slice(lastSlash + 1);
  const parentPath = lastSlash === -1 ? "" : path.slice(0, lastSlash + 1);
  // Directories get a trailing "/" in both id and label so they're distinguishable
  const suffix = isDirectory ? "/" : "";
  return new SuggestionItem(`@${path}${suffix}`, name + suffix, parentPath);
};

/**
 * Queries starting with `~`, `/`, or `.` are "path mode" — they address
 * the backend filesystem directly (e.g. `@~/.claude/`, `@./.env`, `@.git`),
 * bypassing the workspace's `git ls-files` cache. `.`-relative queries are
 * resolved against the workspace working directory.
 */
const isPathModeQuery = (query: string): boolean =>
  query.startsWith("~") || query.startsWith("/") || query.startsWith(".");

/**
 * Split a path-mode query into the directory to list and a filter prefix.
 * "~" and "~/" → list home, no filter. "~/.cla" → list "~/", filter ".cla".
 * "/usr/l" → list "/usr/", filter "l". "." or "./" → list workspace root.
 * ".git" → list workspace root, filter ".git". "./src/comp" → list "./src/", filter "comp".
 */
const parsePathQuery = (query: string): { directory: string; filter: string } => {
  if (query === "~") {
    return { directory: "~/", filter: "" };
  }

  if (query === "." || query === "./") {
    return { directory: "./", filter: "" };
  }
  const lastSlash = query.lastIndexOf("/");
  if (lastSlash === -1) {
    if (query.startsWith(".")) {
      // e.g. ".git", ".env" — list workspace root filtered for that name
      return { directory: "./", filter: query };
    }
    // e.g. "~foo" — not really valid, but treat the part after "~" as a filter in home.
    return { directory: "~/", filter: query.slice(1) };
  }
  return { directory: query.slice(0, lastSlash + 1), filter: query.slice(lastSlash + 1) };
};

/** A directory entry parsed from the `getFilesAndFolders` string response. */
type DirEntry = { name: string; isDirectory: boolean };

/** Parse a `getFilesAndFolders` string (dirs have trailing "/"). */
const parseDirEntry = (raw: string): DirEntry =>
  raw.endsWith("/") ? { name: raw.slice(0, -1), isDirectory: true } : { name: raw, isDirectory: false };

const filterFilesystemEntries = (entries: Array<DirEntry>, filter: string): Array<DirEntry> => {
  if (!filter) return entries;
  // Score against the entry name (with trailing "/" for dirs) for terminal-like ranking.
  const scored = entries
    .map((e) => ({
      entry: e,
      score: scoreFilePath(filter, e.isDirectory ? `${e.name}/` : e.name),
    }))
    .filter(({ score }) => score > 0);
  scored.sort((a, b) => b.score - a.score);
  return scored.map(({ entry }) => entry);
};

/**
 * Given a path-mode directory like "./sculptor/agent_docs/", return its
 * parent ("./sculptor/"). Returns null for the three path-mode roots
 * (`./`, `~/`, `/`) since there's nowhere further up to go.
 */
const parentDirectory = (directory: string): string | null => {
  if (directory === "./" || directory === "~/" || directory === "/") {
    return null;
  }
  const withoutTrailingSlash = directory.slice(0, -1);
  const lastSlash = withoutTrailingSlash.lastIndexOf("/");
  if (lastSlash === -1) {
    return null;
  }
  return directory.slice(0, lastSlash + 1);
};

/**
 * Step-back handler for path-mode queries: rewrites the suggestion query
 * to the parent directory, keeping the active trigger char so the popover
 * stays open and re-queries one level up. No-op for fuzzy-mode queries or
 * when we're already at a path-mode root.
 *
 * `triggerChar` defaults to `@` because that's the file picker's native
 * trigger; the plus-prefilter picker passes `+` so the outer session char
 * is preserved in the editor.
 */
export const navigateUpPathMode = (props: SuggestionProps, triggerChar = "@"): boolean => {
  if (!isPathModeQuery(props.query)) {
    return false;
  }
  const { directory } = parsePathQuery(props.query);
  const parent = parentDirectory(directory);
  if (parent === null) {
    return false;
  }
  props.editor
    .chain()
    .focus()
    .deleteRange(props.range)
    .insertContentAt(props.range.from, triggerChar + parent)
    .run();
  return true;
};

/**
 * Creates a TipTap suggestion configuration for @-mentioning files.
 *
 * Searches the full workspace file list with a fuzzy scorer:
 * consecutive-match bonuses, word-boundary bonuses, filename bias, and
 * compactness scoring. The file list is read from the TanStack Query cache
 * populated by `useWorkspaceFiles` (pre-warmed in WorkspacePageContent). If
 * the cache is empty when the user types @, a one-off fetch is performed.
 *
 * `triggerChar` controls which character anchors the suggestion session in
 * the editor text. Defaults to `@`. The plus-prefilter picker passes `+`
 * so folder-drill rewrites (e.g. `@./foo/` → `@./foo/bar/`) keep the outer
 * `+` session alive instead of swapping triggers mid-flow.
 */
export const createFileSuggestion = (
  projectID: string,
  workspaceID: string,
  { triggerChar = "@" }: { triggerChar?: string } = {},
): Omit<SuggestionOptions, "editor"> => {
  // Per-session cache of directory listings so navigating back into a folder
  // doesn't re-hit the backend. Cleared on each new '@' via onSessionStart.
  const dirCache = new Map<string, Promise<Array<DirEntry>>>();
  const resetDirCache = (): void => {
    dirCache.clear();
  };

  const fetchDirectoryContents = (directory: string): Promise<Array<DirEntry>> => {
    const cached = dirCache.get(directory);
    if (cached !== undefined) {
      return cached;
    }
    const promise = getFilesAndFolders({
      path: { project_id: projectID },
      query: { directory, workspace_id: workspaceID },
      meta: { skipWsAck: true },
    })
      .then(({ data }) => (data ?? []).map(parseDirEntry))
      .catch((error: unknown) => {
        console.error("Error listing directory contents for @-mention:", error);
        dirCache.delete(directory);
        return [];
      });
    dirCache.set(directory, promise);
    return promise;
  };

  const pluginKey = new PluginKey("fileMention");
  return {
    pluginKey,
    char: "@",
    allow: ({ state, range }): boolean => {
      const $from = state.doc.resolve(range.from);
      if ($from.parent.type.name === "codeBlock") {
        return false;
      }
      const codeMark = state.schema.marks.code;
      if (codeMark && state.doc.rangeHasMark(range.from, range.from + 1, codeMark)) {
        return false;
      }

      if (isPositionDismissed(state, range.from)) {
        return false;
      }
      return true;
    },
    // Don't reopen on a pure cursor move into an existing `@path` (SCU-1298).
    shouldShow: showSuggestionOnlyWhenTyping(pluginKey),
    items: async ({ query }): Promise<Array<SuggestionItem>> => {
      // Path mode: queries starting with "~" or "/" reference the host
      // filesystem directly, bypassing the workspace file cache.
      if (isPathModeQuery(query)) {
        const { directory, filter } = parsePathQuery(query);
        const entries = await fetchDirectoryContents(directory);
        return filterFilesystemEntries(entries, filter)
          .slice(0, MAX_RESULTS)
          .map((e) => {
            const suffix = e.isDirectory ? "/" : "";
            return new SuggestionItem(`@${directory}${e.name}${suffix}`, e.name + suffix, directory);
          });
      }

      // Reads from the TanStack Query cache populated by `useWorkspaceFiles`
      // pre-warm in WorkspacePage; falls back to a fetch (and caches) if no
      // observer has primed it yet.
      let fileEntries: ReadonlyArray<{ path: string; type: "file" | "directory" }>;
      try {
        fileEntries = await ensureWorkspaceFiles(workspaceID);
      } catch (error: unknown) {
        console.error("Error fetching workspace files for @-mention:", error);
        return [];
      }

      if (!query) {
        // Empty query: show first N entries alphabetically as a starting point
        return fileEntries.slice(0, MAX_RESULTS).map((f) => entryToSuggestionItem(f.path, f.type === "directory"));
      }

      const allPaths = fileEntries.map((f) => f.path);
      const dirPaths = new Set(fileEntries.filter((f) => f.type === "directory").map((f) => f.path));

      return fuzzySearchFiles(query, allPaths).map(({ path }) => entryToSuggestionItem(path, dirPaths.has(path)));
    },

    command: ({ editor, range, props: item }): void => {
      const action: SuggestionAction = (item as SuggestionItem & { action?: SuggestionAction }).action ?? "select";
      const isFolder = item.label.endsWith("/");
      const isPathMode = item.id.startsWith("@~") || item.id.startsWith("@/") || item.id.startsWith("@./");

      // Tab on a folder drills into it; Enter/click always commits the item
      // as a mention. Fuzzy-mode folders drilled via Tab switch to `./`
      // path mode so the search narrows to that directory's contents on
      // disk (including `.gitignore`'d files the fuzzy corpus hides).
      if (isFolder && action === "drillIn") {
        const rawPath = item.id.slice(1); // strip leading '@'
        const nextQuery = isPathMode ? rawPath : `./${rawPath}`;
        editor
          .chain()
          .focus()
          .deleteRange(range)
          .insertContentAt(range.from, triggerChar + nextQuery)
          .run();
        return;
      }

      editor
        .chain()
        .focus()
        .deleteRange(range)
        .insertContent([
          { type: "mention", attrs: { id: item.id, label: item.label, mentionSuggestionChar: "@" } },
          { type: "text", text: " " },
        ])
        .run();
    },

    render: renderSuggestion(MentionList, resetDirCache),
  };
};
