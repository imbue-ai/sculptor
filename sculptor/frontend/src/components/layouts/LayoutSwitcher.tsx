// The Layouts switcher: a switcher-first dialog (PyCharm ⌘E semantics) rendered on
// the PaletteDialog shell. MRU-ordered list, type-to-filter, a Raycast-style bottom
// bar, and a ⌘J more-options popover scoped to the highlighted layout. Keyboard is
// owned by a capture-phase window listener so ⌘⇧L / ⌘J / Enter / Esc beat the global
// shortcut handler while the switcher is open.

import { Button, ContextMenu } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import type { LucideIcon } from "lucide-react";
import { Check, Keyboard, Pencil, Plus, Sparkles, Star, Trash2 } from "lucide-react";
import type { RefObject } from "react";
import type { ReactElement } from "react";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ElementIds } from "~/api";
import { useKeybinding } from "~/common/keybindings";
import { layoutShortcutBindingsAtom } from "~/common/keybindings/layoutShortcuts.ts";
import { useSetLayoutShortcut } from "~/common/keybindings/useLayoutShortcutActions.ts";
import { useImbueNavigate } from "~/common/NavigateUtils.ts";
import { formatShortcutForDisplay, shouldHandleKeybinding } from "~/common/ShortcutUtils.ts";
import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";
import {
  applyLayoutAtom,
  deleteLayoutAtom,
  renameLayoutAtom,
  setDefaultLayoutAtom,
  setLayoutTidyOnApplyAtom,
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
import { ShortcutHint } from "~/components/ShortcutHint.tsx";
import { SettingsSection } from "~/pages/settings/sections.ts";

import { describeLayout } from "./layoutSummary.ts";
import styles from "./LayoutSwitcher.module.scss";
import { layoutsSwitcherOpenAtom, saveLayoutModalOpenAtom } from "./layoutUiAtoms.ts";
import { LayoutWireframeIcon } from "./LayoutWireframeIcon.tsx";
import { initialHighlightIndex, orderLayoutsByMru } from "./switcherOrder.ts";

type RowMarker = "default" | "current" | null;

// Wires the search input's aria-activedescendant to the highlighted row so
// screen readers announce the active option while focus stays in the input.
const LISTBOX_ID = "layouts-switcher-listbox";
const optionDomId = (layoutId: string): string => `layouts-switcher-option-${layoutId}`;

// One actionable item scoped to a single layout. The same descriptor list feeds
// both the ⌘J popover (highlighted layout) and each row's right-click context menu,
// so the two surfaces can't drift. `shortcut` is a RAW binding string; each surface
// formats it. `checked` marks a toggle row (the tidy-on-apply option).
type PopoverItem = {
  key: string;
  label: string;
  icon: LucideIcon;
  shortcut?: string;
  testId: string;
  disabled: boolean;
  danger: boolean;
  separatorBefore: boolean;
  checked?: boolean;
  run: () => void;
};

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
  const applyLayout = useSetAtom(applyLayoutAtom);
  const setDefaultLayout = useSetAtom(setDefaultLayoutAtom);
  const deleteLayout = useSetAtom(deleteLayoutAtom);
  const renameLayout = useSetAtom(renameLayoutAtom);
  const setTidyOnApply = useSetAtom(setLayoutTidyOnApplyAtom);
  const layoutShortcutBindings = useAtomValue(layoutShortcutBindingsAtom);
  const setLayoutShortcut = useSetLayoutShortcut();
  const { navigateToGlobalSettings } = useImbueNavigate();

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

  // Opening the save dialog closes the switcher so the two don't stack on the
  // same centered shell.
  const openSave = useCallback((): void => {
    setSaveOpen(true);
    close();
  }, [setSaveOpen, close]);

  // Actions the switcher performs on the highlighted layout.
  const apply = useCallback(
    (layout: SavedLayout): void => {
      applyLayout(layout);
      close();
    },
    [applyLayout, close],
  );

  // Open Settings ▸ Keybindings, where a layout's shortcut is assigned (there is no
  // bespoke recording surface here — the switcher only links out to it).
  const openShortcutSettings = useCallback((): void => {
    close();
    navigateToGlobalSettings(SettingsSection.KEYBINDINGS);
  }, [close, navigateToGlobalSettings]);

  // Delete the layout and drop its now-orphaned shortcut override (if any).
  const removeLayout = useCallback(
    (layout: SavedLayout): void => {
      deleteLayout(layout.id);
      void setLayoutShortcut(layout.id, null);
    },
    [deleteLayout, setLayoutShortcut],
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

  // Build the action list for a given layout. Shared by the ⌘J popover (highlighted
  // layout) and each row's right-click context menu so both stay in lock-step.
  const buildLayoutItems = useCallback(
    (layout: SavedLayout): ReadonlyArray<PopoverItem> => {
      const isSystemDefault = layout.id === SYSTEM_DEFAULT_LAYOUT_ID;
      return [
        {
          key: "apply",
          label: "Apply",
          icon: Check,
          shortcut: "Enter",
          testId: ElementIds.LAYOUTS_MORE_OPTIONS_APPLY,
          disabled: false,
          danger: false,
          separatorBefore: false,
          run: () => apply(layout),
        },
        {
          key: "tidy-toggle",
          label: "Tidy panels when applying",
          icon: Sparkles,
          testId: ElementIds.LAYOUTS_MORE_OPTIONS_TIDY_TOGGLE,
          disabled: isSystemDefault,
          danger: false,
          separatorBefore: false,
          checked: layout.tidyOnApply === true,
          // Toggle the flag in place — deliberately does NOT close the popover, so the
          // check flips under the pointer.
          run: () => setTidyOnApply({ id: layout.id, tidyOnApply: !(layout.tidyOnApply === true) }),
        },
        {
          key: "shortcut",
          label: "Keyboard shortcut",
          icon: Keyboard,
          shortcut: layoutShortcutBindings[layout.id],
          testId: ElementIds.LAYOUTS_MORE_OPTIONS_SHORTCUT,
          disabled: false,
          danger: false,
          separatorBefore: true,
          run: () => openShortcutSettings(),
        },
        {
          key: "set-default",
          label: "Set as default",
          icon: Star,
          testId: ElementIds.LAYOUTS_MORE_OPTIONS_SET_DEFAULT,
          disabled: layout.id === defaultLayoutId,
          danger: false,
          separatorBefore: false,
          run: (): void => {
            setDefaultLayout(layout.id);
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
          run: () => startRename(layout),
        },
        {
          key: "delete",
          label: "Delete",
          icon: Trash2,
          shortcut: "Meta+Backspace",
          testId: ElementIds.LAYOUTS_MORE_OPTIONS_DELETE,
          disabled: isSystemDefault,
          danger: true,
          separatorBefore: false,
          run: (): void => {
            removeLayout(layout);
            setIsMoreOptionsOpen(false);
          },
        },
      ];
    },
    [
      apply,
      setTidyOnApply,
      layoutShortcutBindings,
      openShortcutSettings,
      defaultLayoutId,
      setDefaultLayout,
      startRename,
      removeLayout,
    ],
  );

  const popoverItems: ReadonlyArray<PopoverItem> = useMemo(
    () => (highlighted === undefined ? [] : buildLayoutItems(highlighted)),
    [highlighted, buildLayoutItems],
  );

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

  // Keyboard (capture phase, so it wins over the global handler).
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
    apply,
    openPopover,
    openSave,
    cancelRename,
    close,
    removeLayout,
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
      apply,
      openPopover,
      openSave,
      cancelRename,
      close,
      removeLayout,
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
          state.cancelRename();
        } else if (state.moreOptionsOpen) {
          setIsMoreOptionsOpen(false);
        } else if (state.query !== "") {
          setQuery("");
          setHighlightIndex(0);
        } else {
          state.close();
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
          state.openPopover();
        }
        return;
      }

      const isMod = event.metaKey || event.ctrlKey;

      // ⌘S: save the current arrangement.
      if (isMod && !event.shiftKey && !event.altKey && event.key.toLowerCase() === "s") {
        event.preventDefault();
        event.stopPropagation();
        state.openSave();
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

        // Plain Enter runs the highlighted popover row (skipping it if it is
        // disabled); ⌘⌫ falls through to its own branch below, so this must not
        // swallow a modified Enter.
        if (event.key === "Enter" && !isMod) {
          event.preventDefault();
          const item = state.popoverItems[state.popoverIndex];
          if (item !== undefined && !item.disabled) {
            item.run();
          }
          return;
        }

        // ⌘⌫ Delete works directly from the popover too.
        if (
          isMod &&
          event.key === "Backspace" &&
          state.highlighted !== undefined &&
          state.highlighted.id !== SYSTEM_DEFAULT_LAYOUT_ID
        ) {
          event.preventDefault();
          state.removeLayout(state.highlighted);
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

      // Enter applies the highlighted layout (⌘↵ collapses to the same — tidy is now
      // a per-layout property applyLayoutAtom honors, not a separate verb).
      if (event.key === "Enter" && state.highlighted !== undefined) {
        event.preventDefault();
        state.apply(state.highlighted);
      }
    };

    window.addEventListener("keydown", handler, { capture: true });
    return (): void => window.removeEventListener("keydown", handler, { capture: true });
    // Subscribed once for the switcher's lifetime: the handler reads all live
    // state and callbacks through stateRef, so it never re-subscribes when the
    // highlight or selection changes.
  }, []);

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
          role="combobox"
          aria-expanded={true}
          aria-controls={LISTBOX_ID}
          aria-activedescendant={highlighted !== undefined ? optionDomId(highlighted.id) : undefined}
        />
      </div>
      <div className={styles.divider} />
      <div className={styles.list} id={LISTBOX_ID} role="listbox" aria-label="Layouts">
        <div className={styles.groupHeading} aria-hidden="true">
          Layouts
        </div>
        {filtered.length === 0 ? (
          <div className={styles.empty}>No layouts match “{query}”.</div>
        ) : (
          filtered.map((layout, index) => (
            <SwitcherRow
              key={layout.id}
              layout={layout}
              summary={summaryFor(layout)}
              marker={markerFor(layout, defaultLayoutId, appliedLayoutId)}
              shortcut={layoutShortcutBindings[layout.id]}
              items={buildLayoutItems(layout)}
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
          onClick={openSave}
          data-testid={ElementIds.LAYOUTS_SWITCHER_SAVE_BUTTON}
        >
          <Plus size={13} />
          Save current arrangement…
          <ShortcutHint binding="Meta+s" className={styles.barKbd} />
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
            <ShortcutHint binding="Enter" className={styles.barKbd} />
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
            <ShortcutHint binding={moreOptionsBinding ?? ""} className={styles.barKbd} />
          </Button>
        </div>
      </div>
      {isMoreOptionsOpen && highlighted !== undefined ? (
        <div className={styles.popover} role="menu" data-testid={ElementIds.LAYOUTS_MORE_OPTIONS_POPOVER}>
          {popoverItems.map((item, index) => (
            <div key={item.key}>
              {item.separatorBefore ? <div className={styles.popoverSeparator} /> : null}
              <Button
                type="button"
                role="menuitem"
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
                {item.shortcut !== undefined ? (
                  <ShortcutHint binding={item.shortcut} className={styles.popoverShortcut} />
                ) : null}
                {item.checked === true ? <Check size={14} className={styles.popoverCheck} /> : null}
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
  // The layout's assigned keyboard shortcut (raw binding), shown as a trailing hint.
  shortcut?: string;
  // The shared action descriptors, rendered as this row's right-click context menu.
  items: ReadonlyArray<PopoverItem>;
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
  shortcut,
  items,
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
  const dangerColor = useThemeDangerColor();

  // Radix Themes' ContextMenu.Trigger already renders its single child as the trigger
  // (it applies asChild internally), so the option div stays a direct child of the
  // listbox — the role="listbox" > role="option" tree and aria-activedescendant are
  // untouched. Root/Content render no inline DOM (Content is portaled).
  const row = (
    <div
      id={optionDomId(layout.id)}
      role="option"
      aria-selected={selected}
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
            {shortcut !== undefined ? <ShortcutHint binding={shortcut} className={styles.rowShortcut} /> : null}
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

  return (
    <ContextMenu.Root>
      <ContextMenu.Trigger>{row}</ContextMenu.Trigger>
      <ContextMenu.Content size="1" data-testid={ElementIds.LAYOUTS_ROW_CONTEXT_MENU}>
        {items.map((item) => (
          <Fragment key={item.key}>
            {item.separatorBefore ? <ContextMenu.Separator /> : null}
            {item.checked !== undefined ? (
              <ContextMenu.CheckboxItem
                checked={item.checked}
                disabled={item.disabled}
                onCheckedChange={() => item.run()}
                data-testid={item.testId}
              >
                {item.label}
              </ContextMenu.CheckboxItem>
            ) : (
              <ContextMenu.Item
                color={item.danger ? dangerColor : undefined}
                disabled={item.disabled}
                shortcut={item.shortcut !== undefined ? formatShortcutForDisplay(item.shortcut) : undefined}
                onSelect={() => item.run()}
                data-testid={item.testId}
              >
                {item.label}
              </ContextMenu.Item>
            )}
          </Fragment>
        ))}
      </ContextMenu.Content>
    </ContextMenu.Root>
  );
};
