import { Button, Flex, Text, TextField } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useMemo, useState } from "react";

import { ElementIds, UserConfigField } from "~/api";
import { CATEGORY_DISPLAY_NAMES, CATEGORY_ORDER, type ResolvedKeybinding } from "~/common/keybindings";
import { keybindingsAtom } from "~/common/keybindings/atoms.ts";
import { allNamedBindingsAtom, dynamicLayoutKeybindingsAtom } from "~/common/keybindings/layoutShortcuts.ts";
import { formatShortcutForDisplay, parseShortcut } from "~/common/ShortcutUtils.ts";
import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";

import { HotkeyChip } from "./HotkeyChip.tsx";
import { SettingRow } from "./SettingRow.tsx";
import { SectionTitle, SettingsSectionLayout } from "./SettingsSection.tsx";

// ids are plain strings, not the static KeybindingId union: a conflict can involve a
// dynamic per-layout binding (layout.apply.<id>) on either side.
type ConflictInfo = {
  recordedKeys: string;
  targetId: string;
  conflictingId: string;
};

type KeybindingsSectionProps = {
  onSettingChange: (field: UserConfigField, value: unknown) => Promise<void>;
};

type HotkeyFieldProps = {
  title: string;
  description: string;
  value: string | undefined;
  onSet: (keys: string) => void;
  onClear: () => void;
  onRecordComplete?: (keys: string) => boolean | void;
};

const HotkeyField = ({
  title,
  description,
  value,
  onSet,
  onClear,
  onRecordComplete,
}: HotkeyFieldProps): ReactElement => (
  <SettingRow title={title} description={description}>
    <HotkeyChip value={value} onSet={onSet} onClear={onClear} onRecordComplete={onRecordComplete} />
  </SettingRow>
);

