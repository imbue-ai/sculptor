// The "Apply & tidy" confirmation. Driven by layoutTidyTargetAtom, which the
// switcher sets right after applying a layout. It lists exactly the static panels
// that would close and reassures that agents/terminals never do (design.md). When
// nothing would close it applies silently — clearing the target without ever
// rendering — so ↵/Apply & tidy on an already-tidy workspace is a no-op.

import { AlertDialog, Button, Flex } from "@radix-ui/themes";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { ShieldCheck } from "lucide-react";
import type { ReactElement } from "react";
import { createElement } from "react";
import { useEffect, useMemo, useRef } from "react";

import { ElementIds } from "~/api";
import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";
import { POPOVER_FRIENDLY_MODAL_ATTRIBUTE } from "~/components/popoverFriendlyModal.ts";
import { tidyToLayoutAtom } from "~/components/sections/layoutActions.ts";
import { computeTidyClosure } from "~/components/sections/layoutApply.ts";
import { panelRegistryAtom } from "~/components/sections/registry/panelRegistry.ts";
import { workspaceLayoutAtom } from "~/components/sections/sectionAtoms.ts";
import type { SectionId } from "~/components/sections/sectionTypes.ts";
import { toSection } from "~/components/sections/sectionTypes.ts";

import styles from "./LayoutTidyConfirmation.module.scss";
import { layoutTidyTargetAtom } from "./layoutUiAtoms.ts";

const SECTION_WORD: Readonly<Record<SectionId, string>> = {
  left: "left",
  center: "center",
  right: "right",
  bottom: "bottom",
};

export const LayoutTidyConfirmation = (): ReactElement | undefined => {
  const [target, setTarget] = useAtom(layoutTidyTargetAtom);
  const layout = useAtomValue(workspaceLayoutAtom);
  const registry = useAtomValue(panelRegistryAtom);
  const tidyToLayout = useSetAtom(tidyToLayoutAtom);
  const dangerColor = useThemeDangerColor();
  const confirmButtonRef = useRef<HTMLButtonElement>(null);

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

  const handleOpenAutoFocus = (event: Event): void => {
    event.preventDefault();
    confirmButtonRef.current?.focus();
  };

  const handleConfirm = (): void => {
    tidyToLayout(target);
    setTarget(null);
  };

  const count = closure.length;
  const countLabel = count === 1 ? "1 panel" : `${count} panels`;

  return (
    <AlertDialog.Root open onOpenChange={(open) => (open ? undefined : setTarget(null))}>
      <AlertDialog.Content
        maxWidth="420px"
        data-testid={ElementIds.LAYOUT_TIDY_DIALOG}
        {...{ [POPOVER_FRIENDLY_MODAL_ATTRIBUTE]: "true" }}
        onOpenAutoFocus={handleOpenAutoFocus}
      >
        <AlertDialog.Title>Close {countLabel}?</AlertDialog.Title>
        <AlertDialog.Description className={styles.body}>
          Tidying matches this workspace to <strong>{target.name}</strong>. Panels the layout doesn’t include will
          close:
        </AlertDialog.Description>
        <ul className={styles.closeList}>
          {closure.map(({ panelId, subSection }) => {
            const definition = registry.find((candidate) => candidate.id === panelId);
            const name = definition?.displayName ?? panelId;
            return (
              <li key={panelId} className={styles.closeItem}>
                {definition !== undefined ? createElement(definition.icon, { size: 15 }) : null}
                {name}
                <span className={styles.closeItemSection}>{SECTION_WORD[toSection(subSection)]} section</span>
              </li>
            );
          })}
        </ul>
        <div className={styles.reassure}>
          <ShieldCheck size={14} />
          Your agents and terminals are never closed.
        </div>
        <Flex gap="3" mt="4" justify="end">
          <AlertDialog.Cancel>
            <Button variant="soft" color="gray" data-testid={ElementIds.LAYOUT_TIDY_CANCEL}>
              Cancel
            </Button>
          </AlertDialog.Cancel>
          <AlertDialog.Action>
            <Button
              ref={confirmButtonRef}
              variant="solid"
              color={dangerColor}
              onClick={handleConfirm}
              data-testid={ElementIds.LAYOUT_TIDY_CONFIRM}
            >
              Close {countLabel}
            </Button>
          </AlertDialog.Action>
        </Flex>
      </AlertDialog.Content>
    </AlertDialog.Root>
  );
};
