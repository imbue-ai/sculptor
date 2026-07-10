import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PiLoginDialog } from "./PiLoginDialog.tsx";

const { mockStartPiLogin, mockFinishPiLogin, mockGetPiLoginStatus } = vi.hoisted(() => ({
  mockStartPiLogin: vi.fn(),
  mockFinishPiLogin: vi.fn(),
  mockGetPiLoginStatus: vi.fn(),
}));

vi.mock("~/api", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...(actual as object),
    startPiLogin: mockStartPiLogin,
    finishPiLogin: mockFinishPiLogin,
    getPiLoginStatus: mockGetPiLoginStatus,
  };
});

// The real terminal opens a PTY WebSocket; the stub only exposes the Done control.
vi.mock("./PiLoginTerminal.tsx", () => ({
  PiLoginTerminal: ({ loginId, onDone }: { loginId: string; onDone: () => void }): ReactElement => (
    <div data-testid="fake-login-terminal" data-login-id={loginId}>
      <div data-testid="fake-login-done" onClick={onDone}>
        Done
      </div>
    </div>
  ),
}));

const renderDialog = (mode: "login" | "logout", onClose: () => void = vi.fn()): void => {
  render(
    <Theme>
      <PiLoginDialog request={{ providerId: "openai", displayName: "OpenAI", mode }} onClose={onClose} />
    </Theme>,
  );
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("PiLoginDialog", () => {
  it("starts the login session immediately on mount, with no intro step", async () => {
    mockStartPiLogin.mockResolvedValue({ data: { loginId: "login-1" } });
    mockGetPiLoginStatus.mockResolvedValue({ data: { completed: false } });

    renderDialog("login");

    const terminal = await screen.findByTestId("fake-login-terminal");
    expect(terminal.getAttribute("data-login-id")).toBe("login-1");
    expect(mockStartPiLogin).toHaveBeenCalledWith(
      expect.objectContaining({ body: { mode: "login", providerId: "openai" } }),
    );
    expect(screen.queryByText("Open pi login")).toBeNull();
  });

  it("shows an error when the session cannot start", async () => {
    mockStartPiLogin.mockRejectedValue(new Error("no pi"));

    renderDialog("login");

    expect(await screen.findByText(/Could not start the pi session/)).toBeTruthy();
  });

  it("tears the session down and closes on Done", async () => {
    mockStartPiLogin.mockResolvedValue({ data: { loginId: "login-2" } });
    mockGetPiLoginStatus.mockResolvedValue({ data: { completed: false } });
    mockFinishPiLogin.mockResolvedValue({ data: {} });
    const onClose = vi.fn();

    renderDialog("login", onClose);

    fireEvent.click(await screen.findByTestId("fake-login-done"));

    await waitFor(() => {
      expect(onClose).toHaveBeenCalledTimes(1);
    });
    expect(mockFinishPiLogin).toHaveBeenCalledWith(expect.objectContaining({ path: { login_id: "login-2" } }));
  });
});