export const KeybindingsSection = ({ onSettingChange }: KeybindingsSectionProps): ReactElement => {
  const resolvedKeybindings = useAtomValue(keybindingsAtom);
  const layoutKeybindings = useAtomValue(dynamicLayoutKeybindingsAtom);
  // Static + per-layout bindings together, so conflict detection sees both lanes.
  const allNamedBindings = useAtomValue(allNamedBindingsAtom);
  const userConfig = useAtomValue(userConfigAtom);
  const [searchQuery, setSearchQuery] = useState("");
  const [conflictInfo, setConflictInfo] = useState<ConflictInfo | null>(null);

  const currentOverrides = useMemo(() => userConfig?.keybindings ?? {}, [userConfig]);

  const saveKeybindings = useCallback(
    async (updatedDict: Record<string, string | null>): Promise<void> => {
      await onSettingChange(UserConfigField.KEYBINDINGS, updatedDict);
    },
    [onSettingChange],
  );

  const handleResetAll = useCallback(async (): Promise<void> => {
    await saveKeybindings({});
  }, [saveKeybindings]);

  // Both static and per-layout bindings live in the same userConfig.keybindings
  // dict (per-layout ones keyed by layout.apply.<id>), so the same write path
  // serves both — `id` is just a string key.
  const handleSetBinding = useCallback(
    async (id: string, keys: string): Promise<void> => {
      await saveKeybindings({ ...currentOverrides, [id]: keys });
    },
    [currentOverrides, saveKeybindings],
  );

  const handleClearBinding = useCallback(
    async (id: string): Promise<void> => {
      await saveKeybindings({ ...currentOverrides, [id]: null });
    },
    [currentOverrides, saveKeybindings],
  );

  const checkForConflict = useCallback(
    (targetId: string, recordedKeys: string): boolean | void => {
      const parsedRecorded = parseShortcut(recordedKeys);
      for (const kb of allNamedBindings) {
        if (kb.id === targetId) continue;
        if (kb.binding) {
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
      }
      return true;
    },
    [allNamedBindings],
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

  const handleCancelConflict = useCallback((): void => {
    setConflictInfo(null);
  }, []);

  const filteredByCategory = useMemo(() => {
    const lowerQuery = searchQuery.toLowerCase();
    const groups: Array<{
      category: string;
      displayName: string;
      bindings: Array<ResolvedKeybinding>;
    }> = [];

    for (const category of CATEGORY_ORDER) {
      const categoryBindings = resolvedKeybindings.filter((kb) => {
        if (kb.category !== category) return false;
        if (!searchQuery) return true;
        return kb.name.toLowerCase().includes(lowerQuery) || kb.description.toLowerCase().includes(lowerQuery);
      });
      if (categoryBindings.length > 0) {
        groups.push({
          category,
          displayName: CATEGORY_DISPLAY_NAMES[category],
          bindings: categoryBindings,
        });
      }
    }
    return groups;
  }, [resolvedKeybindings, searchQuery]);

  const conflictingName = useMemo(() => {
    if (!conflictInfo) return "";
    const match = allNamedBindings.find((kb) => kb.id === conflictInfo.conflictingId);
    return match?.name ?? conflictInfo.conflictingId;
  }, [conflictInfo, allNamedBindings]);

  // Per-layout shortcut rows for the "Layouts" group, filtered by the search box.
  const filteredLayoutKeybindings = useMemo(() => {
    const lowerQuery = searchQuery.toLowerCase();
    if (!searchQuery) {
      return layoutKeybindings;
    }
    return layoutKeybindings.filter(
      (kb) => kb.name.toLowerCase().includes(lowerQuery) || kb.description.toLowerCase().includes(lowerQuery),
    );
  }, [layoutKeybindings, searchQuery]);

  // One binding row + its inline conflict prompt. Shared by the static category
  // groups and the dynamic Layouts group so both behave identically.
  const renderBindingRow = (id: string, name: string, description: string, binding: string | null): ReactElement => (
    <Flex key={id} direction="column" data-keybinding-id={id}>
      <HotkeyField
        title={name}
        description={description}
        value={binding ?? undefined}
        onSet={(keys) => void handleSetBinding(id, keys)}
        onClear={() => void handleClearBinding(id)}
        onRecordComplete={(keys) => checkForConflict(id, keys)}
      />
      {conflictInfo?.targetId === id && (
        <Flex
          mt="2"
          mb="2"
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

  return (
    <SettingsSectionLayout
      description="Customize keybindings for Sculptor."
      toolbar={
        <Flex justify="between" align="center" mb="6" wrap="wrap" gap="2">
          <TextField.Root
            placeholder="Search keybindings..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            data-testid={ElementIds.SETTINGS_KEYBINDINGS_SEARCH}
            style={{ minWidth: "150px", maxWidth: "300px", flex: 1 }}
          />
          <Button
            variant="soft"
            onClick={() => void handleResetAll()}
            data-testid={ElementIds.SETTINGS_KEYBINDINGS_RESET_ALL}
          >
            Reset all to defaults
          </Button>
        </Flex>
      }
    >
      {filteredByCategory.map(({ category, displayName, bindings }, index) => (
        <Flex key={category} direction="column" mt={index > 0 ? "6" : "0"}>
          <SectionTitle>{displayName}</SectionTitle>
          {bindings.map((kb) => renderBindingRow(kb.id, kb.name, kb.description, kb.binding))}
        </Flex>
      ))}
      {filteredLayoutKeybindings.length > 0 && (
        <Flex
          direction="column"
          mt={filteredByCategory.length > 0 ? "6" : "0"}
          data-testid={ElementIds.SETTINGS_KEYBINDINGS_LAYOUTS_GROUP}
        >
          <SectionTitle>Layouts</SectionTitle>
          {filteredLayoutKeybindings.map((kb) => renderBindingRow(kb.id, kb.name, kb.description, kb.binding))}
        </Flex>
      )}
    </SettingsSectionLayout>
  );
};
