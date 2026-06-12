import { useAtom } from "jotai";

import { helpDialogOpenAtom } from "../atoms/helpDialog.ts";

type HelpDialogControls = {
  isHelpDialogOpen: boolean;
  showHelpDialog: () => void;
  hideHelpDialog: () => void;
  toggleHelpDialog: () => void;
};

export const useHelpDialog = (): HelpDialogControls => {
  const [isHelpDialogOpen, setIsHelpDialogOpen] = useAtom(helpDialogOpenAtom);

  return {
    isHelpDialogOpen,
    showHelpDialog: () => setIsHelpDialogOpen(true),
    hideHelpDialog: () => setIsHelpDialogOpen(false),
    toggleHelpDialog: () => setIsHelpDialogOpen((prev) => !prev),
  };
};
