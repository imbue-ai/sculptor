import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createStore } from "jotai";
import type { ReactElement } from "react";
import { Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { ElementIds } from "~/api";
import { renderWithProviders } from "~/common/utils/renderWithProviders.tsx";

import { JjLeftOutFilesBanner } from "./JjLeftOutFilesBanner.tsx";

const BIG_FILE_REASON =
  "jj did not snapshot this file: 2.0MiB (2097152 bytes); the maximum size allowed is 1.0MiB (1048576 bytes)";

const SettingsLocation = (): ReactElement => {
  const location = useLocation();
  return <div data-testid="settings-location">{`${location.pathname}${location.search}`}</div>;
};

const renderBanner = (fileErrors: Readonly<Record<string, string>>): void => {
  renderWithProviders(
    <Routes>
      <Route path="/ws/ws-1" element={<JjLeftOutFilesBanner fileErrors={fileErrors} />} />
      <Route path="/settings" element={<SettingsLocation />} />
    </Routes>,
    { store: createStore(), initialEntries: ["/ws/ws-1"] },
  );
};

afterEach(() => {
  cleanup();
});

describe("JjLeftOutFilesBanner", () => {
  it("shows nothing while jj has left no file out", () => {
    renderBanner({});

    expect(screen.queryByTestId(ElementIds.JJ_LEFT_OUT_FILES_BANNER)).toBeNull();
  });

  it("lists each left-out file with jj's reason, by path", () => {
    renderBanner({ "data/big.bin": BIG_FILE_REASON, "assets/video.mp4": BIG_FILE_REASON });

    const files = screen.getAllByTestId(ElementIds.JJ_LEFT_OUT_FILE);
    expect(files.map((file) => file.textContent)).toEqual([
      `assets/video.mp4${BIG_FILE_REASON}`,
      `data/big.bin${BIG_FILE_REASON}`,
    ]);
    expect(screen.getByTestId(ElementIds.JJ_LEFT_OUT_FILES_BANNER).textContent).toContain("jj left 2 new files out");
  });

  it("says the files are in no diff, commit or push, and where to raise the limit", () => {
    renderBanner({ "big.bin": BIG_FILE_REASON });

    const banner = screen.getByTestId(ElementIds.JJ_LEFT_OUT_FILES_BANNER);
    expect(banner.textContent).toContain("jj left 1 new file out");
    expect(banner.textContent).toContain("no diff, commit or push");
    expect(banner.textContent).toContain("Jujutsu settings page");
  });

  it("opens the Jujutsu settings page", async () => {
    const user = userEvent.setup();
    renderBanner({ "big.bin": BIG_FILE_REASON });

    await user.click(screen.getByText("Open Jujutsu settings"));

    expect(screen.getByTestId("settings-location").textContent).toBe("/settings?section=JJ");
  });
});
