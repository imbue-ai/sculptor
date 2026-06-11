import { IconButton, Spinner, Tooltip } from "@radix-ui/themes";
import { Command } from "cmdk";
import { useAtom, useAtomValue } from "jotai";
import { ChevronRightIcon, SearchIcon, XIcon } from "lucide-react";
import type { KeyboardEvent, ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ElementIds } from "../../api";
import { keybindingsMapAtom } from "../../common/keybindings/atoms.ts";
import { formatShortcutForDisplay, shouldHandleKeybinding } from "../../common/ShortcutUtils.ts";
import { PaletteDialog } from "../PaletteDialog";
import { commandPaletteOpenAtom, commandPalettePendingAtom, commandPaletteSearchAtom } from "./atoms.ts";
import styles from "./CommandPalette.module.scss";
import { buildItemValue, makePaletteFilter, ROW_VALUE_SEP } from "./filter.ts";
import { groupCommands } from "./groupCommands.ts";
import { groupHeading } from "./groups.ts";
import {
  useCommandPalette,
  usePaletteContext,
  useResetOnOpenChange,
  useRunCommand,
  useVisibleCommands,
} from "./hooks.ts";
import { PAGE_DEFINITIONS } from "./pages.ts";
import type { Command as PaletteCommand, CommandGroupId, PaletteContext } from "./types.ts";
import { isPageScoped, pagesOf } from "./types.ts";

// Show the row's "kind" label (group heading) only when the user is
// actively searching: cmdk re-orders rows by score during a search, so the
// group headers visually drift away from the items they belong to. With
// no query, the group heading is right above the row and a duplicate
// label would just be noise.
const kindLabelForRow = (groupId: CommandGroupId, isSearching: boolean): string => {
  if (!isSearching) return "";
  return groupHeading(groupId);
};

