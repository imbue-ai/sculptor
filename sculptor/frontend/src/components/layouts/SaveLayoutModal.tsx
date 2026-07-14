// The "Save current arrangement as a layout" dialog, on the PaletteDialog shell.
// A name field (styled as the heading), a mini capture preview that shows what the
// layout stores (solid cells = saved static panels; dashed chips mark where default
// seeding creates an agent/terminal), then a clean options list — an inline keyboard
// shortcut, a "tidy panels when applying" toggle, and "set as default" — and Save
// (⌘↵). Atom-driven host, mounted in AppShell.

import { Button, Switch } from "@radix-ui/themes";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ElementIds } from "~/api";
import { useLayoutBindingConflict, useSetLayoutShortcut } from "~/common/keybindings/useLayoutShortcutActions.ts";
import { formatShortcutForDisplay } from "~/common/ShortcutUtils.ts";
import { PaletteDialog } from "~/components/PaletteDialog/PaletteDialog.tsx";
import { saveCurrentLayoutAtom } from "~/components/sections/layoutActions.ts";
import { openPanelsInSubSection, SECTION_LABELS } from "~/components/sections/layoutQueries.ts";
import { isMultiInstancePanelId } from "~/components/sections/registry/dynamicPanels.tsx";
import { panelRegistryAtom } from "~/components/sections/registry/panelRegistry.ts";
import { workspaceLayoutAtom } from "~/components/sections/sectionAtoms.ts";
import type { PanelId, SectionId } from "~/components/sections/sectionTypes.ts";
import { toSecondary } from "~/components/sections/sectionTypes.ts";
import { HotkeyChip } from "~/pages/settings/components/HotkeyChip.tsx";

import { saveLayoutModalOpenAtom } from "./layoutUiAtoms.ts";
import styles from "./SaveLayoutModal.module.scss";

const SAVE_HINT = formatShortcutForDisplay("Meta+Enter");

export const SaveLayoutModal = (): ReactElement | undefined => {
  const [isOpen, setIsOpen] = useAtom(saveLayoutModalOpenAtom);

  useEffect(() => (): void => setIsOpen(false), [setIsOpen]);

  const handleOpenChange = useCallback(
    (next: boolean): void => {
      if (!next) {
        setIsOpen(false);
      }
    },
    [setIsOpen],
  );

  if (!isOpen) {
    return undefined;
  }

  return (
    <PaletteDialog
      open={isOpen}
      onOpenChange={handleOpenChange}
      title="Save layout"
      testId={ElementIds.SAVE_LAYOUT_DIALOG}
    >
      <SaveLayoutForm onClose={() => setIsOpen(false)} />
    </PaletteDialog>
  );
};

