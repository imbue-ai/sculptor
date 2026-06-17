import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DependenciesStatus, ErrorBlock } from "~/api";
import { TaskStatus } from "~/api";
import { dependenciesStatusAtom } from "~/common/state/atoms/dependenciesStatus.ts";

import { AlphaErrorBlock } from "./AlphaErrorBlock.tsx";

// Spy on useOpenSettings so the tests can assert which settings section the
// error block navigates to, without exercising the real router/navigation.
const { openSettingsSpy } = vi.hoisted(() => ({
  openSettingsSpy: vi.fn(),
}));
vi.mock("~/common/state/hooks/useOpenSettings.ts", () => ({
  useOpenSettings: (): ((section?: string) => void) => openSettingsSpy,
}));

const makeErrorBlock = (overrides: Partial<ErrorBlock> = {}): ErrorBlock => ({
  type: "error",
  objectType: "ErrorBlock",
  message: "Something went wrong.",
  traceback: "Traceback (most recent call last): ...",
  errorType: "builtins.Exception",
  ...overrides,
});

const renderErrorBlock = (props: {
  block: ErrorBlock;
  isLastMessage?: boolean;
  taskStatus?: TaskStatus;
  onRetryRequest?: () => void;
  dependenciesStatus?: DependenciesStatus | null;
}): ReturnType<typeof render> => {
  const store = createStore();
  store.set(dependenciesStatusAtom, props.dependenciesStatus ?? null);

  const Wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>
      <Theme>{children}</Theme>
    </Provider>
  );

  return render(
    <AlphaErrorBlock
      block={props.block}
      isLastMessage={props.isLastMessage ?? true}
      taskStatus={props.taskStatus ?? TaskStatus.RUNNING}
      onRetryRequest={props.onRetryRequest}
    />,
    { wrapper: Wrapper },
  );
};

afterEach(() => {
  cleanup();
  // openSettingsSpy is hoisted and shared across tests; clear its call history
  // so per-test call-count assertions stay isolated as more tests are added.
  vi.clearAllMocks();
});

describe("AlphaErrorBlock", () => {
  describe("PiBinaryNotFoundError", () => {
    const piBlock = makeErrorBlock({
      message: "Pi binary not found or is invalid.",
      errorType: "sculptor.interfaces.agents.errors.PiBinaryNotFoundError",
    });

    it("shows a friendly 'Pi Not Available' label with the error message", () => {
      renderErrorBlock({ block: piBlock });
      expect(screen.getByText("Pi Not Available")).toBeInTheDocument();
      expect(screen.getByText(/Pi binary not found or is invalid\./)).toBeInTheDocument();
    });

    it("links to the Pi settings section where managed pi can be installed", () => {
      renderErrorBlock({ block: piBlock });
      fireEvent.click(screen.getByText("Go to Settings"));
      expect(openSettingsSpy).toHaveBeenCalledTimes(1);
      expect(openSettingsSpy).toHaveBeenCalledWith("PI");
    });

    it("offers a settings link instead of a retry button", () => {
      renderErrorBlock({ block: piBlock, onRetryRequest: vi.fn() });
      expect(screen.getByText("Go to Settings")).toBeInTheDocument();
      expect(screen.queryByText(/Retry Request/)).not.toBeInTheDocument();
    });
  });

  describe("ClaudeBinaryNotFoundError", () => {
    // Regression: the Pi handling generalizes the original Claude-only block, so
    // Claude must keep linking to its own (DEPENDENCIES) settings section.
    const claudeBlock = makeErrorBlock({
      message: "Claude binary not found or is invalid.",
      errorType: "sculptor.interfaces.agents.errors.ClaudeBinaryNotFoundError",
    });

    it("shows 'Claude Not Available' and links to the Dependencies settings section", () => {
      renderErrorBlock({ block: claudeBlock });
      expect(screen.getByText("Claude Not Available")).toBeInTheDocument();
      fireEvent.click(screen.getByText("Go to Settings"));
      expect(openSettingsSpy).toHaveBeenCalledWith("DEPENDENCIES");
    });
  });

  describe("generic errors", () => {
    it("offers a retry button and no settings link", () => {
      renderErrorBlock({ block: makeErrorBlock(), onRetryRequest: vi.fn() });
      expect(screen.getByText(/Retry Request/)).toBeInTheDocument();
      expect(screen.queryByText("Go to Settings")).not.toBeInTheDocument();
    });
  });
});
