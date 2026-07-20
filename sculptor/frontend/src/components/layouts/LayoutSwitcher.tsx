// The Layouts switcher: a switcher-first dialog (PyCharm ⌘E semantics) rendered on
// the PaletteDialog shell. MRU-ordered list, type-to-filter, a Raycast-style bottom
// bar, and a ⌘J more-options menu (a Radix DropdownMenu) scoped to the highlighted
// layout. Keyboard is owned by a capture-phase window listener so ⌘⇧L / ⌘J / Enter /
// Esc beat the global shortcut handler while the switcher is open; once the menu is
// open, Radix owns arrows / Enter / Escape / typeahead within it.

import { Button, ContextMenu, DropdownMenu } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import type { LucideIcon } from "lucide-react";
import { Check, Pencil, Star, Trash2 } from "lucide-react";
import type { ReactElement } from "react";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ElementIds } from "~/api";
import { useKeybinding } from "~/common/keybindings";
import { layoutShortcutBindingsAtom } from "~/common/keybindings/layoutShortcuts.ts";
import { useSetLayoutShortcut } from "~/common/keybindings/useLayoutShortcutActions.ts";
import { formatShortcutForDisplay, shouldHandleKeybinding } from "~/common/ShortcutUtils.ts";
import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";
import { applyLayoutAtom, deleteLayoutAtom, setDefaultLayoutAtom } from "~/components/sections/layoutActions.ts";
import type { SavedLayout } from "~/components/sections/persistence/types.ts";
import { panelRegistryAtom } from "~/components/sections/registry/panelRegistry.ts";
import {
  appliedLayoutIdAtom,
  defaultLayoutIdAtom,
  layoutMruAtom,
  resolvedLayoutsAtom,
} from "~/components/sections/savedLayoutAtoms.ts";
import type { PanelId } from "~/components/sections/sectionTypes.ts";
import { isSystemLayoutId, SYSTEM_LAYOUT_SUMMARIES } from "~/components/sections/systemDefaultLayout.ts";
import { ShortcutHint } from "~/components/ShortcutHint.tsx";

import { describeLayout } from "./layoutSummary.ts";
import styles from "./LayoutSwitcher.module.scss";
import { layoutsSwitcherOpenAtom, saveLayoutModalRequestAtom } from "./layoutUiAtoms.ts";
import { LayoutWireframeIcon } from "./LayoutWireframeIcon.tsx";
import { initialHighlightIndex, orderLayoutsByMru } from "./switcherOrder.ts";

type RowMarker = "default" | "current" | null;

// Wires the search input's aria-activedescendant to the highlighted row so
// screen readers announce the active option while focus stays in the input.
const LISTBOX_ID = "layouts-switcher-listbox";
const optionDomId = (layoutId: string): string => `layouts-switcher-option-${layoutId}`;

