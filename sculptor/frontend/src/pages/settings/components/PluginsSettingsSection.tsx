import { Badge, Button, Flex, IconButton, Spinner, Switch, Text, TextField, Tooltip } from "@radix-ui/themes";
import { useAtomValue, useStore } from "jotai";
import { Plus, RotateCw, Settings2, Trash2 } from "lucide-react";
import { type ComponentType, type ReactElement, useState } from "react";

import { ElementIds } from "~/api";
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

/**
 * Lists installed plugins and lets the user point Sculptor at additional
 * plugin sources (a URL or directory containing a `manifest.json`). Sources
 * are persisted to localStorage and re-loaded on every boot.
 */
export const PluginsSettingsSection = (): ReactElement => {
  const store = useStore();
  const userSources = useAtomValue(pluginSourcesAtom);
  const states = useAtomValue(pluginSourceStatesAtom);
  const [draft, setDraft] = useState("");
  const [isBusy, setIsBusy] = useState(false);

  // Built-in sources come from the status map; user sources keep their saved
  // order. A freshly-added user source may not have a status entry yet, so the
  // row falls back to a loading state.
  const builtinSources = Object.keys(states).filter((s) => states[s].isBuiltin);
  const orderedSources = [...builtinSources, ...userSources];

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

  return (
    <SettingsSectionLayout description="Plugins extend Sculptor with new panels and behavior. Point at a URL or directory that contains a manifest.json; sources are saved locally and re-loaded each launch. Use the switch to disable a plugin without removing it.">
      <Flex gap="2" align="center" mb="4">
        <TextField.Root
          style={{ flexGrow: 1 }}
          placeholder="https://localhost:5174/my-plugin or /plugins/my-plugin"
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
            <SourceRow key={source} source={source} state={states[source]} store={store} setIsBusy={setIsBusy} />
          ))}
        </Flex>
      )}
    </SettingsSectionLayout>
  );
};

type SourceRowProps = {
  source: string;
  state: PluginSourceState | undefined;
  store: ReturnType<typeof useStore>;
  setIsBusy: (busy: boolean) => void;
};

const SourceRow = ({ source, state, store, setIsBusy }: SourceRowProps): ReactElement => {
  const isBuiltin = state?.isBuiltin ?? false;
  const isDisabled = state?.status === "disabled";
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
            {state?.status === "loaded" ? (
              <Text weight="medium">{state.manifest.name}</Text>
            ) : (
              <Text weight="medium" color="gray">
                {source.split("/").filter(Boolean).pop() ?? source}
              </Text>
            )}
            {state?.status === "loaded" && (
              <Text size="1" color="gray">
                v{state.manifest.version}
              </Text>
            )}
            {isBuiltin && (
              <Badge size="1" color="gray" variant="soft">
                bundled
              </Badge>
            )}
            {isDisabled && (
              <Badge size="1" color="gray" variant="soft">
                disabled
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
        </Flex>
        <Flex align="center" gap="2">
          {/* Settings and reload only show while the source is enabled (loaded).
              They sit to the LEFT of the switch so toggling the source — which
              shows/hides them — never shifts the switch horizontally; only the
              always-present Remove stays to its right. */}
          {!isDisabled && SettingsComponent && (
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
          {!isDisabled && (
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
          {/* The enable/disable switch is always present — it is how the user
              opts out of a built-in plugin or mutes a remote source without
              removing it. Wrap it in a span so the Tooltip trigger's own
              `data-state` lands on the span, not the Switch — otherwise it
              clobbers the Switch's `data-state="checked"/"unchecked"` and the
              track loses its on/off coloring. */}
          <Tooltip content={isDisabled ? "Enable" : "Disable"}>
            <span style={{ display: "inline-flex" }}>
              <Switch
                checked={!isDisabled}
                onCheckedChange={(value) => void handleToggle(value)}
                aria-label={`${isDisabled ? "Enable" : "Disable"} ${source}`}
                data-testid={ElementIds.SETTINGS_PLUGINS_SOURCE_TOGGLE}
              />
            </span>
          </Tooltip>
          {!isBuiltin && (
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
