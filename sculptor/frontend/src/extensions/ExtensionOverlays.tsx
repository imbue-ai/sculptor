import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import { extensionOverlaysAtom } from "./extensionRegistry.ts";

/**
 * Renders every extension-contributed overlay (`api.registerOverlay`) above the
 * whole app. Mounted once from `AppShell`, so overlays live *inside* the
 * host's Router and Jotai/Theme/QueryClient providers — that is what lets an
 * overlay use route- and store-backed SDK hooks (`useCurrentWorkspaceId`,
 * `useWorkspaces`) even though it floats across every route.
 *
 * The layer is a fixed, full-viewport, click-through (`pointer-events: none`)
 * container; each overlay must re-enable pointer events on its own interactive
 * box. Entries are already wrapped by the loader in an error boundary and the
 * extension's ExtensionContext.
 */
export const ExtensionOverlays = (): ReactElement | null => {
  const overlays = useAtomValue(extensionOverlaysAtom);
  if (overlays.length === 0) return null;
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        pointerEvents: "none",
        // Above app chrome; intentionally below Radix dialogs/popovers, which
        // sit higher. Revisit if an overlay needs to cover modal content.
        zIndex: 50,
      }}
    >
      {overlays.map(({ id, component: Overlay }) => (
        <Overlay key={id} />
      ))}
    </div>
  );
};
