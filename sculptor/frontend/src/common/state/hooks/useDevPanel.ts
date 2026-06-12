import { useAtom } from "jotai";

import { devPanelOpenAtom } from "../atoms/devPanel.ts";

type DevPanelControls = {
  isDevPanelOpen: boolean;
  showDevPanel: () => void;
  hideDevPanel: () => void;
  toggleDevPanel: () => void;
};

export const useDevPanel = (): DevPanelControls => {
  const [isDevPanelOpen, setIsDevPanelOpen] = useAtom(devPanelOpenAtom);

  return {
    isDevPanelOpen,
    showDevPanel: () => setIsDevPanelOpen(true),
    hideDevPanel: () => setIsDevPanelOpen(false),
    toggleDevPanel: () => setIsDevPanelOpen((prev) => !prev),
  };
};