// Keys cmdk owns inside its own input handler — Enter, arrows, Escape,
// Tab, Backspace. We skip these in the window-level shortcut listener so
// in-palette navigation isn't intercepted as a command shortcut.
const CMDK_KEYS = new Set(["Enter", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Escape", "Tab", "Backspace"]);

/**
 * Render a keybinding hint as a single <kbd> with the platform-formatted
 * display string. We deliberately do NOT split into per-character <kbd>s:
 * the Mac modifier glyphs (⌘ ⇧ ⌥ ⌃) only render legibly when the system
 * font can lay them out as a single text run with kerning / ligature
 * lookups in play. Splitting per-character broke that, especially for
 * thin glyphs like ⇧ which then looked like a ghost. Same approach as
 * the chat input's `<KeyboardHint>`.
 */
const ShortcutHint = ({ binding }: { binding: string }): ReactElement => {
  const display = formatShortcutForDisplay(binding);
  if (!display) return <></>;
  return (
    <kbd className={styles.itemShortcut} aria-label={`Shortcut: ${display}`}>
      {display}
    </kbd>
  );
};

const PaletteRow = ({
  command,
  isSearching,
  ctx,
  binding,
  onSelect,
}: {
  command: PaletteCommand;
  isSearching: boolean;
  ctx: PaletteContext;
  // Pre-resolved keybinding string (or null when the command has no
  // shortcut, or the user has unbound it). The parent owns the single
  // `keybindingsMap` subscription — passing this in per-row keeps cmdk
  // from re-subscribing once per visible row.
  binding: string | null;
  onSelect: (cmd: PaletteCommand) => void;
}): ReactElement => {
  // Display-only: dynamic getters take precedence over the static fields.
  // Note we still use `command.title` (the stable value) for `buildItemValue`
  // below — that keeps fuzzy-search ranking on a stable haystack.
  const Icon = command.getIcon?.(ctx) ?? command.icon;
  const displayTitle = command.getTitle?.(ctx) ?? command.title;
  const displaySubtitle = command.getSubtitle?.(ctx) ?? command.subtitle;
  const pending = useAtomValue(commandPalettePendingAtom);
  const isPending = pending === command.id;
  const kind = kindLabelForRow(command.group, isSearching);

  const item = (
    <Command.Item
      // IMPORTANT: pass the stable `command.title` (not the dynamic display
      // label) so the user types a stable mental model — fuzzy ranking does
      // not chase live UI state.
      value={buildItemValue(command)}
      keywords={command.keywords}
      onSelect={() => onSelect(command)}
      // Disabled rows render greyed-out (via the cmdk-set
      // `data-disabled` attribute, see CommandPalette.module.scss) and
      // cmdk skips onSelect for them.
      disabled={command.disabled}
      className={styles.item}
      data-testid={ElementIds.COMMAND_PALETTE_ITEM}
      data-command-id={command.id}
      aria-busy={isPending}
    >
      <div className={styles.itemIcon}>{Icon ? <Icon size={16} /> : <SearchIcon size={16} />}</div>
      <div className={styles.itemBody}>
        <span className={styles.itemTitle}>{displayTitle}</span>
        {displaySubtitle ? <span className={styles.itemSubtitle}>{displaySubtitle}</span> : null}
      </div>
      {/* Trailing slot is fixed-min-width so swapping spinner <-> shortcut
          / kind label doesn't cause a layout shift. Shortcut hint takes
          priority over the kind label — if a row has a binding, the
          binding is the most useful piece of context. */}
      <div className={styles.itemTrailing} aria-hidden={!isPending}>
        {isPending ? (
          <Spinner size="1" />
        ) : (
          <>
            {binding ? (
              <ShortcutHint binding={binding} />
            ) : kind ? (
              <span className={styles.itemKind}>{kind}</span>
            ) : null}
            {command.pageId || command.showChevron ? (
              <span className={styles.itemChevron} aria-hidden>
                <ChevronRightIcon size={14} />
              </span>
            ) : null}
          </>
        )}
      </div>
    </Command.Item>
  );

  // Tooltip explains why a disabled row is greyed-out. Skipped when the
  // command is enabled, or when no reason was supplied (e.g. agents.switch
  // already explains "Only one agent in this workspace" via its subtitle —
  // a tooltip would just duplicate it).
  //
  // The `disabledTooltip` className lifts the portal-rendered tooltip
  // above the palette Dialog's z-index — without it the tooltip renders
  // behind the dialog content and is never visible. See module.scss.
  if (command.disabled && command.disabledReason) {
    return (
      <Tooltip content={command.disabledReason} side="left" className={styles.disabledTooltip}>
        {item}
      </Tooltip>
    );
  }
  return item;
};

export const CommandPalette = (): ReactElement => {
  const [isOpen, setIsOpen] = useAtom(commandPaletteOpenAtom);
  const [search, setSearch] = useAtom(commandPaletteSearchAtom);
  const pendingCommandId = useAtomValue(commandPalettePendingAtom);

  const { close, popPage, pushPage } = useCommandPalette();
  const ctx = usePaletteContext();
  const allCommands = useVisibleCommands(ctx);
  const runCommand = useRunCommand();

  useResetOnOpenChange();

  const hasQuery = search.trim().length > 0;

  // Pre-compute predicate flags over the visible-set so the filter
  // closure is O(1) Set/Map gets per row instead of three
  // `commandsById.get(id)` indirections. Memoized on `allCommands` so
  // identity is stable across keystrokes — only the user navigating or
  // the registry changing rebuilds them.
  const pageScopedIds = useMemo(() => {
    const s = new Set<string>();
    for (const cmd of allCommands) if (isPageScoped(cmd)) s.add(cmd.id);
    return s;
  }, [allCommands]);
  const primaryIds = useMemo(() => {
    const s = new Set<string>();
    for (const cmd of allCommands) if (cmd.primary === true) s.add(cmd.id);
    return s;
  }, [allCommands]);
  const boostById = useMemo(() => {
    const m = new Map<string, number>();
    for (const cmd of allCommands) {
      // Any positive multiplier other than 1 is a real adjustment —
      // > 1 boosts (e.g. panel toggles), < 1 demotes (e.g. settings
      // sub-page rows). 0 would zero out the score and hide the row,
      // which is `when`'s job, not a boost's.
      if (cmd.boost != null && cmd.boost > 0 && cmd.boost !== 1) m.set(cmd.id, cmd.boost);
    }
    return m;
  }, [allCommands]);

  // Page-aware filter: penalizes page-scoped commands at the root so
  // top-level matches always rank above sub-page matches; boosts commands
  // marked `primary` so page-openers like the workspace switcher and the
  // settings opener rank highest within their tier. Rebuilt only when the
  // visible command set changes or the user navigates between root and a
  // sub-page.
  const filter = useMemo(
    () =>
      makePaletteFilter({
        isPageScoped: (id) => pageScopedIds.has(id),
        isPrimary: (id) => primaryIds.has(id),
        getBoost: (id) => boostById.get(id),
        isAtRoot: ctx.page == null,
      }),
    [pageScopedIds, primaryIds, boostById, ctx.page],
  );

  // Single per-keystroke score map: cmdk re-runs `filter` per row for
  // ranking, and the page-opener-hiding logic below also needs a score
  // per command. Computing once and reading via `.get(id)` removes the
  // duplicate string-matching pass we used to do in `visibleCommands`,
  // and lets `groupCommands`' `scoreOf` callback share the same numbers.
  const scoreOfRow = useMemo(() => {
    const m = new Map<string, number>();
    if (!hasQuery) return m;
    for (const cmd of allCommands) {
      m.set(cmd.id, filter(buildItemValue(cmd), search, cmd.keywords));
    }
    return m;
  }, [allCommands, filter, search, hasQuery]);

  // During search at root, hide page-opener entries (those with `pageId`)
  // when at least one of their sub-page items is also matching. Without
  // this, typing "delete" surfaces both "Workspace actions..." and
  // "Delete workspace: …" — the page-opener is redundant noise once the
  // user can see the action they actually want directly. Page-openers
  // are still shown when no child of theirs is matching, because that's
  // the only way to surface the sub-page in that case.
  const visibleCommands = useMemo<Array<PaletteCommand>>(() => {
    if (!hasQuery || ctx.page != null) return allCommands;
    const pagesWithMatchingChild = new Set<string>();
    for (const cmd of allCommands) {
      const pages = pagesOf(cmd);
      if (pages == null) continue;
      const score = scoreOfRow.get(cmd.id) ?? 0;
      if (score === 0) continue;
      for (const p of pages) pagesWithMatchingChild.add(p);
    }
    if (pagesWithMatchingChild.size === 0) return allCommands;
    return allCommands.filter((cmd) => cmd.pageId == null || !pagesWithMatchingChild.has(cmd.pageId));
  }, [hasQuery, ctx.page, allCommands, scoreOfRow]);

  // During search, sort groups by their best command score so a
  // high-confidence match (e.g. typing "dark" → exact-title hit on
  // "Dark") trumps the static group order. Without this, the Theme
  // group would still render below Workspaces just because Workspaces
  // has a lower `groupOrder`. Computed via the same filter cmdk uses,
  // so the per-row score and the per-group score never disagree.
  const grouped = useMemo(() => {
    const scoreOf = hasQuery ? (cmd: PaletteCommand): number => scoreOfRow.get(cmd.id) ?? 0 : undefined;
    return groupCommands(visibleCommands, hasQuery, scoreOf);
  }, [visibleCommands, hasQuery, scoreOfRow]);

  // cmdk drives the active row via its own `value` state; we mirror it
  // here so Cmd+Enter (keepOpen) and Tab (push sub-page) can resolve the
  // active command without querying the DOM. cmdk's value is
  // `<title>__<id>` (per buildItemValue).
  const [activeValue, setActiveValue] = useState<string>("");

  // Clear the mirrored value on the falling edge of `isOpen`. The CommandPalette
  // host doesn't unmount between opens (only Dialog.Content does), so without
  // this `activeValue` would carry over from the previous session and cmdk
  // would re-select that row on the next open instead of auto-selecting the
  // first row. Resetting on close means the very first paint of the next open
  // sees an empty value and cmdk picks the top row — no flicker.
  useEffect(() => {
    if (!isOpen) setActiveValue("");
  }, [isOpen]);

  // Ref on Command.Input so we can pull focus back to it after a
  // `keepOpen` command finishes. The pending atom tracks in-flight runs;
  // see the effect below the listRef setup for why this is here and not
  // in `useRunCommand`.
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Ref on Command.List so we can imperatively scroll it back to the top
  // on every open. cmdk's internal `scrollIntoView` (called when its
  // selected value changes) can leave the list scrolled into the middle
  // after the user runs a command from a long list — reopening should
  // always start at the top.
  const listRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!isOpen) return;
    // Why rAF: cmdk's auto-selection of the first row on open queues a
    // `scrollIntoView` from a child effect AFTER our parent effect runs
    // (cmdk's selection effect is value-change-driven, so it fires from
    // a follow-up render). A synchronous scroll-reset here loses that
    // race — the auto-selected row's `scrollIntoView` then re-scrolls
    // the list mid-list. Deferring to the next frame lets cmdk's
    // selection settle first; our reset wins. This is the
    // "post-paint coalescing" exception in docs/development/review/react.md
    // (`no_raf_as_timing_hack`), not a generic "wait for DOM" hack.
    const handle = requestAnimationFrame(() => {
      if (listRef.current) listRef.current.scrollTop = 0;
    });
    return (): void => cancelAnimationFrame(handle);
  }, [isOpen]);

  // Pull focus back to the palette input after a `keepOpen` command
  // finishes. The command's `perform` may have triggered a panel that
  // auto-focuses on mount (e.g. xterm in the terminal panel) — without
  // this, the next keystroke gets routed to the panel even though the
  // palette is still on screen. Watching the pending atom transition
  // keeps the focus restoration on React's render cycle (deeper
  // sibling-tree mount effects commit before the palette's effect),
  // and using a ref on `Command.Input` avoids reaching into the DOM
  // by data-testid from `useRunCommand`.
  const prevPendingRef = useRef<string | null>(null);
  useEffect(() => {
    const didJustFinish = prevPendingRef.current != null && pendingCommandId == null;
    prevPendingRef.current = pendingCommandId;
    if (didJustFinish && isOpen) {
      inputRef.current?.focus();
    }
  }, [pendingCommandId, isOpen]);

  // We disable cmdk's per-item pointer selection (see `disablePointerSelection`
  // below) and roll our own at the list level so we can swallow the FIRST
  // pointermove that fires after open. Without this gate, opening the
  // palette under a stationary cursor was fine — but a cursor that is
  // mid-motion when Cmd+K fires would land on whatever row the pointer
  // happens to be over, overriding the auto-selected first row. The user
  // expects the keyboard-selected row to stay put until they actually
  // move the cursor.
  const hasCursorMovedRef = useRef(false);
  useEffect(() => {
    if (isOpen) hasCursorMovedRef.current = false;
  }, [isOpen]);

  const activeCommand = useMemo(() => {
    if (!activeValue) return null;
    const id = activeValue.split(ROW_VALUE_SEP)[1];
    if (!id) return null;
    return allCommands.find((c) => c.id === id) ?? null;
  }, [activeValue, allCommands]);

  const onSelect = useCallback(
    (cmd: PaletteCommand) => {
      void runCommand(cmd);
    },
    [runCommand],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>) => {
      // Backspace on empty input pops a sub-page (only when we have one).
      if (e.key === "Backspace" && search === "" && ctx.page != null) {
        e.preventDefault();
        popPage();
        return;
      }

      // Cmd/Ctrl+Enter: run with keepOpen. We always preventDefault +
      // stopPropagation so cmdk's own Enter handler doesn't ALSO invoke
      // the row's onSelect (which would run the command twice — once
      // without keepOpen, once with). Even if we have no activeCommand,
      // suppress so a stray Enter doesn't fire the wrong row.
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        e.stopPropagation();
        if (activeCommand != null) {
          void runCommand(activeCommand, { keepOpen: true });
        }
        return;
      }

      // Tab enters the active row's sub-page (if it has one) or runs a
      // `showChevron` command (chevron-marked commands without a page —
      // e.g. New workspace, which opens a modal). Shift+Tab exits the
      // current sub-page back to its parent. We always swallow Tab so
      // Radix Dialog's focus trap never sees it and tries to shift focus
      // out of the input.
      if (e.key === "Tab") {
        e.preventDefault();
        e.stopPropagation();
        if (e.shiftKey) {
          if (ctx.page != null) popPage();
          return;
        }

        if (activeCommand?.pageId != null) {
          pushPage(activeCommand.pageId);
        } else if (activeCommand?.showChevron) {
          void runCommand(activeCommand);
        }
        return;
      }

      // ArrowRight/ArrowLeft mirror Tab/Shift+Tab for sub-page navigation,
      // but only when the input's caret is at the relevant edge — so
      // mid-word text-cursor movement still works. Any modifier (Shift,
      // Cmd, Ctrl, Alt) means it's a text-edit gesture (extend selection,
      // jump to line edge, etc.) — don't hijack those.
      const hasNoModifier = !e.shiftKey && !e.metaKey && !e.ctrlKey && !e.altKey;
      if (hasNoModifier && (e.key === "ArrowRight" || e.key === "ArrowLeft")) {
        const target = e.target instanceof HTMLInputElement ? e.target : null;
        const isCaretAtEnd = target == null || target.selectionStart === target.value.length;
        const isCaretAtStart = target == null || target.selectionEnd === 0;

        if (e.key === "ArrowRight" && isCaretAtEnd) {
          if (activeCommand?.pageId != null) {
            e.preventDefault();
            e.stopPropagation();
            pushPage(activeCommand.pageId);
            return;
          }

          if (activeCommand?.showChevron) {
            e.preventDefault();
            e.stopPropagation();
            void runCommand(activeCommand);
            return;
          }
        }

        if (e.key === "ArrowLeft" && isCaretAtStart && ctx.page != null) {
          e.preventDefault();
          e.stopPropagation();
          popPage();
          return;
        }
      }
    },
    [search, ctx.page, popPage, pushPage, activeCommand, runCommand],
  );

  // Escape / outside-click / Radix close requests. Behavior:
  //  - On open request, just open.
  //  - If we're on a sub-page, pop it instead of closing (so Esc/click-out
  //    walks back up the page stack).
  //  - If a command is currently in flight (async perform), refuse to close
  //    so the user doesn't accidentally cancel a pending action by clicking
  //    outside the dialog. They can still hit Esc twice or wait for the
  //    spinner.
  const handleOpenChange = useCallback(
    (next: boolean) => {
      if (next) {
        setIsOpen(true);
        return;
      }

      if (pendingCommandId != null) {
        return;
      }

      if (ctx.page != null) {
        popPage();
        return;
      }
      close();
    },
    [setIsOpen, pendingCommandId, ctx.page, popPage, close],
  );

  // While the palette is open, capture window-level keydowns and check
  // them against every visible command's `shortcut`. A match closes the
  // palette and runs the command — so `Cmd+T` (toggle theme) fires its
  // command directly, instead of being swallowed by the overlay
  // suppression in `usePageLayoutKeyboardShortcuts`.
  //
  // We use the capture phase so we run BEFORE that suppression handler
  // (which is registered on `window` in bubble phase). cmdk's own input
  // handlers (Enter, Arrow*, Escape, Tab, Backspace) are skipped first so
  // navigation inside the palette still works.
  const keybindingsMap = useAtomValue(keybindingsMapAtom);
  useEffect(() => {
    if (!isOpen) return;
    const listener = (e: globalThis.KeyboardEvent): void => {
      if (CMDK_KEYS.has(e.key)) return;
      // Only consider events with at least one modifier — every command
      // shortcut in the registry uses one. This avoids "user pressed t in
      // the input" matching a `t`-only shortcut and dismissing the palette.
      if (!e.metaKey && !e.ctrlKey && !e.altKey) return;
      for (const cmd of allCommands) {
        if (cmd.shortcut == null) continue;
        if (cmd.disabled) continue;
        const binding = keybindingsMap[cmd.shortcut]?.binding;
        if (binding == null) continue;
        if (shouldHandleKeybinding(e, binding)) {
          e.preventDefault();
          e.stopPropagation();
          void runCommand(cmd);
          return;
        }
      }
    };
    window.addEventListener("keydown", listener, { capture: true });
    return (): void => window.removeEventListener("keydown", listener, { capture: true });
  }, [isOpen, allCommands, keybindingsMap, runCommand]);

  const pageDef = ctx.page != null ? PAGE_DEFINITIONS[ctx.page] : null;
  const placeholder = pageDef?.placeholder ?? "Type a command or search...";

  // Total registered command count, for the empty-state copy. cmdk hides
  // individual rows that don't match — we trust its filter and
  // `Command.Empty` for the "no matches" UI.
  const totalItems = useMemo(() => grouped.reduce((acc, g) => acc + g.commands.length, 0), [grouped]);

  // Reset list scroll on every search change. cmdk auto-scrolls the
  // selected item into view, which on long filtered lists (e.g. typing
  // "settings" with all 12 settings sections matching) can land mid-
  // list and the top result drops off-screen. The user wants the list
  // to anchor at the top while they're still typing — they can arrow
  // down once they see what they want.
  //
  // Same rAF rationale as the open-reset above: cmdk's scheduler-driven
  // `scrollIntoView` fires from a follow-up render after a search-
  // triggered value change, AFTER our parent useEffect runs. A
  // synchronous reset here loses that race and cmdk wins, leaving the
  // list scrolled past the top-scored row (e.g. typing "set" hides
  // "Open settings" behind the auto-selected row's scrollIntoView).
  // Deferring to the next frame lets cmdk's selection settle first;
  // our reset wins.
  const prevSearchRef = useRef(search);
  useEffect(() => {
    if (search === prevSearchRef.current) return;
    prevSearchRef.current = search;
    const handle = requestAnimationFrame(() => {
      if (listRef.current) listRef.current.scrollTop = 0;
    });
    return (): void => cancelAnimationFrame(handle);
  }, [search]);

  return (
    <PaletteDialog
      open={isOpen}
      onOpenChange={handleOpenChange}
      title="Command palette"
      contentTestId={ElementIds.COMMAND_PALETTE}
      overlayClassName={pendingCommandId != null ? styles.overlayPending : undefined}
      // Use capture phase so we intercept Cmd+Enter and Backspace
      // BEFORE cmdk's own input handler runs (which would otherwise
      // fire onSelect a second time on Cmd+Enter or fall through on
      // Backspace).
      onKeyDownCapture={handleKeyDown}
      // Two-stage Escape: when the search input has text, the FIRST
      // Esc clears the input (preventDefault stops Radix from closing
      // the dialog). A second Esc — or the first one with an empty
      // input — falls through to Radix and triggers `handleOpenChange`,
      // which pops a sub-page or closes.
      //
      // Read the live DOM value via `inputRef` rather than the `search`
      // state: a user (or test) who clears the input then immediately
      // presses Escape can fire the keydown before React commits the
      // `setSearch("")` update, leaving this closure with stale text
      // and stranding the dialog open. The DOM value is updated
      // synchronously by the input event, so it's always current.
      onEscapeKeyDown={(e): void => {
        if (inputRef.current != null && inputRef.current.value !== "") {
          e.preventDefault();
          setSearch("");
        }
      }}
    >
      <Command
        label="Sculptor command palette"
        className={styles.command}
        filter={filter}
        loop
        // Let cmdk auto-select the first row on mount and the top-
        // scoring row on every search change — so Enter works the
        // moment the palette opens, with no priming arrow-key needed.
        value={activeValue}
        onValueChange={setActiveValue}
        // We disable cmdk's per-item pointer selection and re-implement
        // it on Command.List below. This lets us swallow the very first
        // pointermove after open so a cursor that happens to be sitting
        // on (or moving across) a row when Cmd+K fires doesn't override
        // the keyboard-selected first row. Click selection is unaffected
        // — cmdk's per-item onClick handler doesn't read this flag.
        disablePointerSelection
      >
        <div className={styles.header}>
          {pageDef ? (
            <div className={styles.breadcrumb} data-testid={ElementIds.COMMAND_PALETTE_PAGE_BREADCRUMB}>
              <span>{pageDef.title}</span>
              <IconButton
                variant="ghost"
                size="1"
                color="gray"
                className={styles.breadcrumbClose}
                onClick={() => popPage()}
                aria-label="Back"
              >
                <XIcon size={10} />
              </IconButton>
            </div>
          ) : null}
          <Command.Input
            ref={inputRef}
            value={search}
            onValueChange={setSearch}
            placeholder={placeholder}
            className={styles.input}
            autoFocus
            data-testid={ElementIds.COMMAND_PALETTE_INPUT}
          />
        </div>
        <div className={styles.divider} aria-hidden />
        <Command.List
          ref={listRef}
          className={styles.list}
          data-testid={ElementIds.COMMAND_PALETTE_LIST}
          // Custom pointer selection (cmdk's own is disabled above).
          // We swallow the first pointermove after open — the cursor
          // may have been mid-motion when Cmd+K fired, and we don't
          // want that to override the auto-selected first row. Once
          // the user has actually moved the cursor, subsequent moves
          // grab whatever row is under it (matching cmdk's default).
          onPointerMove={(e): void => {
            if (!hasCursorMovedRef.current) {
              hasCursorMovedRef.current = true;
              return;
            }
            const item = (e.target as HTMLElement | null)?.closest("[cmdk-item]");
            if (!item) return;
            if (item.getAttribute("aria-disabled") === "true") return;
            const value = item.getAttribute("data-value");
            if (value) setActiveValue(value);
          }}
        >
          <Command.Empty className={styles.empty} data-testid={ElementIds.COMMAND_PALETTE_EMPTY}>
            {totalItems === 0 ? "No commands here." : `No matches for "${search}"`}
          </Command.Empty>
          {grouped.map((g) => (
            // Include `hasQuery` in the key so the group remounts when the
            // user transitions between searching and not. cmdk's internal
            // `z()` physically reorders DOM nodes via `appendChild` to sort
            // by score on every search change, but it early-returns when
            // search is empty — so without a remount, the score-sorted DOM
            // positions from the prior search persist and the empty-query
            // list shows up in the wrong order.
            <Command.Group
              key={`${hasQuery ? "q" : "r"}.${g.id}`}
              heading={groupHeading(g.id)}
              className={styles.group}
              data-testid={ElementIds.COMMAND_PALETTE_GROUP}
              data-group-id={g.id}
            >
              {g.commands.map((cmd) => (
                <PaletteRow
                  key={`${g.id}.${cmd.id}`}
                  command={cmd}
                  isSearching={hasQuery}
                  ctx={ctx}
                  binding={cmd.shortcut != null ? (keybindingsMap[cmd.shortcut]?.binding ?? null) : null}
                  onSelect={onSelect}
                />
              ))}
            </Command.Group>
          ))}
        </Command.List>
      </Command>
    </PaletteDialog>
  );
};
