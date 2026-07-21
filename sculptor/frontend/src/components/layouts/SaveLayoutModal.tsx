// The "Save current arrangement as a layout" dialog, on the PaletteDialog shell.
// A name field (styled as the heading), a mini capture preview that shows what the
// layout stores (solid cells = saved static panels; dashed chips mark where default
// seeding creates an agent/terminal), then a clean options list — an inline keyboard
// shortcut, a "tidy panels when applying" toggle, and "set as default" — and Save
// (⌘↵). The same form doubles as the Edit surface for an existing layout: opened in
// "edit" mode it prefills from the layout and updates its metadata on Save WITHOUT
// re-capturing the arrangement (the preview then shows the layout's stored panels).
// Atom-driven host, mounted in AppShell.

import { Button, Switch } from "@radix-ui/themes";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ElementIds } from "~/api";
import { layoutShortcutBindingsAtom } from "~/common/keybindings/layoutShortcuts.ts";
import { useLayoutBindingConflict, useSetLayoutShortcut } from "~/common/keybindings/useLayoutShortcutActions.ts";
import { formatShortcutForDisplay } from "~/common/ShortcutUtils.ts";
import { PaletteDialog } from "~/components/PaletteDialog/PaletteDialog.tsx";
import { saveCurrentLayoutAtom, updateLayoutAtom } from "~/components/sections/layoutActions.ts";
import { defaultLayoutIdAtom } from "~/components/sections/savedLayoutAtoms.ts";
import { HotkeyChip } from "~/pages/settings/components/HotkeyChip.tsx";

import { LayoutPreview } from "./LayoutPreview.tsx";
import type { SaveLayoutModalRequest } from "./layoutUiAtoms.ts";
import { saveLayoutModalRequestAtom } from "./layoutUiAtoms.ts";
import styles from "./SaveLayoutModal.module.scss";

const SAVE_HINT = formatShortcutForDisplay("Meta+Enter");

export const SaveLayoutModal = (): ReactElement | undefined => {
  const [request, setRequest] = useAtom(saveLayoutModalRequestAtom);

  useEffect(() => (): void => setRequest(null), [setRequest]);

  const handleOpenChange = useCallback(
    (next: boolean): void => {
      if (!next) {
        setRequest(null);
      }
    },
    [setRequest],
  );

  if (request === null) {
    return undefined;
  }

  const isEdit = request.mode === "edit";
  return (
    <PaletteDialog
      open
      onOpenChange={handleOpenChange}
      title={isEdit ? "Edit layout" : "Save layout"}
      testId={ElementIds.SAVE_LAYOUT_DIALOG}
    >
      {/* Keyed by mode+id so switching between create and editing different layouts
        remounts the form with fresh initial state rather than reusing stale values. */}
      <SaveLayoutForm
        key={isEdit ? `edit:${request.layout.id}` : "create"}
        request={request}
        onClose={() => setRequest(null)}
      />
    </PaletteDialog>
  );
};

const SaveLayoutForm = ({
  request,
  onClose,
}: {
  request: SaveLayoutModalRequest;
  onClose: () => void;
}): ReactElement => {
  const isEdit = request.mode === "edit";
  const editingLayout = request.mode === "edit" ? request.layout : undefined;

  const defaultLayoutId = useAtomValue(defaultLayoutIdAtom);
  const shortcutBindings = useAtomValue(layoutShortcutBindingsAtom);

  const [name, setName] = useState<string>(editingLayout?.name ?? "");
  const [isSetAsDefault, setIsSetAsDefault] = useState<boolean>(editingLayout?.id === defaultLayoutId);
  const [shouldTidyOnApply, setShouldTidyOnApply] = useState<boolean>(editingLayout?.tidyOnApply === true);
  // The shortcut is held locally while editing; it's persisted to
  // userConfig.keybindings (keyed by the Layout's id) only on Save. In create mode
  // there is no id yet, so it starts unset.
  const [shortcut, setShortcut] = useState<string | undefined>(
    editingLayout !== undefined ? shortcutBindings[editingLayout.id] : undefined,
  );
  const [shortcutConflict, setShortcutConflict] = useState<string | null>(null);
  const saveCurrentLayout = useSetAtom(saveCurrentLayoutAtom);
  const updateLayout = useSetAtom(updateLayoutAtom);
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

    if (editingLayout !== undefined) {
      updateLayout({
        id: editingLayout.id,
        name: name.trim(),
        setAsDefault: isSetAsDefault,
        tidyOnApply: shouldTidyOnApply,
      });
      void setLayoutShortcut(editingLayout.id, shortcut ?? null);
    } else {
      const id = saveCurrentLayout({ name: name.trim(), setAsDefault: isSetAsDefault, tidyOnApply: shouldTidyOnApply });
      if (shortcut !== undefined) {
        void setLayoutShortcut(id, shortcut);
      }
    }
    onClose();
  }, [
    canSave,
    editingLayout,
    updateLayout,
    saveCurrentLayout,
    name,
    isSetAsDefault,
    shouldTidyOnApply,
    shortcut,
    setLayoutShortcut,
    onClose,
  ]);

  // Guard the recorded chord against every OTHER binding — in edit mode a Layout may
  // keep its own current shortcut (pass its layout id as the "self" to skip; undefined
  // when creating, where there is nothing to skip).
  const handleShortcutRecord = useCallback(
    (chord: string): boolean => {
      const conflict = findBindingConflict(chord, editingLayout?.id);
      if (conflict !== null) {
        setShortcutConflict(conflict.name);
        return false;
      }
      setShortcutConflict(null);
      return true;
    },
    [findBindingConflict, editingLayout],
  );

  const clearShortcut = useCallback((): void => {
    setShortcut(undefined);
    setShortcutConflict(null);
  }, []);

  return (
    <div
      className={styles.form}
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
        <LayoutPreview source={editingLayout?.captured} />
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
          {isEdit ? "Save changes" : "Save layout"}
        </Button>
      </div>
    </div>
  );
};
