import { Flex, Select, TextField } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";
import {
  getDefaultNightModeExpiry,
  getNightModeExpiry,
  getNightModeKind,
  NIGHT_MODE_OFF,
  NIGHT_MODE_ON,
  type NightModeKind,
  toDateTimeLocalValue,
} from "~/common/nightMode.ts";

import { SettingRow } from "./SettingRow.tsx";

const KIND_LABELS: Record<NightModeKind, string> = {
  off: "Off",
  on: "On",
  until: "Until…",
};

type NightModeSettingRowProps = {
  nightMode: string;
  onChange: (nightMode: string) => void;
};

/**
 * Chooses the global night-mode override.
 *
 * Selecting "Until…" seeds the next 8am rather than an empty picker, so the
 * overnight case costs one choice instead of a full date and time.
 */
export const NightModeSettingRow = ({ nightMode, onChange }: NightModeSettingRowProps): ReactElement => {
  const kind = getNightModeKind(nightMode);
  const expiry = getNightModeExpiry(nightMode);

  const handleKindChange = (nextKind: string): void => {
    if (nextKind === "off") {
      onChange(NIGHT_MODE_OFF);
    } else if (nextKind === "on") {
      onChange(NIGHT_MODE_ON);
    } else {
      onChange(getDefaultNightModeExpiry(new Date()).toISOString());
    }
  };

  const handleExpiryChange = (value: string): void => {
    const nextExpiry = new Date(value);
    // The picker reports an empty or half-entered value as an invalid date;
    // writing that would silently turn the override off.
    if (!Number.isNaN(nextExpiry.getTime())) {
      onChange(nextExpiry.toISOString());
    }
  };

  return (
    <SettingRow
      title="Night Mode"
      description="Run every Claude agent without fast mode, so overnight work bills at standard rates rather than fast mode's premium. Agents pick fast mode back up on their own once it ends."
    >
      <Flex gap="2" align="center" justify="end" wrap="wrap">
        <Select.Root value={kind} onValueChange={handleKindChange}>
          <Select.Trigger variant="soft" data-testid={ElementIds.SETTINGS_NIGHT_MODE_SELECT} />
          <Select.Content>
            {(Object.keys(KIND_LABELS) as Array<NightModeKind>).map((option) => (
              <Select.Item key={option} value={option} data-testid={ElementIds.SETTINGS_NIGHT_MODE_OPTION}>
                {KIND_LABELS[option]}
              </Select.Item>
            ))}
          </Select.Content>
        </Select.Root>
        {expiry !== null && (
          <TextField.Root
            type="datetime-local"
            value={toDateTimeLocalValue(expiry)}
            onChange={(event) => handleExpiryChange(event.target.value)}
            data-testid={ElementIds.SETTINGS_NIGHT_MODE_UNTIL_INPUT}
          />
        )}
      </Flex>
    </SettingRow>
  );
};
