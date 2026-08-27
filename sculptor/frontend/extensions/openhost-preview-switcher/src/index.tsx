import type { ExtensionHostApi } from "@sculptor/extension-sdk";

import { PreviewSwitcherOverlay } from "./overlay.tsx";

/**
 * Preview Switcher — an OpenHost-only helper for hopping between the deployed
 * web app and the Vite dev previews served behind the nginx `/proxy/<port>/`
 * front (see openhost-nginx.conf at the repo root). It renders a small pill in
 * the page's bottom-left dev strip area; see overlay.tsx for the behavior.
 *
 * Deliberately NOT in BUILTIN_SOURCES: on non-OpenHost deployments it would
 * only ever hide itself. On an OpenHost box it is installed as a local extension
 * (openhost-run.sh copies the built `manifest.json` + `main.js` into the
 * backend's `<sculptor-folder>/extensions/openhost-preview-switcher/` on every
 * boot), which also survives image rebuilds there because the sculptor folder
 * lives on the persistent volume.
 */
export default function activate(api: ExtensionHostApi): () => void {
  return api.registerOverlay({ id: "openhost-preview-switcher", component: PreviewSwitcherOverlay });
}
