// The "Apply & tidy" confirmation. Driven by layoutTidyTargetAtom, which the
// switcher sets right after applying a layout. It lists exactly the static panels
// that would close and reassures that agents/terminals never do. When
// nothing would close it applies silently — clearing the target without ever
// rendering — so ↵/Apply & tidy on an already-tidy workspace is a no-op.

import { AlertDialog } from "@radix-ui/themes";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { ShieldCheck } from "lucide-react";
import type { ReactElement } from "react";
import { createElement } from "react";
import { useEffect, useMemo } from "react";

import { ElementIds } from "~/api";
import { ConfirmationDialog } from "~/components/ConfirmationDialog.tsx";
import { tidyToLayoutAtom } from "~/components/sections/layoutActions.ts";
import { computeTidyClosure } from "~/components/sections/layoutApply.ts";
import { panelRegistryAtom } from "~/components/sections/registry/panelRegistry.ts";
import { workspaceLayoutAtom } from "~/components/sections/sectionAtoms.ts";
import { toSection } from "~/components/sections/sectionTypes.ts";
import { layoutTidyTargetAtom } from "~/components/sections/transientAtoms.ts";

import styles from "./LayoutTidyConfirmation.module.scss";

export const LayoutTidyConfirmation = (): ReactElement | undefined => {
  const [target, setTarget] = useAtom(layoutTidyTargetAtom);
  const layout = useAtomValue(workspaceLayoutAtom);
  const registry = useAtomValue(panelRegistryAtom);
  const tidyToLayout = useSetAtom(tidyToLayoutAtom);

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
    setTarget(null);
  };

  const count = closure.length;
  const countLabel = count === 1 ? "1 panel" : `${count} panels`;

  return (
    <ConfirmationDialog
      open
      onOpenChange={(open) => (open ? undefined : setTarget(null))}
      title={`Close ${countLabel}?`}
      confirmLabel={`Close ${countLabel}`}
      onConfirm={handleConfirm}
      isDanger
      maxWidth="420px"
      dialogTestId={ElementIds.LAYOUT_TIDY_DIALOG}
      cancelTestId={ElementIds.LAYOUT_TIDY_CANCEL}
      confirmTestId={ElementIds.LAYOUT_TIDY_CONFIRM}
    >
      <AlertDialog.Description className={styles.body}>
        Tidying matches this workspace to <strong>{target.name}</strong>. Panels the layout doesn’t include will close:
      </AlertDialog.Description>
      <ul className={styles.closeList}>
        {closure.map(({ panelId, subSection }) => {
          const definition = registry.find((candidate) => candidate.id === panelId);
          const name = definition?.displayName ?? panelId;
          return (
            <li key={panelId} className={styles.closeItem}>
              {definition !== undefined ? createElement(definition.icon, { size: 15 }) : null}
              {name}
              <span className={styles.closeItemSection}>{toSection(subSection)} section</span>
            </li>
          );
        })}
      </ul>
      <div className={styles.reassure}>
        <ShieldCheck size={14} />
        Your agents and terminals are never closed.
      </div>
    </ConfirmationDialog>
  );
};
