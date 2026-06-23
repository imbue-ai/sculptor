import { Badge, Button, Flex, IconButton, Spinner, Switch, Text, TextField, Tooltip } from "@radix-ui/themes";
import { useAtomValue, useStore } from "jotai";
import { Plus, RefreshCw, RotateCw, Settings2, Trash2 } from "lucide-react";
import { type ComponentType, type ReactElement, useEffect, useState } from "react";

import { ElementIds, getLocalPluginsDirectory } from "~/api";
import { healthCheckDataAtom } from "~/common/state/atoms/backend.ts";
import { Code } from "~/components/Code.tsx";
import { PluginContext } from "~/plugins/PluginContext.tsx";
import { PluginErrorBoundary } from "~/plugins/PluginErrorBoundary.tsx";
import { pluginManager } from "~/plugins/pluginManager.tsx";
import {
  pluginSettingsComponentsAtom,
  pluginSourcesAtom,
  type PluginSourceState,
  pluginSourceStatesAtom,
} from "~/plugins/pluginRegistry.ts";

import { SettingsSectionLayout } from "./SettingsSection.tsx";
import { inlineCodeStyle } from "./settingsStyles.ts";

// Last-resort label, shown only until either path source below resolves. The
// real directory varies by build/environment (`~/.sculptor`, a packaged dev
// `~/.dev-sculptor`, or a per-checkout `.dev_sculptor` from source), so this
// hardcoded guess is wrong on a dev/source build — hence the layered fallbacks.
const DEFAULT_PLUGINS_DIR = "~/.sculptor/plugins";

// Derive the plugins directory from the health check's data directory: the real
// path, just not home-collapsed. Used as a fallback when the dedicated endpoint
// isn't available (e.g. an older running backend), so we never show a hardcoded
// path that doesn't match this install. The separator follows the reported
// path's style so it reads correctly on Windows too.
const pluginsDirFromDataDirectory = (dataDirectory: string | null | undefined): string | null => {
  if (!dataDirectory) return null;
  const separator = dataDirectory.includes("\\") ? "\\" : "/";
  return `${dataDirectory.replace(/[/\\]+$/, "")}${separator}plugins`;
};

/**
 * Lists installed plugins and lets the user point Sculptor at additional plugin
 * sources (a URL serving a `manifest.json`). User sources are persisted to
 * localStorage and re-loaded on every boot.
 */
