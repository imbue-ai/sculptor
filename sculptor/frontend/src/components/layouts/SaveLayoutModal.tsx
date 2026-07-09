// The "Save current arrangement as a layout" dialog, on the PaletteDialog shell.
// A name field (styled as the heading), a mini capture preview that shows what the
// layout stores (solid cells = saved static panels; dashed chips mark where default
// seeding creates an agent/terminal), a "set as default" switch, and Save (⌘↵).
// Atom-driven host, mounted in AppShell.

import { Button, Switch } from "@radix-ui/themes";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ElementIds } from "~/api";
import { formatShortcutForDisplay } from "~/common/ShortcutUtils.ts";
import { PaletteDialog } from "~/components/PaletteDialog/PaletteDialog.tsx";
import { saveCurrentLayoutAtom } from "~/components/sections/layoutActions.ts";
import { openPanelsInSubSection, SECTION_LABELS } from "~/components/sections/layoutQueries.ts";
import { isMultiInstancePanelId } from "~/components/sections/registry/dynamicPanels.tsx";
import { panelRegistryAtom } from "~/components/sections/registry/panelRegistry.ts";
import { workspaceLayoutAtom } from "~/components/sections/sectionAtoms.ts";
import type { PanelId, SectionId } from "~/components/sections/sectionTypes.ts";
import { toSecondary } from "~/components/sections/sectionTypes.ts";

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
  const saveCurrentLayout = useSetAtom(saveCurrentLayoutAtom);
  const nameInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    nameInputRef.current?.focus();
  }, []);

  const canSave = name.trim() !== "";

  const handleSave = useCallback((): void => {
    if (!canSave) {
      return;
    }
    saveCurrentLayout({ name, setAsDefault: isSetAsDefault });
    onClose();
  }, [canSave, saveCurrentLayout, name, isSetAsDefault, onClose]);

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
        <div className={styles.caption}>Saves this workspace’s panels and space as a reusable layout.</div>
        <SaveLayoutPreview />
        <div className={styles.legend}>
          An agent is created by default in the center section. A terminal is created by default in the bottom section.
        </div>
      </div>
      <div className={styles.footer}>
        <label className={styles.switchLabel}>
          <Switch
            size="1"
            checked={isSetAsDefault}
            onCheckedChange={setIsSetAsDefault}
            data-testid={ElementIds.SAVE_LAYOUT_DEFAULT_SWITCH}
          />
          Set as default for new workspaces
        </label>
        <div className={styles.footerRight}>
          <span className={styles.saveHint}>{SAVE_HINT} to save</span>
          <Button variant="solid" disabled={!canSave} onClick={handleSave} data-testid={ElementIds.SAVE_LAYOUT_SUBMIT}>
            Save layout
          </Button>
        </div>
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