const SaveLayoutForm = ({ onClose }: { onClose: () => void }): ReactElement => {
  const [name, setName] = useState<string>("");
  const [isSetAsDefault, setIsSetAsDefault] = useState<boolean>(false);
  const [shouldTidyOnApply, setShouldTidyOnApply] = useState<boolean>(false);
  // The shortcut is held locally while the Layout has no id yet; it's persisted to
  // userConfig.keybindings (keyed by the new Layout's id) only on Save.
  const [shortcut, setShortcut] = useState<string | undefined>(undefined);
  const [shortcutConflict, setShortcutConflict] = useState<string | null>(null);
  const saveCurrentLayout = useSetAtom(saveCurrentLayoutAtom);
  const setLayoutShortcut = useSetLayoutShortcut();
  const findBindingConflict = useLayoutBindingConflict();
  const nameInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    nameInputRef.current?.focus();
  }, []);

  const canSave = name.trim() !== "";

  const handleSave = useCallback((): void => {
    if (!canSave) {
      return;
    }
    const id = saveCurrentLayout({ name: name.trim(), setAsDefault: isSetAsDefault, tidyOnApply: shouldTidyOnApply });
    if (shortcut !== undefined) {
      void setLayoutShortcut(id, shortcut);
    }
    onClose();
  }, [canSave, saveCurrentLayout, name, isSetAsDefault, shouldTidyOnApply, shortcut, setLayoutShortcut, onClose]);

  // No id exists yet, so guard against every existing binding (empty self id).
  const handleShortcutRecord = useCallback(
    (chord: string): boolean => {
      const conflict = findBindingConflict(chord, "");
      if (conflict !== null) {
        setShortcutConflict(conflict.name);
        return false;
      }
      setShortcutConflict(null);
      return true;
    },
    [findBindingConflict],
  );

  const clearShortcut = useCallback((): void => {
    setShortcut(undefined);
    setShortcutConflict(null);
  }, []);

  return (
    <div
      onKeyDown={(event) => {
        if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
          event.preventDefault();
          handleSave();
        }
      }}
    >
      <div className={styles.body}>
        <input
          ref={nameInputRef}
          className={styles.titleInput}
          placeholder="Name this layout"
          value={name}
          onChange={(event) => setName(event.target.value)}
          data-testid={ElementIds.SAVE_LAYOUT_NAME_INPUT}
          aria-label="Layout name"
        />
        <SaveLayoutPreview />
        <div className={styles.legend}>
          An agent is created by default in the center section. A terminal is created by default in the bottom section.
        </div>
        <div className={styles.options}>
          <div className={styles.optionRow}>
            <div className={styles.optionLabel}>
              <span className={styles.optionTitle}>Keyboard shortcut</span>
              <span className={styles.optionSub}>Apply this layout with a keypress.</span>
            </div>
            <div className={styles.optionControl} data-testid={ElementIds.SAVE_LAYOUT_SHORTCUT}>
              <HotkeyChip
                value={shortcut}
                onSet={setShortcut}
                onClear={clearShortcut}
                onRecordComplete={handleShortcutRecord}
                idleLabel="Set keyboard shortcut"
                setLabel="Update keyboard shortcut"
              />
            </div>
          </div>
          {shortcutConflict !== null ? (
            <div className={styles.shortcutWarning}>Already assigned to “{shortcutConflict}”. Pick another.</div>
          ) : null}
          <div className={styles.optionRow}>
            <div className={styles.optionLabel}>
              <span className={styles.optionTitle}>Tidy panels when applying</span>
              <span className={styles.optionSub}>
                Closes panels this layout doesn’t include — never agents or terminals.
              </span>
            </div>
            <div className={styles.optionControl}>
              <Switch
                size="1"
                checked={shouldTidyOnApply}
                onCheckedChange={setShouldTidyOnApply}
                data-testid={ElementIds.SAVE_LAYOUT_TIDY_SWITCH}
              />
            </div>
          </div>
          <div className={styles.optionRow}>
            <div className={styles.optionLabel}>
              <span className={styles.optionTitle}>Set as default for new workspaces</span>
            </div>
            <div className={styles.optionControl}>
              <Switch
                size="1"
                checked={isSetAsDefault}
                onCheckedChange={setIsSetAsDefault}
                data-testid={ElementIds.SAVE_LAYOUT_DEFAULT_SWITCH}
              />
            </div>
          </div>
        </div>
        <div className={styles.optionNote}>Change or clear layout shortcuts anytime in Settings ▸ Keybindings.</div>
      </div>
      <div className={styles.footer}>
        <span className={styles.saveHint}>{SAVE_HINT} to save</span>
        <Button variant="solid" disabled={!canSave} onClick={handleSave} data-testid={ElementIds.SAVE_LAYOUT_SUBMIT}>
          Save layout
        </Button>
      </div>
    </div>
  );
};

const PREVIEW_SECTIONS: ReadonlyArray<{ section: SectionId; areaClass: string }> = [
  { section: "left", areaClass: styles.cellLeft },
  { section: "center", areaClass: styles.cellCenter },
  { section: "right", areaClass: styles.cellRight },
  { section: "bottom", areaClass: styles.cellBottom },
];

// A layout never declares agents/terminals; default seeding creates them in fixed
// sections. The preview marks those homes with a dashed chip.
const DEFAULT_DYNAMIC_CHIPS: Partial<Record<SectionId, string>> = {
  center: "Agent default",
  bottom: "Terminal default",
};

const SaveLayoutPreview = (): ReactElement => {
  const layout = useAtomValue(workspaceLayoutAtom);
  const registry = useAtomValue(panelRegistryAtom);

  const nameOf = (id: PanelId): string => registry.find((definition) => definition.id === id)?.displayName ?? id;

  return (
    <div className={styles.preview}>
      {PREVIEW_SECTIONS.map(({ section, areaClass }) => {
        const ids = [
          ...openPanelsInSubSection(layout, section),
          ...openPanelsInSubSection(layout, toSecondary(section)),
        ];
        const statics = ids.filter((id) => !isMultiInstancePanelId(id));
        const activeId = layout.activePanel[section];
        const defaultChip = DEFAULT_DYNAMIC_CHIPS[section];

        return (
          <div
            key={section}
            className={`${styles.cell} ${statics.length > 0 ? styles.cellSaved : styles.cellStays} ${areaClass}`}
          >
            <div className={styles.cellLabel}>{SECTION_LABELS[section]}</div>
            {statics.length > 0 || defaultChip !== undefined ? (
              <div className={styles.cellTabs}>
                {statics.map((id) => (
                  <span key={id} className={`${styles.tab} ${id === activeId ? styles.tabActive : ""}`}>
                    {nameOf(id)}
                  </span>
                ))}
                {defaultChip !== undefined ? (
                  <span className={`${styles.tab} ${styles.tabDefault}`}>{defaultChip}</span>
                ) : undefined}
              </div>
            ) : undefined}
          </div>
        );
      })}
    </div>
  );
};