export const PluginsSettingsSection = (): ReactElement => {
  const store = useStore();
  const userSources = useAtomValue(pluginSourcesAtom);
  const states = useAtomValue(pluginSourceStatesAtom);
  const healthCheckData = useAtomValue(healthCheckDataAtom);
  const [draft, setDraft] = useState("");
  const [isBusy, setIsBusy] = useState(false);
  // The directory drop-in plugins load from, as the backend reports it for
  // display (home collapsed to `~`). Fetched on mount.
  const [reportedPluginsDir, setReportedPluginsDir] = useState<string | null>(null);

  useEffect(() => {
    // Guard the post-await state update: if the section unmounts (or StrictMode
    // re-runs the effect) before the fetch resolves, don't set state on a dead
    // component.
    let isIgnored = false;
    void (async (): Promise<void> => {
      try {
        const response = await getLocalPluginsDirectory({ meta: { skipWsAck: true } });
        if (!isIgnored && response.data?.path) setReportedPluginsDir(response.data.path);
      } catch {
        // Fall back to the health check's data directory (below); the label is
        // cosmetic, not load-critical.
      }
    })();

    return (): void => {
      isIgnored = true;
    };
  }, []);

  // Prefer the backend's display-formatted path. If that endpoint is missing
  // (an older running backend that predates it), use the data directory from the
  // health check — the real path for this install, just not home-collapsed —
  // rather than a hardcoded guess that would be wrong on a dev/source build.
  const pluginsDir =
    reportedPluginsDir ?? pluginsDirFromDataDirectory(healthCheckData?.dataDirectory) ?? DEFAULT_PLUGINS_DIR;

  // Built-in and discovered local sources come from the status map (the user
  // doesn't manage them); user URL sources keep their saved order. A freshly-
  // added user source may not have a status entry yet, so the row falls back to
  // a loading state.
  const managedSources = Object.keys(states).filter((s) => states[s].kind !== "url");
  const orderedSources = [...managedSources, ...userSources];

  // The source currently active (loaded) for each plugin id. A "shadowed" row
  // uses this to find its winning sibling: while that sibling is loaded, the
  // shadowed row can't be enabled (one active source per plugin id).
  const activeSourceByPluginId = new Map<string, string>();
  // Sources still occupying a plugin id — loaded, or loading (a winner claims
  // the id before it activates; a "loading" row carries no manifest, so it isn't
  // in activeSourceByPluginId yet). A shadowed row uses this to stay locked
  // during that activation window, while a since-disabled winner correctly
  // releases the lock.
  const activeOrLoadingSources = new Set<string>();
  for (const [src, state] of Object.entries(states)) {
    if (state.status === "loaded") activeSourceByPluginId.set(state.manifest.id, src);
    if (state.status === "loaded" || state.status === "loading") activeOrLoadingSources.add(src);
  }

  const handleAdd = async (): Promise<void> => {
    const source = draft.trim();
    if (!source || isBusy) return;
    setIsBusy(true);
    try {
      await pluginManager.addSource(store, source);
      setDraft("");
    } finally {
      setIsBusy(false);
    }
  };

  // Re-scan the Sculptor plugins folder on demand so a folder dropped in (or a
  // broken manifest fixed) shows up without a hard reload. There's no live
  // filesystem push yet, so this is the manual nudge.
  const handleRefresh = async (): Promise<void> => {
    if (isBusy) return;
    setIsBusy(true);
    try {
      await pluginManager.refreshLocalSources(store);
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <SettingsSectionLayout
      description={
        <>
          Plugins extend Sculptor with new panels and behavior. Drop a plugin folder into{" "}
          <Code size="2" style={inlineCodeStyle} data-testid={ElementIds.SETTINGS_PLUGINS_DIRECTORY}>
            {pluginsDir}
          </Code>{" "}
          and it loads on the next launch — or click Refresh to pick it up right away. You can also add the URL of a
          server hosting a{" "}
          <Code size="2" style={inlineCodeStyle}>
            manifest.json
          </Code>
          ; URL sources are saved and re-loaded each launch. Use the switch to disable a plugin without removing it.
        </>
      }
    >
      <Flex gap="2" align="center" mb="4">
        <TextField.Root
          style={{ flexGrow: 1 }}
          placeholder="http://localhost:5174/my-plugin"
          value={draft}
          disabled={isBusy}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void handleAdd();
          }}
          data-testid={ElementIds.SETTINGS_PLUGINS_SOURCE_INPUT}
        />
        <Button
          onClick={() => void handleAdd()}
          disabled={!draft.trim() || isBusy}
          data-testid={ElementIds.SETTINGS_PLUGINS_ADD_BUTTON}
        >
          <Plus size={14} />
          Add
        </Button>
        <Tooltip content={`Re-scan ${pluginsDir} for added or removed plugins`}>
          <IconButton
            variant="soft"
            color="gray"
            disabled={isBusy}
            onClick={() => void handleRefresh()}
            aria-label="Refresh local plugins"
            data-testid={ElementIds.SETTINGS_PLUGINS_REFRESH_BUTTON}
          >
            <RefreshCw size={14} />
          </IconButton>
        </Tooltip>
      </Flex>

      {orderedSources.length === 0 ? (
        <Flex direction="column" align="center" py="6" data-testid={ElementIds.SETTINGS_PLUGINS_EMPTY}>
          <Text size="2" color="gray">
            No plugins installed.
          </Text>
        </Flex>
      ) : (
        <Flex direction="column" data-testid={ElementIds.SETTINGS_PLUGINS_LIST}>
          {orderedSources.map((source) => (
            <SourceRow
              key={source}
              source={source}
              state={states[source]}
              activeSourceByPluginId={activeSourceByPluginId}
              activeOrLoadingSources={activeOrLoadingSources}
              pluginsDir={pluginsDir}
              store={store}
              setIsBusy={setIsBusy}
            />
          ))}
        </Flex>
      )}
    </SettingsSectionLayout>
  );
};

type SourceRowProps = {
  source: string;
  state: PluginSourceState | undefined;
  activeSourceByPluginId: ReadonlyMap<string, string>;
  activeOrLoadingSources: ReadonlySet<string>;
  pluginsDir: string;
  store: ReturnType<typeof useStore>;
  setIsBusy: (busy: boolean) => void;
};

