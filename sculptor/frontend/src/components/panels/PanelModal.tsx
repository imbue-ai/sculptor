import { Dialog } from "@radix-ui/themes";
import { useAtom } from "jotai";
import type { ReactElement } from "react";
import { memo } from "react";

import { modalPanelIdAtom } from "~/components/panels/atoms.ts";
import { usePanelById } from "~/components/panels/hooks.ts";

import styles from "./PanelModal.module.scss";

const PanelModalInner = (): ReactElement => {
  const [modalPanelId, setModalPanelId] = useAtom(modalPanelIdAtom);
  const panelDef = usePanelById(modalPanelId);
  const isOpen = modalPanelId !== null && panelDef !== undefined;

  const handleOpenChange = (open: boolean): void => {
    if (!open) {
      setModalPanelId(null);
    }
  };

  return (
    <Dialog.Root open={isOpen} onOpenChange={handleOpenChange}>
      <Dialog.Content className={styles.content} aria-describedby={undefined}>
        {panelDef && (
          <>
            <Dialog.Title>{panelDef.displayName}</Dialog.Title>
            <panelDef.component />
          </>
        )}
      </Dialog.Content>
    </Dialog.Root>
  );
};

export const PanelModal = memo(PanelModalInner);
PanelModal.displayName = "PanelModal";
