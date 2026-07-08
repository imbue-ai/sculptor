// The Layouts switcher: a switcher-first dialog (PyCharm ⌘E semantics) rendered on
// the PaletteDialog shell. MRU-ordered list, type-to-filter, a Raycast-style bottom
// bar, and a ⌘J more-options popover scoped to the highlighted layout. Keyboard is
// owned by a capture-phase window listener so ⌘⇧L / ⌘J / Enter / Esc beat the global
// shortcut handler while the switcher is open.

import { Button } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { Check, Pencil, Plus, Sparkles, Star, Trash2 } from "lucide-react";
import type { RefObject } from "react";
import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ElementIds } from "~/api";
import { useKeybinding } from "~/common/keybindings";
import { formatShortcutForDisplay, shouldHandleKeybinding } from "~/common/ShortcutUtils.ts";
import {
  applyLayoutAtom,
  deleteLayoutAtom,
  renameLayoutAtom,
  setDefaultLayoutAtom,
} from "~/components/sections/layoutActions.ts";
import type { SavedLayout } from "~/components/sections/persistence/types.ts";
import { panelRegistryAtom } from "~/components/sections/registry/panelRegistry.ts";
import {
  appliedLayoutIdAtom,
  defaultLayoutIdAtom,
  layoutMruAtom,
  resolvedLayoutsAtom,
} from "~/components/sections/savedLayoutAtoms.ts";
import type { PanelId } from "~/components/sections/sectionTypes.ts";
import { SYSTEM_DEFAULT_LAYOUT_ID, SYSTEM_DEFAULT_LAYOUT_SUMMARY } from "~/components/sections/systemDefaultLayout.ts";

import { describeLayout } from "./layoutSummary.ts";
import styles from "./LayoutSwitcher.module.scss";
import { layoutsSwitcherOpenAtom, layoutTidyTargetAtom, saveLayoutModalOpenAtom } from "./layoutUiAtoms.ts";
import { LayoutWireframeIcon } from "./LayoutWireframeIcon.tsx";
import { initialHighlightIndex, orderLayoutsByMru } from "./switcherOrder.ts";

type RowMarker = "default" | "current" | null;

// The ⌘J popover items, scoped to the highlighted layout.
type PopoverItem = {
  key: string;
  label: string;
  icon: typeof Check;
  shortcut?: string;
  testId: string;
  disabled: boolean;
  danger: boolean;
  separatorBefore: boolean;
  run: () => void;
};

const MOD = formatShortcutForDisplay("Meta");

function markerFor(layout: SavedLayout, defaultLayoutId: string, appliedLayoutId: string | undefined): RowMarker {
  if (layout.id === defaultLayoutId) {
    return "default";
  }

  if (layout.id === appliedLayoutId) {
    return "current";
  }
  return null;
}