const SourceRow = ({
  source,
  state,
  activeSourceByPluginId,
  activeOrLoadingSources,
  pluginsDir,
  store,
  setIsBusy,
}: SourceRowProps): ReactElement => {
  const kind = state?.kind ?? "url";
  // Built-in and discovered local sources aren't user-managed, so they can't be
  // removed (a local source would just reappear on the next rescan).
  const isReadOnly = kind !== "url";
  const isDisabled = state?.status === "disabled";
  const isLoaded = state?.status === "loaded";
  const isShadowed = state?.status === "shadowed";
  // A local source that vanished from disk but whose on/off choice we kept: a
  // dead-trace row, with no live plugin to toggle, settings, or reload — only a
  // Remove to forget it.
  const isMissing = state?.status === "missing";
  // Loaded and shadowed rows both carry a manifest (the shadowed one fetched
  // fine, it just isn't the active version) so both can show name + version.
  const manifest = state?.status === "loaded" || state?.status === "shadowed" ? state.manifest : undefined;
  // The sibling currently holding this plugin's id, if any — while it does, this
  // (shadowed) row can't be enabled. Prefer the loaded winner; fall back to the
  // recorded `activeSource` while it's still loading (it has no manifest yet, so
  // it isn't in activeSourceByPluginId), but only while that source is genuinely
  // occupying the slot — once it's disabled, the lock clears so the user can
  // switch to this version.
  const blockingSource = isShadowed
    ? (activeSourceByPluginId.get(state.manifest.id) ??
      (activeOrLoadingSources.has(state.activeSource) ? state.activeSource : undefined))
    : undefined;
  // The switch reflects *active*: on iff loaded (or mid-load/errored-but-trying);
  // off for disabled and shadowed. It's locked off while a sibling holds the id —
  // switch to this version by disabling that sibling first.
  const isToggleBlocked = blockingSource !== undefined;
  const isToggleChecked = !(isDisabled || isShadowed);
  const toggleTooltip = isToggleBlocked
    ? `Another version is active (from ${blockingSource}). Disable it to use this one.`
    : isToggleChecked
      ? "Disable"
      : "Enable";
  const settingsComponents = useAtomValue(pluginSettingsComponentsAtom);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  const pluginId = state?.status === "loaded" ? state.manifest.id : undefined;
  const SettingsComponent: ComponentType | undefined = pluginId ? settingsComponents[pluginId] : undefined;

  const handleReload = async (): Promise<void> => {
    setIsBusy(true);
    try {
      await pluginManager.reloadSource(store, source);
    } finally {
      setIsBusy(false);
    }
  };

  const handleToggle = async (enabled: boolean): Promise<void> => {
    setIsBusy(true);
    try {
      await pluginManager.setSourceEnabled(store, source, enabled);
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <Flex
      direction="column"
      style={{ borderBottom: "1px solid var(--gray-4)" }}
      data-testid={ElementIds.SETTINGS_PLUGINS_SOURCE_ROW}
      data-source={source}
      data-kind={kind}
      // A fresh source has no status entry yet; mirror the row's own loading
      // fallback. `data-status`/`data-phase` give integration tests a stable
      // hook to assert a source settled (loaded/error) and never hung loading.
      data-status={state?.status ?? "loading"}
      data-phase={state?.status === "error" ? state.phase : undefined}
    >
      {/* Anchor the controls to the top (align="start") so they stay put when
          the left column grows — e.g. enabling an invalid source adds a
          "failed" badge and an error message, which must not shove the switch
          down. */}
      <Flex justify="between" align="start" gap="3" py="3">
        <Flex direction="column" gap="1" style={{ minWidth: 0, flexGrow: 1 }}>
          <Flex align="center" gap="2">
            {manifest ? (
              <Text weight="medium">{manifest.name}</Text>
            ) : (
              <Text weight="medium" color="gray">
                {source.split("/").filter(Boolean).pop() ?? source}
              </Text>
            )}
            {manifest && (
              <Text size="1" color="gray">
                v{manifest.version}
              </Text>
            )}
            {kind === "builtin" && (
              <Badge size="1" color="gray" variant="soft">
                bundled
              </Badge>
            )}
            {kind === "local" && (
              <Badge size="1" color="gray" variant="soft">
                local
              </Badge>
            )}
            {isDisabled && (
              <Badge size="1" color="gray" variant="soft">
                disabled
              </Badge>
            )}
            {isShadowed && (
              <Badge size="1" color="amber" variant="soft">
                shadowed
              </Badge>
            )}
            {isMissing && (
              <Badge size="1" color="red" variant="soft">
                missing
              </Badge>
            )}
            {(!state || state.status === "loading") && <Spinner size="1" />}
            {state?.status === "error" && (
              <Badge size="1" color="red" variant="soft">
                failed: {state.phase}
              </Badge>
            )}
          </Flex>
          <Text size="1" color="gray" style={{ fontFamily: "var(--code-font-family)" }}>
            {source}
          </Text>
          {state?.status === "error" && (
            <Text size="1" color="gray">
              {state.message}
            </Text>
          )}
          {isMissing && (
            <Text size="1" color="gray">
              No longer found in{" "}
              <Code size="1" style={inlineCodeStyle}>
                {pluginsDir}
              </Code>
              . Its on/off choice is remembered and re-applied if it returns; remove to forget it.
            </Text>
          )}
        </Flex>
        <Flex align="center" gap="2">
          {/* Settings and reload only show while the source is enabled (loaded).
              They sit to the LEFT of the switch so toggling the source — which
              shows/hides them — never shifts the switch horizontally; only the
              always-present Remove stays to its right. */}
          {isLoaded && SettingsComponent && (
            <Tooltip content="Settings">
              <IconButton
                variant={isSettingsOpen ? "soft" : "ghost"}
                size="1"
                color="gray"
                aria-label={`Settings for ${source}`}
                onClick={() => setIsSettingsOpen((open) => !open)}
                data-testid={ElementIds.SETTINGS_PLUGINS_SOURCE_SETTINGS}
              >
                <Settings2 size={14} />
              </IconButton>
            </Tooltip>
          )}
          {isLoaded && (
            <Tooltip content="Reload">
              <IconButton
                variant="ghost"
                size="1"
                color="gray"
                aria-label={`Reload ${source}`}
                onClick={() => void handleReload()}
                data-testid={ElementIds.SETTINGS_PLUGINS_SOURCE_RELOAD}
              >
                <RotateCw size={14} />
              </IconButton>
            </Tooltip>
          )}
          {/* The enable/disable switch is present for every live source — it is
              how the user opts out of a built-in plugin, mutes a remote source,
              or switches between competing versions of the same plugin. It is
              locked off while a competing version is active (one source per id).
              A `missing` row has no live plugin to toggle, so it shows no switch
              (only the Remove below). Wrap it in a span so the Tooltip trigger's
              own `data-state` lands on the span, not the Switch — otherwise it
              clobbers the Switch's `data-state="checked"/"unchecked"` and the
              track loses its on/off coloring. */}
          {!isMissing && (
            <Tooltip content={toggleTooltip}>
              <span style={{ display: "inline-flex" }}>
                <Switch
                  checked={isToggleChecked}
                  disabled={isToggleBlocked}
                  onCheckedChange={(value) => void handleToggle(value)}
                  aria-label={`${toggleTooltip} ${source}`}
                  data-testid={ElementIds.SETTINGS_PLUGINS_SOURCE_TOGGLE}
                />
              </span>
            </Tooltip>
          )}
          {/* User URL sources are removable as always; a `missing` local row is
              too, so the user can forget its remembered on/off choice (a present
              local source has no Remove — a rescan would just re-add it). */}
          {(!isReadOnly || isMissing) && (
            <Tooltip content="Remove">
              <IconButton
                variant="ghost"
                size="1"
                color="gray"
                aria-label={`Remove ${source}`}
                onClick={() => pluginManager.removeSource(store, source)}
                data-testid={ElementIds.SETTINGS_PLUGINS_SOURCE_REMOVE}
              >
                <Trash2 size={14} />
              </IconButton>
            </Tooltip>
          )}
        </Flex>
      </Flex>
      {SettingsComponent && isSettingsOpen && pluginId && (
        <Flex direction="column" pb="3" pl="2">
          <PluginErrorBoundary pluginId={pluginId} pluginName={pluginId}>
            <PluginContext.Provider value={{ pluginId }}>
              <SettingsComponent />
            </PluginContext.Provider>
          </PluginErrorBoundary>
        </Flex>
      )}
    </Flex>
  );
};
