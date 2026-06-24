import type { PluginHostApi } from "@sculptor/plugin-sdk";
import { Hash } from "lucide-react";

import { LinearPanel } from "./components/LinearPanel.tsx";
import { LinearSettings } from "./components/LinearSettings.tsx";
import { WorkspaceShortcutWidget } from "./components/WorkspaceShortcutWidget.tsx";
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
    component: LinearPanel,
  });
  const disposeSettings = api.registerSettings(LinearSettings);
  // The banner shortcut: a compact ticket reference beside the PR button,
  // sharing the panel's per-workspace `shortcut` state. collapsePriority 3 sits
  // between the host's repo (2) and PR (4) items, so it collapses before the PR
  // button but after the repo breadcrumb when the banner runs out of room.
  const disposeWidget = api.registerWorkspaceWidget({
    id: PLUGIN_ID,
    component: WorkspaceShortcutWidget,
    collapsePriority: 3,
  });
  return (): void => {
    disposePanel();
    disposeSettings();
    disposeWidget();
  };
}
