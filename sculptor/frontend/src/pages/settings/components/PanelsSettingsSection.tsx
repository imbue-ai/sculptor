import { Badge, Button, Flex, Select, Switch, Text } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { type ReactElement, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import type { UserConfigField } from "~/api";
import { ElementIds } from "~/api";
import { KEYBINDING_DEFINITIONS, type KeybindingId } from "~/common/keybindings";
import { keybindingsAtom } from "~/common/keybindings/atoms.ts";
import { formatShortcutForDisplay, parseShortcut } from "~/common/ShortcutUtils.ts";
import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";
import {
  activePanelPerZoneAtom,
  panelEnabledAtom,
  panelKeybindingId,
  panelRegistryAtom,
  zoneAssignmentsAtom,
  zoneOrderAtom,
  zoneVisibilityAtom,
} from "~/components/panels/atoms.ts";
import { ZONE_DISPLAY_NAMES } from "~/components/panels/constants.ts";
import { usePanelActions, usePanelEnabled, usePanelsByZone } from "~/components/panels/hooks.ts";
import type { PanelId, ZoneId } from "~/components/panels/types.ts";
import { ZONE_IDS } from "~/components/panels/types.ts";
import { isZoneMoveDisabled } from "~/components/panels/utils.ts";
import { workspaceDefaultLayout } from "~/pages/workspace/panels/workspacePanels.ts";

import { HotkeyChip } from "./HotkeyChip.tsx";
import { PanelsLayoutDiagram } from "./PanelsLayoutDiagram.tsx";
import styles from "./PanelsSettingsSection.module.scss";
import { SettingsSectionLayout } from "./SettingsSection.tsx";

type ConflictInfo = {
  recordedKeys: string;
  targetId: KeybindingId;
  conflictingId: KeybindingId;
};

type PanelsSettingsSectionProps = {
  onSettingChange: (field: UserConfigField, value: unknown) => Promise<void>;
};

export const PanelsSettingsSection = ({ onSettingChange }: PanelsSettingsSectionProps): ReactElement => {
  const registry = useAtomValue(panelRegistryAtom);
  const zoneAssignments = useAtomValue(zoneAssignmentsAtom);
  const panelsByZone = usePanelsByZone();
  const resolvedKeybindings = useAtomValue(keybindingsAtom);
  const userConfig = useAtomValue(userConfigAtom);
  const { enabled, setEnabled } = usePanelEnabled();
  const { movePanel } = usePanelActions();
  const setZoneAssignments = useSetAtom(zoneAssignmentsAtom);
  const setActivePanelPerZone = useSetAtom(activePanelPerZoneAtom);
  const setZoneVisibility = useSetAtom(zoneVisibilityAtom);
  const setZoneOrder = useSetAtom(zoneOrderAtom);
  const setPanelEnabled = useSetAtom(panelEnabledAtom);
  const [conflictInfo, setConflictInfo] = useState<ConflictInfo | null>(null);
  const [filterZone, setFilterZone] = useState<ZoneId | null>(null);
  const [searchParams] = useSearchParams();
  const targetPanelId = searchParams.get("panel");

  useEffect(() => {
    if (!targetPanelId) return;
    const row = document.querySelector(`[data-panel-row-id="${CSS.escape(targetPanelId)}"]`);
    if (!(row instanceof HTMLElement)) return;
    row.scrollIntoView({ behavior: "smooth", block: "center" });
    const firstControl = row.querySelector<HTMLElement>('button, [role="combobox"], [role="switch"]');
    firstControl?.focus();
  }, [targetPanelId]);

  const currentOverrides = useMemo(() => userConfig?.keybindings ?? {}, [userConfig]);

  const saveKeybindings = useCallback(
    async (updatedDict: Record<string, string | null>): Promise<void> => {
      await onSettingChange("keybindings" as UserConfigField, updatedDict);
    },
    [onSettingChange],
  );

  const handleSetBinding = useCallback(
    async (id: KeybindingId, keys: string): Promise<void> => {
      await saveKeybindings({ ...currentOverrides, [id]: keys });
    },
    [currentOverrides, saveKeybindings],
  );

  const handleClearBinding = useCallback(
    async (id: KeybindingId): Promise<void> => {
      await saveKeybindings({ ...currentOverrides, [id]: null });
    },
    [currentOverrides, saveKeybindings],
  );

  const checkForConflict = useCallback(
    (targetId: KeybindingId, recordedKeys: string): boolean | void => {
      const parsedRecorded = parseShortcut(recordedKeys);
      for (const kb of resolvedKeybindings) {
        if (kb.id === targetId) continue;
        if (!kb.binding) continue;
        const parsedExisting = parseShortcut(kb.binding);
        if (
          parsedRecorded.meta === parsedExisting.meta &&
          parsedRecorded.ctrl === parsedExisting.ctrl &&
          parsedRecorded.alt === parsedExisting.alt &&
          parsedRecorded.shift === parsedExisting.shift &&
          parsedRecorded.key === parsedExisting.key
        ) {
          setConflictInfo({ recordedKeys, targetId, conflictingId: kb.id });
          return false;
        }
      }
      return true;
    },
    [resolvedKeybindings],
  );

  const handleReassign = useCallback(async (): Promise<void> => {
    if (!conflictInfo) return;
    await saveKeybindings({
      ...currentOverrides,
      [conflictInfo.targetId]: conflictInfo.recordedKeys,
      [conflictInfo.conflictingId]: null,
    });
    setConflictInfo(null);
  }, [conflictInfo, currentOverrides, saveKeybindings]);

  const handleCancelConflict = useCallback((): void => setConflictInfo(null), []);

  const handleReset = useCallback((): void => {
    setZoneAssignments(workspaceDefaultLayout.zoneAssignments);
    setActivePanelPerZone(workspaceDefaultLayout.activePanelPerZone);
    setZoneVisibility(workspaceDefaultLayout.zoneVisibility);
    setZoneOrder(workspaceDefaultLayout.zoneOrder);
    setPanelEnabled({});
  }, [setZoneAssignments, setActivePanelPerZone, setZoneVisibility, setZoneOrder, setPanelEnabled]);

  const conflictingName = useMemo(() => {
    if (!conflictInfo) return "";
    if (conflictInfo.conflictingId.startsWith("panel_")) {
      const panelId = conflictInfo.conflictingId.slice("panel_".length);
      return registry.find((p) => p.id === panelId)?.displayName ?? panelId;
    }
    return KEYBINDING_DEFINITIONS.find((d) => d.id === conflictInfo.conflictingId)?.name ?? conflictInfo.conflictingId;
  }, [conflictInfo, registry]);

  const filteredPanels = registry.filter(
    (panel) => filterZone == null || (zoneAssignments[panel.id] ?? panel.defaultZone) === filterZone,
  );

  return (
    <SettingsSectionLayout description="Configure which panels are available, where they dock, and their keyboard shortcuts.">
      <PanelsLayoutDiagram filterZone={filterZone} onFilterZone={setFilterZone} />
      {filteredPanels.map((panel) => {
        const Icon = panel.icon;
        const targetId = panelKeybindingId(panel.id);
        const binding = resolvedKeybindings.find((kb) => kb.id === targetId)?.binding ?? null;
        const isBuiltin = panel.isBuiltin ?? false;
        const isEnabled = isBuiltin || (enabled[panel.id] ?? panel.defaultEnabled ?? true);
        const currentZone = zoneAssignments[panel.id] ?? panel.defaultZone;

        return (
          <Flex
            key={panel.id}
            direction="column"
            py="3"
            className={styles.panelRow}
            data-panel-row-id={panel.id}
            data-testid={`${ElementIds.SETTINGS_PANELS_ROW}-${panel.id}`}
          >
            <Flex justify="between" align="center" gap="3">
              <Flex align="center" gap="3" style={{ flex: 1, minWidth: 0 }}>
                <Icon size={18} />
                <Flex direction="column" style={{ minWidth: 0 }}>
                  <Flex align="center" gap="2">
                    <Text weight="medium">{panel.displayName}</Text>
                    {panel.pluginId && (
                      <Badge
                        size="1"
                        color="iris"
                        variant="soft"
                        data-testid={`${ElementIds.SETTINGS_PANELS_PLUGIN_BADGE}-${panel.id}`}
                      >
                        plugin
                      </Badge>
                    )}
                  </Flex>
                  <Text size="2" color="gray">
                    {panel.description}
                  </Text>
                </Flex>
              </Flex>
              <Flex align="center" gap="3">
                <Select.Root
                  value={currentZone}
                  onValueChange={(value) => movePanel(panel.id as PanelId, value as ZoneId)}
                >
                  <Select.Trigger data-testid={`${ElementIds.SETTINGS_PANELS_ZONE_SELECT}-${panel.id}`} />
                  <Select.Content>
                    {ZONE_IDS.map((zoneId) => {
                      const isDisabled =
                        zoneId !== currentZone &&
                        isZoneMoveDisabled({
                          panelId: panel.id as PanelId,
                          targetZone: zoneId,
                          panelsByZone,
                        });
                      return (
                        <Select.Item key={zoneId} value={zoneId} disabled={isDisabled}>
                          {ZONE_DISPLAY_NAMES[zoneId]}
                        </Select.Item>
                      );
                    })}
                  </Select.Content>
                </Select.Root>
                <HotkeyChip
                  value={binding ?? undefined}
                  onSet={(keys) => void handleSetBinding(targetId, keys)}
                  onClear={() => void handleClearBinding(targetId)}
                  onRecordComplete={(keys) => checkForConflict(targetId, keys)}
                  disabled={!isEnabled}
                />
                {!isBuiltin && (
                  <Switch
                    checked={enabled[panel.id] ?? panel.defaultEnabled ?? true}
                    onCheckedChange={(value) => setEnabled(panel.id as PanelId, value)}
                    data-testid={`${ElementIds.SETTINGS_PANELS_ENABLED_SWITCH}-${panel.id}`}
                  />
                )}
              </Flex>
            </Flex>
            {conflictInfo?.targetId === targetId && (
              <Flex
                mt="2"
                p="2"
                gap="2"
                align="center"
                style={{ background: "var(--amber-a3)", borderRadius: "var(--radius-2)" }}
                data-testid={ElementIds.SETTINGS_KEYBINDINGS_CONFLICT_WARNING}
              >
                <Text size="2">
                  &ldquo;{formatShortcutForDisplay(conflictInfo.recordedKeys)}&rdquo; is already assigned to &ldquo;
                  {conflictingName}&rdquo;
                </Text>
                <Button
                  size="1"
                  variant="solid"
                  onClick={() => void handleReassign()}
                  data-testid={ElementIds.SETTINGS_KEYBINDINGS_REASSIGN}
                >
                  Reassign
                </Button>
                <Button
                  size="1"
                  variant="soft"
                  onClick={handleCancelConflict}
                  data-testid={ElementIds.SETTINGS_KEYBINDINGS_CANCEL_CONFLICT}
                >
                  Cancel
                </Button>
              </Flex>
            )}
          </Flex>
        );
      })}
      <Flex justify="end" mt="4">
        <Button
          variant="ghost"
          size="1"
          color="gray"
          onClick={handleReset}
          data-testid={ElementIds.SETTINGS_PANELS_RESET_DEFAULTS}
        >
          Reset to defaults
        </Button>
      </Flex>
    </SettingsSectionLayout>
  );
};
