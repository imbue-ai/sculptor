import { useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useEffect } from "react";

import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import type { PanelDefinition } from "~/components/panels/types.ts";

import { installHostRuntime } from "./hostRuntime.ts";
import { PluginErrorBoundary } from "./PluginErrorBoundary.tsx";
import { loadedPluginManifestsAtom, pluginLoadErrorsAtom, pluginPanelsAtom } from "./pluginRegistry.ts";
import type { LoadedPlugin, PluginHostApi, PluginLoadError, PluginManifest, PluginModule } from "./types.ts";
import { WorkspacePluginContext } from "./WorkspaceContext.tsx";

/**
 * Plugins to load at boot. In a real implementation this would come from a
 * user-managed list and a discovery API; for the prototype we hard-code
 * one entry pointing at the bundle the workspace-cost-tracker plugin
 * builds into the host's `public/plugins/` tree.
 */
const BUILTIN_PLUGIN_MANIFEST_URLS: ReadonlyArray<string> = ["/plugins/workspace-cost-tracker/manifest.json"];

/** SDK major version the host currently provides. */
const HOST_SDK_VERSION = 1;

const parseMajor = (range: string): number | null => {
  const match = range.match(/(\d+)/);
  return match ? Number(match[1]) : null;
};

const validateManifest = (manifest: PluginManifest): Error | null => {
  if (!manifest.id || !manifest.entry || !manifest.sdkVersion) {
    return new Error("Manifest missing required fields (id, entry, sdkVersion)");
  }
  const major = parseMajor(manifest.sdkVersion);
  if (major === null) {
    return new Error(`Unparseable sdkVersion "${manifest.sdkVersion}"`);
  }

  if (major !== HOST_SDK_VERSION) {
    return new Error(`Plugin requires SDK major ${major}, host provides ${HOST_SDK_VERSION}`);
  }
  return null;
};

const loadOne = async (
  manifestUrl: string,
  registerPanel: (panel: PanelDefinition) => () => void,
): Promise<LoadedPlugin | PluginLoadError> => {
  let manifest: PluginManifest;
  try {
    const res = await fetch(manifestUrl, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    manifest = (await res.json()) as PluginManifest;
  } catch (e) {
    return {
      manifest: { id: manifestUrl, name: manifestUrl, version: "?", entry: "", sdkVersion: "?" },
      phase: "manifest",
      error: e instanceof Error ? e : new Error(String(e)),
    };
  }

  const validationError = validateManifest(manifest);
  if (validationError) {
    return { manifest, phase: "validate", error: validationError };
  }

  const entryBase = manifestUrl.replace(/\/manifest\.json$/, "");
  const entryUrl = new URL(manifest.entry, window.location.origin + entryBase + "/").toString();

  let mod: PluginModule;
  try {
    mod = (await import(/* @vite-ignore */ entryUrl)) as PluginModule;
  } catch (e) {
    return { manifest, phase: "import", error: e instanceof Error ? e : new Error(String(e)) };
  }

  if (typeof mod.default !== "function") {
    return {
      manifest,
      phase: "activate",
      error: new Error("Plugin entry has no default-exported activate() function"),
    };
  }

  const api: PluginHostApi = { registerPanel };
  try {
    const result = await mod.default(api);
    const dispose = typeof result === "function" ? result : undefined;
    return { manifest, dispose };
  } catch (e) {
    return { manifest, phase: "activate", error: e instanceof Error ? e : new Error(String(e)) };
  }
};

/**
 * Mounts once at app root. Installs the host runtime singletons, fetches
 * each builtin plugin's manifest, validates it, dynamic-imports the bundle,
 * and invokes the plugin's `activate()` function. Contributions land in
 * the plugin registry atoms which downstream consumers read from.
 */
export const PluginLoader = (): ReactElement | null => {
  const setPanels = useSetAtom(pluginPanelsAtom);
  const setManifests = useSetAtom(loadedPluginManifestsAtom);
  const setErrors = useSetAtom(pluginLoadErrorsAtom);

  useEffect(() => {
    installHostRuntime();

    let isDisposed = false;
    const disposers: Array<() => void> = [];

    const registerPanel = (panel: PanelDefinition): (() => void) => {
      // Wrap the plugin's component in the error boundary plus a context
      // provider that exposes the current workspace id to SDK hooks. Both
      // run at render time, so the workspace id is read fresh per render
      // from the route params.
      const PluginComponent = panel.component;
      const Wrapped = (): ReactElement | null => {
        const { workspaceID } = useWorkspacePageParams();
        if (!workspaceID) return null;
        return (
          <PluginErrorBoundary pluginId={panel.id} pluginName={panel.displayName}>
            <WorkspacePluginContext.Provider value={{ workspaceId: workspaceID }}>
              <PluginComponent />
            </WorkspacePluginContext.Provider>
          </PluginErrorBoundary>
        );
      };
      Wrapped.displayName = `PluginPanel(${panel.id})`;
      const wrappedPanel: PanelDefinition = { ...panel, component: Wrapped };

      setPanels((prev) => [...prev, wrappedPanel]);
      const undo = (): void => {
        setPanels((prev) => prev.filter((p) => p.id !== panel.id));
      };
      disposers.push(undo);
      return undo;
    };

    void (async (): Promise<void> => {
      for (const url of BUILTIN_PLUGIN_MANIFEST_URLS) {
        const outcome = await loadOne(url, registerPanel);
        if (isDisposed) {
          if ("dispose" in outcome && outcome.dispose) outcome.dispose();
          return;
        }

        if ("phase" in outcome) {
          console.error(`Plugin load failed (${outcome.phase})`, outcome);
          setErrors((prev) => [...prev, outcome]);
        } else {
          if (outcome.dispose) disposers.push(outcome.dispose);
          setManifests((prev) => [...prev, outcome.manifest]);
        }
      }
    })();

    return (): void => {
      isDisposed = true;
      for (const d of disposers) {
        try {
          d();
        } catch (e) {
          console.error("Plugin disposer threw", e);
        }
      }
    };
  }, [setPanels, setManifests, setErrors]);

  return null;
};
