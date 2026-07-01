import type { PluginHostApi } from "@sculptor/plugin-sdk";
import { Hash, LayoutList } from "lucide-react";

import { LinearBoard } from "./components/LinearBoard.tsx";
import { LinearPanel } from "./components/LinearPanel.tsx";
import { LinearSettings } from "./components/LinearSettings.tsx";
import { WorkspaceTicketWidget } from "./components/WorkspaceTicketWidget.tsx";
import { PLUGIN_ID } from "./constants.ts";

// `activate` is the plugin entry point. The host calls it once after loading
// the bundle; the returned function disposes the contributions on unload.
export default function activate(api: PluginHostApi): () => void {
  const disposePanel = api.registerPanel({
    id: PLUGIN_ID,
    displayName: "Linear",
    description: "Linear issues linked to this workspace — by branch, PR, or pinned",
    icon: Hash,
    defaultZone: "top-right",
    defaultShortcut: "",
    // Registered but off by default: a bundled, on-by-default plugin shouldn't
    // claim a slot in everyone's panel layout uninvited. The workspace banner
    // widget below is the always-on surface; users opt the panel in from
    // Settings → Panels (like the built-in Browser panel).
    defaultEnabled: false,
    component: LinearPanel,
  });
  const disposeSettings = api.registerSettings(LinearSettings);
  // The banner ticket chip: a compact ticket reference beside the PR button,
  // sharing the panel's per-workspace ticket-assignment state. collapsePriority 3
  // sits between the host's repo (2) and PR (4) items, so it collapses before the
  // PR button but after the repo breadcrumb when the banner runs out of room.
  const disposeWidget = api.registerWorkspaceWidget({
    id: PLUGIN_ID,
    component: WorkspaceTicketWidget,
    collapsePriority: 3,
  });
  // The homepage board: the user's assigned issues grouped by state, each
  // flagged with whether a workspace already exists for it. Selectable from the
  // home view switcher the host shows once any plugin contributes a home view.
  const disposeHomeView = api.registerHomeView({
    id: PLUGIN_ID,
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
