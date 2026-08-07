// The "Apply & tidy" confirmation. Driven by layoutTidyTargetAtom, which the
// switcher sets right after applying a layout. It shows the workspace's section-grid
// preview with the panels that would close tinted red, and reassures that
// agents/terminals never do. When nothing would close it applies silently — clearing
// the target without ever rendering — so ↵/Apply & tidy on an already-tidy workspace
// is a no-op.
//
// A "Don't show this again" checkbox sets the global tidy-confirmation suppression
// (applyLayoutAtom then tidies silently for every layout thereafter), and — for the
// user's own layouts — an "Edit layout" link jumps into the save form to turn tidying
// off entirely.

import { AlertDialog, Checkbox } from "@radix-ui/themes";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useEffect, useMemo, useState } from "react";

import { ElementIds } from "~/api";
import { ConfirmationDialog } from "~/components/ConfirmationDialog.tsx";
import { tidyToLayoutAtom } from "~/components/sections/layoutActions.ts";
import { computeTidyClosure } from "~/components/sections/layoutApply.ts";
import { tidyConfirmationSuppressedAtom } from "~/components/sections/savedLayoutAtoms.ts";
import { workspaceLayoutAtom } from "~/components/sections/sectionAtoms.ts";
import type { SectionId } from "~/components/sections/sectionTypes.ts";
import { isSystemLayoutId } from "~/components/sections/systemDefaultLayout.ts";
import { layoutTidyTargetAtom } from "~/components/sections/transientAtoms.ts";

import { LayoutPreview } from "./LayoutPreview.tsx";
import styles from "./LayoutTidyConfirmation.module.scss";
import { saveLayoutModalRequestAtom } from "./layoutUiAtoms.ts";

// The tidy dialog shows the live workspace, so name the agent/terminal homes plainly
// (the save dialog's "default" framing is about seeding and doesn't apply here).
const TIDY_CHIPS: Partial<Record<SectionId, string>> = { center: "Agent", bottom: "Terminal" };

export const LayoutTidyConfirmation = (): ReactElement | undefined => {
  const [target, setTarget] = useAtom(layoutTidyTargetAtom);
  const layout = useAtomValue(workspaceLayoutAtom);
  const tidyToLayout = useSetAtom(tidyToLayoutAtom);
  const setTidyConfirmationSuppressed = useSetAtom(tidyConfirmationSuppressedAtom);
  const setSaveRequest = useSetAtom(saveLayoutModalRequestAtom);

  const [shouldSuppress, setShouldSuppress] = useState<boolean>(false);
  // Reset the checkbox for each fresh confirmation so it never carries a stale tick
  // from a previous layout. Adjusting state during render (rather than in an effect)
  // keeps the checkbox correct on the first paint of each new target.
  const [prevTargetId, setPrevTargetId] = useState<string | undefined>(target?.id);
  if (target?.id !== prevTargetId) {
    setPrevTargetId(target?.id);
    setShouldSuppress(false);
  }

  const closure = useMemo(() => (target === null ? [] : computeTidyClosure(layout, target.captured)), [target, layout]);

  // Nothing to close → apply silently: clear the target without rendering a dialog.
  useEffect(() => {
    if (target !== null && closure.length === 0) {
      setTarget(null);
    }
  }, [target, closure.length, setTarget]);

  if (target === null || closure.length === 0) {
    return undefined;
  }

  const handleConfirm = (): void => {
    tidyToLayout(target);
    if (shouldSuppress) {
      setTidyConfirmationSuppressed(true);
    }
    setTarget(null);
  };

  // Hand off to the save form in edit mode so the user can turn tidy off (or tweak
  // anything else); dismiss this dialog first so the two don't stack.
  const handleEdit = (): void => {
    setTarget(null);
    setSaveRequest({ mode: "edit", layout: target });
  };

  const count = closure.length;
  const countLabel = count === 1 ? "1 panel" : `${count} panels`;
  // Plain (not memoized) — hooks can't run after the early return above, and the set
  // is tiny. LayoutPreview reads it by membership, so identity churn is harmless.
  const removingPanelIds = new Set(closure.map((entry) => entry.panelId));

  return (
    <ConfirmationDialog
      open
      onOpenChange={(open) => (open ? undefined : setTarget(null))}
      title={`Close ${countLabel}?`}
      confirmLabel={`Close ${countLabel}`}
      onConfirm={handleConfirm}
      isDanger
      maxWidth="525px"
      dialogTestId={ElementIds.LAYOUT_TIDY_DIALOG}
      cancelTestId={ElementIds.LAYOUT_TIDY_CANCEL}
      confirmTestId={ElementIds.LAYOUT_TIDY_CONFIRM}
      footerStart={
        <label className={styles.dontShowAgain}>
          <Checkbox
            size="1"
            checked={shouldSuppress}
            onCheckedChange={(checked) => setShouldSuppress(checked === true)}
            data-testid={ElementIds.LAYOUT_TIDY_SUPPRESS_CHECKBOX}
          />
          Don’t show this again
        </label>
      }
    >
      <div className={styles.content}>
        <AlertDialog.Description className={styles.body}>
          Tidying matches this workspace to <strong>{target.name}</strong>. Panels the layout doesn’t include will
          close:
        </AlertDialog.Description>
        <LayoutPreview removingPanelIds={removingPanelIds} dynamicChips={TIDY_CHIPS} />
        <div className={styles.reassure}>Your agents and terminals are never closed.</div>
        {/* Built-in layouts are read-only (they always tidy by design), so the
          escape-hatch link only applies to the user's own layouts. */}
        {isSystemLayoutId(target.id) ? null : (
          <button
            type="button"
            className={styles.editLink}
            onClick={handleEdit}
            data-testid={ElementIds.LAYOUT_TIDY_EDIT_LINK}
          >
            Edit layout to turn off tidying
          </button>
        )}
      </div>
    </ConfirmationDialog>
  );
};
