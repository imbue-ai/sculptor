import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";
import { NIGHT_MODE_OFF, NIGHT_MODE_ON } from "~/common/nightMode.ts";

import { NightModeSettingRow } from "./NightModeSettingRow.tsx";

const withTheme = (children: ReactNode): ReactElement => <Theme>{children}</Theme>;

beforeAll(() => {
  // Radix Select calls scrollIntoView on open; jsdom does not implement it.
  Element.prototype.scrollIntoView = (): void => {};
});

afterEach(() => {
  cleanup();
});

const getUntilInput = (): HTMLInputElement | null =>
  screen.queryByTestId(ElementIds.SETTINGS_NIGHT_MODE_UNTIL_INPUT) as HTMLInputElement | null;

describe("NightModeSettingRow", () => {
  it("shows the expiry picker only for an expiring override", () => {
    const { rerender } = render(withTheme(<NightModeSettingRow nightMode={NIGHT_MODE_OFF} onChange={() => {}} />));
    expect(getUntilInput()).toBeNull();

    rerender(withTheme(<NightModeSettingRow nightMode={NIGHT_MODE_ON} onChange={() => {}} />));
    expect(getUntilInput()).toBeNull();

    rerender(
      withTheme(<NightModeSettingRow nightMode={new Date(2026, 8, 10, 8, 0).toISOString()} onChange={() => {}} />),
    );
    expect(getUntilInput()?.value).toBe("2026-09-10T08:00");
  });

  it("writes the picked wall-clock time back as an absolute instant", () => {
    const onChange = vi.fn();
    render(
      withTheme(<NightModeSettingRow nightMode={new Date(2026, 8, 10, 8, 0).toISOString()} onChange={onChange} />),
    );

    fireEvent.change(getUntilInput() as HTMLInputElement, { target: { value: "2026-09-11T06:30" } });

    expect(onChange).toHaveBeenCalledWith(new Date(2026, 8, 11, 6, 30).toISOString());
  });

  it("ignores a cleared picker rather than silently turning the override off", () => {
    const onChange = vi.fn();
    render(
      withTheme(<NightModeSettingRow nightMode={new Date(2026, 8, 10, 8, 0).toISOString()} onChange={onChange} />),
    );

    fireEvent.change(getUntilInput() as HTMLInputElement, { target: { value: "" } });

    expect(onChange).not.toHaveBeenCalled();
  });
});
