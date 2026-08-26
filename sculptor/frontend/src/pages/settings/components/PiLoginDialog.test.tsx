import { Theme } from "@radix-ui/themes";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProviderGroup } from "~/api";

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

const renderDialog = (
  mode: "login" | "logout",
  onClose: () => void = vi.fn(),
  {
    supportsSubscription = false,
    group = ProviderGroup.SINGLE_KEY,
  }: { supportsSubscription?: boolean; group?: ProviderGroup } = {},
): void => {
  render(
    <Theme>
      <PiLoginDialog
        request={{ providerId: "openai", displayName: "OpenAI", mode, supportsSubscription, group }}
        onClose={onClose}
      />
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

  it("tells an API-key-only provider's user that pi opens at the key input", async () => {
    mockStartPiLogin.mockResolvedValue({ data: { loginId: "login-3" } });
    mockGetPiLoginStatus.mockResolvedValue({ data: { completed: false } });

    renderDialog("login");

    await screen.findByTestId("fake-login-terminal");
    expect(screen.getByText(/Enter your OpenAI API key/)).toBeTruthy();
  });

  it("tells a subscription-capable provider's user to choose a sign-in method", async () => {
    mockStartPiLogin.mockResolvedValue({ data: { loginId: "login-4" } });
    mockGetPiLoginStatus.mockResolvedValue({ data: { completed: false } });

    renderDialog("login", vi.fn(), { supportsSubscription: true });

    await screen.findByTestId("fake-login-terminal");
    expect(screen.getByText(/Choose how to sign in/)).toBeTruthy();
  });

  it("tells a subscription-only provider's user that pi opens the subscription sign-in", async () => {
    mockStartPiLogin.mockResolvedValue({ data: { loginId: "login-5" } });
    mockGetPiLoginStatus.mockResolvedValue({ data: { completed: false } });

    renderDialog("login", vi.fn(), { supportsSubscription: true, group: ProviderGroup.SUBSCRIPTION_ONLY });

    await screen.findByTestId("fake-login-terminal");
    expect(screen.getByText(/subscription sign-in/)).toBeTruthy();
  });

  it("shows an error when the session cannot start", async () => {
    mockStartPiLogin.mockRejectedValue(new Error("no pi"));

    renderDialog("login");

    expect(await screen.findByText(/Could not start the pi session/)).toBeTruthy();
  });

  it("reaps the live session when the dialog unmounts without an explicit teardown", async () => {
    mockStartPiLogin.mockResolvedValue({ data: { loginId: "login-6" } });
    mockGetPiLoginStatus.mockResolvedValue({ data: { completed: false } });
    mockFinishPiLogin.mockResolvedValue({ data: {} });

    const { unmount } = render(
      <Theme>
        <PiLoginDialog
          request={{
            providerId: "openai",
            displayName: "OpenAI",
            mode: "login",
            supportsSubscription: false,
            group: ProviderGroup.SINGLE_KEY,
          }}
          onClose={vi.fn()}
        />
      </Theme>,
    );
    await screen.findByTestId("fake-login-terminal");
    unmount();

    await waitFor(() => {
      expect(mockFinishPiLogin).toHaveBeenCalledWith(expect.objectContaining({ path: { login_id: "login-6" } }));
    });
  });

  it("keeps the status poll single-flight while a request is still pending", async () => {
    vi.useFakeTimers();
    try {
      mockStartPiLogin.mockResolvedValue({ data: { loginId: "login-7" } });
      // A status request that never settles: further interval ticks must not stack.
      mockGetPiLoginStatus.mockImplementation(() => new Promise(() => undefined));

      renderDialog("login");
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1300);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1300);
      });

      expect(mockGetPiLoginStatus).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
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
