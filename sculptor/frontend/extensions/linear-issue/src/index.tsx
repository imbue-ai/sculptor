import type { ExtensionHostApi } from "@sculptor/extension-sdk";
import { Hash, LayoutList } from "lucide-react";

import { LinearBoard } from "./components/LinearBoard.tsx";
import { LinearPanel } from "./components/LinearPanel.tsx";
import { LinearSettings } from "./components/LinearSettings.tsx";
import { WorkspaceTicketWidget } from "./components/WorkspaceTicketWidget.tsx";
import { EXTENSION_ID } from "./constants.ts";

// `activate` is the extension entry point. The host calls it once after loading
// the bundle; the returned function disposes the contributions on unload.
export default function activate(api: ExtensionHostApi): () => void {
  // The issues panel (Linear issues linked to this workspace — by branch, PR,
  // or pinned). Extension panels are not auto-placed: the user opens it from a
  // section's `+` add-panel dropdown (or Cmd+K), so a bundled extension never
  // claims a slot in anyone's layout uninvited. The workspace banner widget
  // below is the always-on surface.
  const disposePanel = api.registerPanel({
    id: EXTENSION_ID,
    displayName: "Linear",
    icon: Hash,
    description: "Linear issues linked to this workspace",
    component: LinearPanel,
  });
  const disposeSettings = api.registerSettings(LinearSettings);
  // The banner ticket chip: a compact ticket reference beside the PR button,
  // sharing the panel's per-workspace ticket-assignment state. collapsePriority
  // orders this widget among the other extension widgets when the banner runs out
  // of room (lower collapses first).
  const disposeWidget = api.registerWorkspaceWidget({
    id: EXTENSION_ID,
    component: WorkspaceTicketWidget,
    collapsePriority: 3,
  });
  // The homepage board: the user's assigned issues grouped by state, each
  // flagged with whether a workspace already exists for it. Selectable from the
  // home view switcher the host shows once any extension contributes a home view.
  const disposeHomeView = api.registerHomeView({
    id: EXTENSION_ID,
    title: "Linear board",
    icon: LayoutList,
    component: LinearBoard,
  });
  return (): void => {
    disposePanel();
    disposeSettings();
    disposeWidget();
    disposeHomeView();
  };
}
