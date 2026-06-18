import type { PluginHostApi } from "@sculptor/plugin-sdk";
import { Hash } from "lucide-react";

import { LinearPanel } from "./components/LinearPanel.tsx";
import { LinearSettings } from "./components/LinearSettings.tsx";
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
  return (): void => {
    disposePanel();
    disposeSettings();
  };
}
