import { Flex, Select, TextField } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";
import {
  getDefaultNightModeExpiry,
  NIGHT_MODE_OFF,
  NIGHT_MODE_ON,
  type NightModeKind,
  parseNightMode,
  toDateTimeLocalValue,
} from "~/common/nightMode.ts";

import { SettingRow } from "./SettingRow.tsx";

const KIND_OPTIONS: ReadonlyArray<{ kind: NightModeKind; label: string }> = [
  { kind: "off", label: "Off" },
  { kind: "on", label: "On" },
  { kind: "until", label: "Until…" },
];

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
  const state = parseNightMode(nightMode);

  const handleKindChange = (nextKind: string): void => {
    if (nextKind === NIGHT_MODE_OFF) {
      onChange(NIGHT_MODE_OFF);
    } else if (nextKind === NIGHT_MODE_ON) {
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
      description="Turn on Night Mode when leaving agents running unattended. It overrides Fast Mode for every agent, so the same work will cost you less. Your Fast Mode settings will remain untouched and begin to apply again when Night Mode ends."
    >
      <Flex gap="2" align="center" justify="end" wrap="wrap">
        <Select.Root value={state.kind} onValueChange={handleKindChange}>
          <Select.Trigger variant="soft" data-testid={ElementIds.SETTINGS_NIGHT_MODE_SELECT} />
          <Select.Content>
            {KIND_OPTIONS.map(({ kind, label }) => (
              <Select.Item key={kind} value={kind} data-testid={ElementIds.SETTINGS_NIGHT_MODE_OPTION}>
                {label}
              </Select.Item>
            ))}
          </Select.Content>
        </Select.Root>
        {state.kind === "until" && (
          <TextField.Root
            type="datetime-local"
            value={toDateTimeLocalValue(state.expiry)}
            onChange={(event) => handleExpiryChange(event.target.value)}
            data-testid={ElementIds.SETTINGS_NIGHT_MODE_UNTIL_INPUT}
          />
        )}
      </Flex>
    </SettingRow>
  );
};