export const LayoutSwitcher = (): ReactElement => {
  // Atoms
  const resolvedLayouts = useAtomValue(resolvedLayoutsAtom);
  const mru = useAtomValue(layoutMruAtom);
  const appliedLayoutId = useAtomValue(appliedLayoutIdAtom);
  const defaultLayoutId = useAtomValue(defaultLayoutIdAtom);
  const registry = useAtomValue(panelRegistryAtom);

  const setOpen = useSetAtom(layoutsSwitcherOpenAtom);
  const setSaveOpen = useSetAtom(saveLayoutModalOpenAtom);
  const setTidyTarget = useSetAtom(layoutTidyTargetAtom);
  const applyLayout = useSetAtom(applyLayoutAtom);
  const setDefaultLayout = useSetAtom(setDefaultLayoutAtom);
  const deleteLayout = useSetAtom(deleteLayoutAtom);
  const renameLayout = useSetAtom(renameLayoutAtom);

  // Keybindings (for hints + the capture-phase matcher).
  const openLayoutsBinding = useKeybinding("open_layouts");
  const moreOptionsBinding = useKeybinding("layout_more_options");

  // The list is MRU-ordered; the highlight opens on the "previous" layout.
  const ordered = useMemo(() => orderLayoutsByMru(resolvedLayouts, mru), [resolvedLayouts, mru]);

  // Internal state
  const [query, setQuery] = useState<string>("");
  const [highlightIndex, setHighlightIndex] = useState<number>(() => initialHighlightIndex(ordered, appliedLayoutId));
  const [isMoreOptionsOpen, setIsMoreOptionsOpen] = useState<boolean>(false);
  const [popoverIndex, setPopoverIndex] = useState<number>(0);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState<string>("");

  const searchInputRef = useRef<HTMLInputElement>(null);
  const renameInputRef = useRef<HTMLInputElement>(null);

  const getPanelName = useCallback(
    (id: PanelId): string => registry.find((definition) => definition.id === id)?.displayName ?? id,
    [registry],
  );

  const summaryFor = useCallback(
    (layout: SavedLayout): string =>
      layout.id === SYSTEM_DEFAULT_LAYOUT_ID
        ? SYSTEM_DEFAULT_LAYOUT_SUMMARY
        : describeLayout(layout.captured, getPanelName),
    [getPanelName],
  );

  const filtered = useMemo(() => {
    const trimmed = query.trim().toLowerCase();
    if (trimmed === "") {
      return ordered;
    }
    return ordered.filter((layout) => layout.name.toLowerCase().includes(trimmed));
  }, [ordered, query]);

  const clampedHighlight = filtered.length === 0 ? 0 : Math.min(highlightIndex, filtered.length - 1);
  const highlighted: SavedLayout | undefined = filtered[clampedHighlight];

  const close = useCallback((): void => setOpen(false), [setOpen]);

  // ── Actions ────────────────────────────────────────────────────────────────
  const apply = useCallback(
    (layout: SavedLayout): void => {
      applyLayout(layout);
      close();
    },
    [applyLayout, close],
  );

  // Apply, then hand off to the Tidy confirmation (which is silent when nothing
  // would close). Applying never closes anything; Tidy is the opt-out.
  const applyAndTidy = useCallback(
    (layout: SavedLayout): void => {
      applyLayout(layout);
      setTidyTarget(layout);
      close();
    },
    [applyLayout, setTidyTarget, close],
  );

  const startRename = useCallback((layout: SavedLayout): void => {
    setIsMoreOptionsOpen(false);
    setRenamingId(layout.id);
    setRenameValue(layout.name);
  }, []);

  const commitRename = useCallback((): void => {
    if (renamingId !== null) {
      renameLayout({ id: renamingId, name: renameValue });
    }
    setRenamingId(null);
  }, [renamingId, renameValue, renameLayout]);

  const cancelRename = useCallback((): void => setRenamingId(null), []);

  const popoverItems: ReadonlyArray<PopoverItem> = useMemo(() => {
    if (highlighted === undefined) {
      return [];
    }
    const isSystemDefault = highlighted.id === SYSTEM_DEFAULT_LAYOUT_ID;
    return [
      {
        key: "apply",
        label: "Apply",
        icon: Check,
        shortcut: formatShortcutForDisplay("Enter"),
        testId: ElementIds.LAYOUTS_MORE_OPTIONS_APPLY,
        disabled: false,
        danger: false,
        separatorBefore: false,
        run: () => apply(highlighted),
      },
      {
        key: "apply-tidy",
        label: "Apply & tidy",
        icon: Sparkles,
        shortcut: formatShortcutForDisplay("Meta+Enter"),
        testId: ElementIds.LAYOUTS_MORE_OPTIONS_APPLY_TIDY,
        disabled: false,
        danger: false,
        separatorBefore: false,
        run: () => applyAndTidy(highlighted),
      },
      {
        key: "set-default",
        label: "Set as default",
        icon: Star,
        testId: ElementIds.LAYOUTS_MORE_OPTIONS_SET_DEFAULT,
        disabled: highlighted.id === defaultLayoutId,
        danger: false,
        separatorBefore: true,
        run: (): void => {
          setDefaultLayout(highlighted.id);
          setIsMoreOptionsOpen(false);
        },
      },
      {
        key: "rename",
        label: "Rename",
        icon: Pencil,
        testId: ElementIds.LAYOUTS_MORE_OPTIONS_RENAME,
        disabled: isSystemDefault,
        danger: false,
        separatorBefore: false,
        run: () => startRename(highlighted),
      },
      {
        key: "delete",
        label: "Delete",
        icon: Trash2,
        shortcut: `${MOD}⌫`,
        testId: ElementIds.LAYOUTS_MORE_OPTIONS_DELETE,
        disabled: isSystemDefault,
        danger: true,
        separatorBefore: false,
        run: (): void => {
          deleteLayout(highlighted.id);
          setIsMoreOptionsOpen(false);
        },
      },
    ];
  }, [highlighted, defaultLayoutId, apply, applyAndTidy, setDefaultLayout, startRename, deleteLayout]);

  const enabledPopoverIndexes = useMemo(
    () =>
      popoverItems
        .map((item, index) => ({ item, index }))
        .filter(({ item }) => !item.disabled)
        .map(({ index }) => index),
    [popoverItems],
  );

  const openPopover = useCallback((): void => {
    if (highlighted === undefined) {
      return;
    }
    setPopoverIndex(enabledPopoverIndexes[0] ?? 0);
    setIsMoreOptionsOpen(true);
  }, [highlighted, enabledPopoverIndexes]);

  // ── Keyboard (capture phase, so it wins over the global handler) ────────────
  // The capture listener is mounted once and reads live state through this ref;
  // it's refreshed after every commit so the handler never closes over stale
  // values (writing the ref in an effect keeps render side-effect-free).
  const stateRef = useRef({
    filtered,
    clampedHighlight,
    highlighted,
    moreOptionsOpen: isMoreOptionsOpen,
    popoverIndex,
    popoverItems,
    enabledPopoverIndexes,
    renamingId,
    query,
    openLayoutsBinding,
    moreOptionsBinding,
  });
  useEffect(() => {
    stateRef.current = {
      filtered,
      clampedHighlight,
      highlighted,
      moreOptionsOpen: isMoreOptionsOpen,
      popoverIndex,
      popoverItems,
      enabledPopoverIndexes,
      renamingId,
      query,
      openLayoutsBinding,
      moreOptionsBinding,
    };
  });

  useEffect(() => {
    const stepPopover = (delta: number): void => {
      const { enabledPopoverIndexes: enabled, popoverIndex: current } = stateRef.current;
      if (enabled.length === 0) {
        return;
      }
      const at = Math.max(0, enabled.indexOf(current));
      setPopoverIndex(enabled[(at + delta + enabled.length) % enabled.length]);
    };

    const handler = (event: KeyboardEvent): void => {
      const state = stateRef.current;

      // Escape is handled here even mid-rename so it can cancel the rename (and
      // stop Radix from closing the whole dialog).
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        if (state.renamingId !== null) {
          cancelRename();
        } else if (state.moreOptionsOpen) {
          setIsMoreOptionsOpen(false);
        } else if (state.query !== "") {
          setQuery("");
          setHighlightIndex(0);
        } else {
          close();
        }
        return;
      }

      // While renaming, the inline input owns every other key.
      if (state.renamingId !== null) {
        return;
      }

      // ⌘⇧L while open: advance the highlight (double-tap bounce).
      if (state.openLayoutsBinding != null && shouldHandleKeybinding(event, state.openLayoutsBinding)) {
        event.preventDefault();
        event.stopPropagation();
        if (state.filtered.length > 0) {
          setHighlightIndex((index) => (index + 1) % state.filtered.length);
        }
        return;
      }

      // ⌘J: toggle the more-options popover.
      if (state.moreOptionsBinding != null && shouldHandleKeybinding(event, state.moreOptionsBinding)) {
        event.preventDefault();
        event.stopPropagation();
        if (state.moreOptionsOpen) {
          setIsMoreOptionsOpen(false);
        } else {
          openPopover();
        }
        return;
      }

      const isMod = event.metaKey || event.ctrlKey;

      // ⌘S: save the current arrangement.
      if (isMod && !event.shiftKey && !event.altKey && event.key.toLowerCase() === "s") {
        event.preventDefault();
        event.stopPropagation();
        setSaveOpen(true);
        return;
      }

      if (state.moreOptionsOpen) {
        // Popover navigation.
        if (event.key === "ArrowDown") {
          event.preventDefault();
          stepPopover(1);
          return;
        }

        if (event.key === "ArrowUp") {
          event.preventDefault();
          stepPopover(-1);
          return;
        }

        if (event.key === "Enter") {
          event.preventDefault();
          state.popoverItems[state.popoverIndex]?.run();
          return;
        }

        // ⌘↵ / ⌘⌫ still work directly from the popover.
        if (isMod && event.key === "Enter" && state.highlighted !== undefined) {
          event.preventDefault();
          applyAndTidy(state.highlighted);
          return;
        }

        if (
          isMod &&
          event.key === "Backspace" &&
          state.highlighted !== undefined &&
          state.highlighted.id !== SYSTEM_DEFAULT_LAYOUT_ID
        ) {
          event.preventDefault();
          deleteLayout(state.highlighted.id);
          setIsMoreOptionsOpen(false);
          return;
        }
        return;
      }

      // List navigation.
      if (event.key === "ArrowDown") {
        event.preventDefault();
        if (state.filtered.length > 0) {
          setHighlightIndex((index) => (index + 1) % state.filtered.length);
        }
        return;
      }

      if (event.key === "ArrowUp") {
        event.preventDefault();
        if (state.filtered.length > 0) {
          setHighlightIndex((index) => (index - 1 + state.filtered.length) % state.filtered.length);
        }
        return;
      }

      if (event.key === "Enter" && state.highlighted !== undefined) {
        event.preventDefault();
        if (isMod) {
          applyAndTidy(state.highlighted);
        } else {
          apply(state.highlighted);
        }
      }
    };

    window.addEventListener("keydown", handler, { capture: true });
    return (): void => window.removeEventListener("keydown", handler, { capture: true });
  }, [apply, applyAndTidy, cancelRename, close, deleteLayout, openPopover, setSaveOpen]);

  // Focus the search input on open, and the rename input when a rename starts.
  useEffect(() => {
    searchInputRef.current?.focus();
  }, []);
  useEffect(() => {
    if (renamingId !== null) {
      renameInputRef.current?.focus();
      renameInputRef.current?.select();
    }
  }, [renamingId]);

  const applyHint = formatShortcutForDisplay("Enter");
  const saveHint = formatShortcutForDisplay("Meta+s");
  const moreOptionsHint = formatShortcutForDisplay(moreOptionsBinding ?? "");

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <input
          ref={searchInputRef}
          className={styles.searchInput}
          placeholder="Search layouts…"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setHighlightIndex(0);
          }}
          data-testid={ElementIds.LAYOUTS_SWITCHER_SEARCH_INPUT}
          aria-label="Search layouts"
        />
      </div>
      <div className={styles.divider} />
      <div className={styles.list}>
        <div className={styles.groupHeading}>Layouts</div>
        {filtered.length === 0 ? (
          <div className={styles.empty}>No layouts match “{query}”.</div>
        ) : (
          filtered.map((layout, index) => (
            <SwitcherRow
              key={layout.id}
              layout={layout}
              summary={summaryFor(layout)}
              marker={markerFor(layout, defaultLayoutId, appliedLayoutId)}
              selected={index === clampedHighlight}
              renaming={renamingId === layout.id}
              renameValue={renameValue}
              renameInputRef={renameInputRef}
              onRenameChange={setRenameValue}
              onRenameCommit={commitRename}
              onRenameCancel={cancelRename}
              onMouseEnter={() => setHighlightIndex(index)}
              onClick={() => apply(layout)}
            />
          ))
        )}
      </div>
      <div className={styles.bar}>
        <Button
          type="button"
          variant="ghost"
          size="1"
          color="gray"
          className={styles.barButton}
          onClick={() => setSaveOpen(true)}
          data-testid={ElementIds.LAYOUTS_SWITCHER_SAVE_BUTTON}
        >
          <Plus size={13} />
          Save current arrangement…
          <span className={styles.barKbd}>{saveHint}</span>
        </Button>
        <div className={styles.barRight}>
          <Button
            type="button"
            variant="ghost"
            size="1"
            color="gray"
            className={styles.barButton}
            onClick={() => highlighted !== undefined && apply(highlighted)}
            disabled={highlighted === undefined}
            data-testid={ElementIds.LAYOUTS_SWITCHER_APPLY_BUTTON}
          >
            Apply
            <span className={styles.barKbd}>{applyHint}</span>
          </Button>
          <span className={styles.barDivider} />
          <Button
            type="button"
            variant="ghost"
            size="1"
            color="gray"
            className={`${styles.barButton} ${isMoreOptionsOpen ? styles.barButtonActive : ""}`}
            onClick={() => (isMoreOptionsOpen ? setIsMoreOptionsOpen(false) : openPopover())}
            disabled={highlighted === undefined}
            data-testid={ElementIds.LAYOUTS_SWITCHER_MORE_OPTIONS_BUTTON}
          >
            More options
            <span className={styles.barKbd}>{moreOptionsHint}</span>
          </Button>
        </div>
      </div>
      {isMoreOptionsOpen && highlighted !== undefined ? (
        <div className={styles.popover} data-testid={ElementIds.LAYOUTS_MORE_OPTIONS_POPOVER}>
          {popoverItems.map((item, index) => (
            <div key={item.key}>
              {item.separatorBefore ? <div className={styles.popoverSeparator} /> : null}
              <Button
                type="button"
                variant="ghost"
                size="2"
                color={item.danger ? "red" : "gray"}
                className={`${styles.popoverRow} ${item.danger ? styles.popoverRowDanger : ""} ${
                  index === popoverIndex ? styles.popoverRowActive : ""
                }`}
                disabled={item.disabled}
                onMouseEnter={() => setPopoverIndex(index)}
                onClick={() => item.run()}
                data-testid={item.testId}
              >
                <item.icon size={14} />
                {item.label}
                {item.shortcut !== undefined ? <span className={styles.popoverShortcut}>{item.shortcut}</span> : null}
              </Button>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
};

type SwitcherRowProps = {
  layout: SavedLayout;
  summary: string;
  marker: RowMarker;
  selected: boolean;
  renaming: boolean;
  renameValue: string;
  renameInputRef: RefObject<HTMLInputElement | null>;
  onRenameChange: (value: string) => void;
  onRenameCommit: () => void;
  onRenameCancel: () => void;
  onMouseEnter: () => void;
  onClick: () => void;
};

const SwitcherRow = ({
  layout,
  summary,
  marker,
  selected,
  renaming,
  renameValue,
  renameInputRef,
  onRenameChange,
  onRenameCommit,
  onRenameCancel,
  onMouseEnter,
  onClick,
}: SwitcherRowProps): ReactElement => {
  return (
    <div
      className={`${styles.row} ${selected ? styles.rowSelected : ""}`}
      onMouseEnter={onMouseEnter}
      onClick={renaming ? undefined : (): void => onClick()}
      data-testid={ElementIds.LAYOUTS_SWITCHER_ROW}
      data-layout-id={layout.id}
      data-selected={selected}
    >
      <span className={styles.rowIcon}>
        <LayoutWireframeIcon captured={layout.captured} />
      </span>
      {renaming ? (
        <input
          ref={renameInputRef}
          className={styles.renameInput}
          value={renameValue}
          onChange={(event) => onRenameChange(event.target.value)}
          onBlur={onRenameCommit}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              onRenameCommit();
            } else if (event.key === "Escape") {
              event.preventDefault();
              onRenameCancel();
            }
          }}
          onClick={(event) => event.stopPropagation()}
          data-testid={ElementIds.LAYOUTS_SWITCHER_RENAME_INPUT}
          aria-label="Rename layout"
        />
      ) : (
        <>
          <span className={styles.rowBody}>
            <span className={styles.rowTitle}>{layout.name}</span>
            <span className={styles.rowSummary}>{summary}</span>
          </span>
          <span className={styles.rowTrailing}>
            {marker === "default" ? (
              <span className={styles.rowMarker}>
                <Star size={12} fill="currentColor" />
                Default
              </span>
            ) : marker === "current" ? (
              <span className={styles.rowMarker}>Current</span>
            ) : null}
          </span>
        </>
      )}
    </div>
  );
};
