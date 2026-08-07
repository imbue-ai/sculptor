// Atom-driven host for the Layouts switcher, mounted once in AppShell (the New
// Workspace modal pattern). Renders nothing when closed, so the switcher's internal
// state resets fresh on every open.

import { useAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useEffect } from "react";

import { ElementIds } from "~/api";
import { PaletteDialog } from "~/components/PaletteDialog/PaletteDialog.tsx";

import { LayoutSwitcher } from "./LayoutSwitcher.tsx";
import { layoutsSwitcherOpenAtom } from "./layoutUiAtoms.ts";

export const LayoutsModal = (): ReactElement | undefined => {
  const [isOpen, setIsOpen] = useAtom(layoutsSwitcherOpenAtom);

  // Close on unmount so a stale open request can't outlive this host.
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
      title="Layouts"
      testId={ElementIds.LAYOUTS_SWITCHER_DIALOG}
    >
      <LayoutSwitcher />
    </PaletteDialog>
  );
};