// One actionable item scoped to a single layout. The same descriptor list feeds
// both the ⌘J more-options menu (highlighted layout) and each row's right-click
// context menu, so the two menus can't drift. `shortcut` is a RAW binding string;
// each surface formats it for display.
type LayoutMenuItem = {
  key: string;
  label: string;
  // Rendered by the ⌘J menu only; the row context menu shows bare labels.
  icon: LucideIcon;
  shortcut?: string;
  testId: string;
  disabled: boolean;
  danger: boolean;
  separatorBefore: boolean;
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
  const setSaveRequest = useSetAtom(saveLayoutModalRequestAtom);
  const applyLayout = useSetAtom(applyLayoutAtom);
  const setDefaultLayout = useSetAtom(setDefaultLayoutAtom);
  const deleteLayout = useSetAtom(deleteLayoutAtom);
  const layoutShortcutBindings = useAtomValue(layoutShortcutBindingsAtom);
  const setLayoutShortcut = useSetLayoutShortcut();

  // Keybindings (for hints + the capture-phase matcher).
  const openLayoutsBinding = useKeybinding("open_layouts");
  const moreOptionsBinding = useKeybinding("layout_more_options");

  // The list is MRU-ordered; the highlight opens on the "previous" layout.
  const ordered = useMemo(() => orderLayoutsByMru(resolvedLayouts, mru), [resolvedLayouts, mru]);

  // Internal state
  const [query, setQuery] = useState<string>("");
  const [highlightIndex, setHighlightIndex] = useState<number>(() => initialHighlightIndex(ordered, appliedLayoutId));
  const [isMoreOptionsOpen, setIsMoreOptionsOpen] = useState<boolean>(false);

  const searchInputRef = useRef<HTMLInputElement>(null);
  const dangerColor = useThemeDangerColor();

  const getPanelName = useCallback(
    (id: PanelId): string => registry.find((definition) => definition.id === id)?.displayName ?? id,
    [registry],
  );

  const summaryFor = useCallback(
    (layout: SavedLayout): string =>
      SYSTEM_LAYOUT_SUMMARIES[layout.id] ?? describeLayout(layout.captured, getPanelName),
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

  // Opening the save/edit dialog closes the switcher so the two don't stack on the
  // same centered shell.
  const openSave = useCallback((): void => {
    setSaveRequest({ mode: "create" });
    close();
  }, [setSaveRequest, close]);

  // Reopen the save form on an existing layout to change its name / shortcut / tidy /
  // default — the single place those live now (no per-item toggles in this menu).
  const openEdit = useCallback(
    (layout: SavedLayout): void => {
      setSaveRequest({ mode: "edit", layout });
      close();
    },
    [setSaveRequest, close],
  );

  // Actions the switcher performs on the highlighted layout.
  const apply = useCallback(
    (layout: SavedLayout): void => {
      applyLayout(layout);
      close();
    },
    [applyLayout, close],
  );

  // Delete the layout and drop its now-orphaned shortcut override (if any).
  const removeLayout = useCallback(
    (layout: SavedLayout): void => {
      deleteLayout(layout.id);
      void setLayoutShortcut(layout.id, null);
    },
    [deleteLayout, setLayoutShortcut],
  );

  // Build the action list for a given layout. Shared by the ⌘J more-options menu
  // (highlighted layout) and each row's right-click context menu so both stay in
  // lock-step. Both surfaces are Radix menus that dismiss themselves once an item is
  // selected, so no descriptor closes its own menu.
  const buildLayoutItems = useCallback(
    (layout: SavedLayout): ReadonlyArray<LayoutMenuItem> => {
      // Built-ins (System Default + presets) are read-only: you can apply them and set
      // one as default, but can't edit, rename, or delete them.
      const isSystem = isSystemLayoutId(layout.id);
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
          key: "set-default",
          label: "Set as default",
          icon: Star,
          testId: ElementIds.LAYOUTS_MORE_OPTIONS_SET_DEFAULT,
          disabled: layout.id === defaultLayoutId,
          danger: false,
          separatorBefore: true,
          run: () => setDefaultLayout(layout.id),
        },
        {
          key: "edit",
          label: "Edit…",
          icon: Pencil,
          testId: ElementIds.LAYOUTS_MORE_OPTIONS_EDIT,
          disabled: isSystem,
          danger: false,
          separatorBefore: false,
          run: () => openEdit(layout),
        },
        {
          key: "delete",
          label: "Delete",
          icon: Trash2,
          testId: ElementIds.LAYOUTS_MORE_OPTIONS_DELETE,
          disabled: isSystem,
          danger: true,
          separatorBefore: false,
          run: () => removeLayout(layout),
        },
      ];
    },
    [apply, defaultLayoutId, setDefaultLayout, openEdit, removeLayout],
  );

  const moreOptionsItems: ReadonlyArray<LayoutMenuItem> = useMemo(
    () => (highlighted === undefined ? [] : buildLayoutItems(highlighted)),
    [highlighted, buildLayoutItems],
  );

  // Keyboard (capture phase, so it wins over the global handler).
  // The capture listener is mounted once and reads live state through this ref;
  // it's refreshed after every commit so the handler never closes over stale
  // values (writing the ref in an effect keeps render side-effect-free).
  const stateRef = useRef({
    filtered,
    highlighted,
    moreOptionsOpen: isMoreOptionsOpen,
    query,
    openLayoutsBinding,
    moreOptionsBinding,
    apply,
    openSave,
    close,
  });
  useEffect(() => {
    stateRef.current = {
      filtered,
      highlighted,
      moreOptionsOpen: isMoreOptionsOpen,
      query,
      openLayoutsBinding,
      moreOptionsBinding,
      apply,
      openSave,
      close,
    };
  });

  useEffect(() => {
    const handler = (event: KeyboardEvent): void => {
      const state = stateRef.current;

      if (event.key === "Escape") {
        // While the more-options menu is open, Radix's DropdownMenu owns Escape: it
        // closes the menu (the highest dismissable layer) and returns focus. Bail so
        // we neither double-close nor swallow the event before Radix's document
        // listener sees it.
        if (state.moreOptionsOpen) {
          return;
        }
        // Otherwise Escape clears a query first, then closes the dialog — stopping
        // Radix from closing the whole dialog while there's a lighter step to take.
        event.preventDefault();
        event.stopPropagation();
        if (state.query !== "") {
          setQuery("");
          setHighlightIndex(0);
        } else {
          state.close();
        }
        return;
      }

      // ⌘⇧L: advance the highlight (double-tap bounce). The more-options menu is
      // scoped to one layout, so cycling the list means leaving it — close it first.
      if (state.openLayoutsBinding != null && shouldHandleKeybinding(event, state.openLayoutsBinding)) {
        event.preventDefault();
        event.stopPropagation();
        setIsMoreOptionsOpen(false);
        if (state.filtered.length > 0) {
          setHighlightIndex((index) => (index + 1) % state.filtered.length);
        }
        return;
      }

      // ⌘J: toggle the more-options menu for the highlighted layout.
      if (state.moreOptionsBinding != null && shouldHandleKeybinding(event, state.moreOptionsBinding)) {
        event.preventDefault();
        event.stopPropagation();
        if (state.moreOptionsOpen) {
          setIsMoreOptionsOpen(false);
        } else if (state.highlighted !== undefined) {
          setIsMoreOptionsOpen(true);
        }
        return;
      }

      const isMod = event.metaKey || event.ctrlKey;

      // ⌘S: save the current arrangement. openSave closes the whole switcher, so an
      // open more-options menu is torn down with it.
      if (isMod && !event.shiftKey && !event.altKey && event.key.toLowerCase() === "s") {
        event.preventDefault();
        event.stopPropagation();
        state.openSave();
        return;
      }

      // While the menu is open, Radix owns navigation inside it (arrows / Enter /
      // typeahead); the switcher's list navigation below must stay dormant.
      if (state.moreOptionsOpen) {
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

  // Focus the search input on open.
  useEffect(() => {
    searchInputRef.current?.focus();
  }, []);

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
          Save current arrangement
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
          {/* The ⌘J menu targets the highlighted layout — the same descriptors each
              row's right-click ContextMenu feeds from, so the two surfaces stay in
              lock-step. Radix Themes DropdownMenu.Trigger renders its single child as
              the trigger (applies asChild internally), so the Button keeps its full
              menu aria wiring. */}
          <DropdownMenu.Root open={isMoreOptionsOpen} onOpenChange={setIsMoreOptionsOpen}>
            <DropdownMenu.Trigger>
              <Button
                type="button"
                variant="ghost"
                size="1"
                color="gray"
                className={`${styles.barButton} ${isMoreOptionsOpen ? styles.barButtonActive : ""}`}
                disabled={highlighted === undefined}
                data-testid={ElementIds.LAYOUTS_SWITCHER_MORE_OPTIONS_BUTTON}
              >
                More options
                <ShortcutHint binding={moreOptionsBinding ?? ""} className={styles.barKbd} />
              </Button>
            </DropdownMenu.Trigger>
            {highlighted !== undefined ? (
              <DropdownMenu.Content
                size="1"
                // Radix returns focus to the trigger on close; redirect it to the
                // search input so type-to-filter keeps working the instant the menu
                // closes (⌘J-again, Escape, or picking an item).
                onCloseAutoFocus={(event): void => {
                  event.preventDefault();
                  searchInputRef.current?.focus();
                }}
                data-testid={ElementIds.LAYOUTS_MORE_OPTIONS_POPOVER}
              >
                {moreOptionsItems.map((item) => (
                  <Fragment key={item.key}>
                    {item.separatorBefore ? <DropdownMenu.Separator /> : null}
                    <DropdownMenu.Item
                      color={item.danger ? dangerColor : undefined}
                      disabled={item.disabled}
                      shortcut={item.shortcut !== undefined ? formatShortcutForDisplay(item.shortcut) : undefined}
                      onSelect={() => item.run()}
                      data-testid={item.testId}
                    >
                      <item.icon size={14} />
                      {item.label}
                    </DropdownMenu.Item>
                  </Fragment>
                ))}
              </DropdownMenu.Content>
            ) : null}
          </DropdownMenu.Root>
        </div>
      </div>
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
  items: ReadonlyArray<LayoutMenuItem>;
  selected: boolean;
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
      onClick={(): void => onClick()}
      data-testid={ElementIds.LAYOUTS_SWITCHER_ROW}
      data-layout-id={layout.id}
      data-selected={selected}
    >
      <span className={styles.rowIcon}>
        <LayoutWireframeIcon captured={layout.captured} />
      </span>
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
    </div>
  );

  return (
    <ContextMenu.Root>
      <ContextMenu.Trigger>{row}</ContextMenu.Trigger>
      <ContextMenu.Content size="1" data-testid={ElementIds.LAYOUTS_ROW_CONTEXT_MENU}>
        {items.map((item) => (
          <Fragment key={item.key}>
            {item.separatorBefore ? <ContextMenu.Separator /> : null}
            <ContextMenu.Item
              color={item.danger ? dangerColor : undefined}
              disabled={item.disabled}
              shortcut={item.shortcut !== undefined ? formatShortcutForDisplay(item.shortcut) : undefined}
              onSelect={() => item.run()}
              data-testid={item.testId}
            >
              {item.label}
            </ContextMenu.Item>
          </Fragment>
        ))}
      </ContextMenu.Content>
    </ContextMenu.Root>
  );
};
