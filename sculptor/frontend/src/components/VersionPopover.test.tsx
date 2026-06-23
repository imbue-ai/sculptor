import { Theme } from "@radix-ui/themes";
import { cleanup, render, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";

import type { HealthCheckResponse } from "~/api";
import { ElementIds } from "~/api";
import { healthCheckDataAtom } from "~/common/state/atoms/backend.ts";
import { devPanelOpenAtom } from "~/common/state/atoms/devPanel.ts";

import { VersionPopover } from "./VersionPopover.tsx";

type Store = ReturnType<typeof createStore>;

const renderPopover = (options: { store?: Store } = {}): { store: Store } => {
  const store = options.store ?? createStore();
  // Open the dev panel so the Popover.Content (which holds the Platform row) is
  // mounted; otherwise the diagnostics rows never render.
  store.set(devPanelOpenAtom, true);
  const Wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>
      <Theme>{children}</Theme>
    </Provider>
  );
  render(<VersionPopover />, { wrapper: Wrapper });
  return { store };
};

afterEach(() => {
  cleanup();
});

describe("VersionPopover", () => {
  // Bug: while health/version data was still loading the Platform row rendered
  // "undefined undefined" (template literal over absent fields). The fix gates
  // the value on `healthCheckData` so InfoRow's nullish fallback ("—") shows.
  it("shows the fallback dash on the Platform row when health data is absent", () => {
    // healthCheckDataAtom defaults to null (data not yet loaded).
    renderPopover();

    // The popover is open by default (isDevPanelOpen drives Popover.Root open),
    // so the diagnostics rows are in the DOM. Find the Platform label row.
    const platformLabel = screen.getByText("Platform");
    const row = platformLabel.parentElement as HTMLElement;

    expect(row.textContent).not.toContain("undefined");
    // The InfoRow value column falls back to the em dash.
    expect(row.textContent).toContain("—");
  });

  it("renders the real platform string when health data is present", () => {
    const store = createStore();
    store.set(healthCheckDataAtom, {
      version: "1.2.3",
      platform: "Darwin",
      platformVersion: "24.0",
    } as unknown as HealthCheckResponse);
    renderPopover({ store });

    const platformLabel = screen.getByText("Platform");
    const row = platformLabel.parentElement as HTMLElement;
    expect(row.textContent).toContain("Darwin 24.0");
    expect(row.textContent).not.toContain("undefined");
  });

  it("renders the version trigger without literal undefined when data is absent", () => {
    renderPopover();
    const trigger = screen.getByTestId(ElementIds.VERSION);
    expect(trigger.textContent ?? "").not.toContain("undefined");
  });
});
