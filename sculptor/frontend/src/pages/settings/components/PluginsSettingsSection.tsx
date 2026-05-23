import { Badge, Flex, Text } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";
import { loadedPluginManifestsAtom, pluginLoadErrorsAtom } from "~/plugins/pluginRegistry.ts";

import { SettingsSectionLayout } from "./SettingsSection.tsx";

/**
 * Lists installed plugins. The prototype only displays what's loaded —
 * later this section will also be where the user installs new plugins
 * and configures per-plugin settings.
 */
export const PluginsSettingsSection = (): ReactElement => {
  const manifests = useAtomValue(loadedPluginManifestsAtom);
  const errors = useAtomValue(pluginLoadErrorsAtom);

  return (
    <SettingsSectionLayout description="Plugins extend Sculptor with new panels and behavior. Each plugin runs in the same renderer as the host and is wrapped in a per-plugin error boundary.">
      {manifests.length === 0 && errors.length === 0 ? (
        <Flex direction="column" align="center" py="6" data-testid={ElementIds.SETTINGS_PLUGINS_EMPTY}>
          <Text size="2" color="gray">
            No plugins installed.
          </Text>
        </Flex>
      ) : (
        <Flex direction="column" data-testid={ElementIds.SETTINGS_PLUGINS_LIST}>
          {manifests.map((manifest) => (
            <Flex
              key={manifest.id}
              justify="between"
              align="center"
              gap="3"
              py="3"
              style={{ borderBottom: "1px solid var(--gray-4)" }}
              data-testid={`${ElementIds.SETTINGS_PLUGINS_ROW}-${manifest.id}`}
            >
              <Flex direction="column" style={{ minWidth: 0, flexGrow: 1 }}>
                <Flex align="center" gap="2">
                  <Text weight="medium">{manifest.name}</Text>
                  <Text size="1" color="gray">
                    v{manifest.version}
                  </Text>
                </Flex>
                <Text size="1" color="gray" style={{ fontFamily: "var(--code-font-family)" }}>
                  {manifest.id}
                </Text>
              </Flex>
              <Badge size="1" color="gray" variant="soft">
                SDK {manifest.sdkVersion}
              </Badge>
            </Flex>
          ))}
          {errors.map((err, idx) => (
            <Flex
              key={`${err.manifest.id}-${idx}`}
              direction="column"
              gap="1"
              py="3"
              style={{ borderBottom: "1px solid var(--gray-4)" }}
              data-testid={`${ElementIds.SETTINGS_PLUGINS_ROW}-error-${err.manifest.id}`}
            >
              <Flex align="center" gap="2">
                <Text weight="medium">{err.manifest.name}</Text>
                <Badge size="1" color="red" variant="soft">
                  failed: {err.phase}
                </Badge>
              </Flex>
              <Text size="1" color="gray">
                {err.error.message}
              </Text>
            </Flex>
          ))}
        </Flex>
      )}
    </SettingsSectionLayout>
  );
};
