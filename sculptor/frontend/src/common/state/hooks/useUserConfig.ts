import { useAtom } from "jotai";
import { useCallback } from "react";

import type { UserConfig, UserConfigField } from "../../../api";
import { getUserConfig, updateUserConfig } from "../../../api";
import { userConfigAtom } from "../atoms/userConfig.ts";

/**
 * Return type for useUserConfigSync hook
 */
type UserConfigSyncActions = {
  /** Load user configuration from the server */
  loadConfig: () => Promise<void>;
  /** Update multiple user config fields with optimistic UI update */
  updateConfig: (fieldUpdates: Partial<UserConfig>) => Promise<UserConfig | undefined>;
  /** Update a single user config field using type-safe field constants */
  updateField: (field: UserConfigField, value: unknown) => Promise<UserConfig | undefined>;
};

/**
 * CONFIGURATION SYNCHRONIZATION HOOK
 *
 * This hook manages the lifecycle of user configuration:
 * 1. Initial loading during app startup
 * 2. Settings updates with optimistic UI updates
 * 3. Error recovery and fallback handling
 */
export const useUserConfig = (): UserConfigSyncActions => {
  const [currentConfig, setUserConfig] = useAtom(userConfigAtom);

  // Initial load - called once during app initialization
  const loadConfig = useCallback(async () => {
    try {
      const { data: config } = await getUserConfig({
        meta: { skipWsAck: true },
      });
      if (!config) {
        console.log("No config created yet, likely because the user has not completed onboarding.");
      }
      setUserConfig(config);
    } catch (error) {
      console.error("Failed to load user config. Error: ", error);
      throw error;
    }
  }, [setUserConfig]);

  const updateConfig = useCallback(
    async (fieldUpdates: Partial<UserConfig>) => {
      if (!currentConfig) {
        console.error("Cannot update config: no current config loaded");
        return;
      }

      const optimisticConfig = { ...currentConfig, ...fieldUpdates };

      // Optimistic update - show changes immediately
      setUserConfig(optimisticConfig);

      try {
        // Send only the changed fields; the backend merges into the current
        // server config. PUTting the full atom would let stale fields
        // (e.g. enableInPlaceWorkspaces from a previous load) clobber the
        // server.
        const { data: newConfig } = await updateUserConfig({
          body: {
            userConfig: fieldUpdates as Record<string, unknown>,
          },
          meta: { skipWsAck: true },
        });
        // Server response overwrites optimistic update
        setUserConfig(newConfig);
        return newConfig;
      } catch (error) {
        console.error("Failed to update user config:", error);
        // Revert optimistic update on failure
        setUserConfig(currentConfig);
        throw error;
      }
    },
    [currentConfig, setUserConfig],
  );

  const updateField = useCallback(
    async (field: UserConfigField, value: unknown): Promise<UserConfig | undefined> => {
      const updates: Partial<UserConfig> = { [field]: value };
      return updateConfig(updates);
    },
    [updateConfig],
  );

  return {
    loadConfig,
    updateConfig,
    updateField,
  };
};
