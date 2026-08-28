import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { TurnMetrics } from "~/api";
import { ElementIds } from "~/api";

import { TurnFooter } from "./TurnFooter.tsx";
import type { TurnFile } from "./useTurnSummaryData";

const renderWithProviders = (ui: React.ReactElement): ReturnType<typeof render> => render(<Theme>{ui}</Theme>);

afterEach(cleanup);

const METRICS: TurnMetrics = {
  durationSeconds: 8.0,
  inputTokens: 500,
  outputTokens: 400,
};

const SINGLE_FILE: ReadonlyArray<TurnFile> = [{ path: "sculptor/backend/utils/pagination.py", status: "modified" }];

const MULTI_FILES: ReadonlyArray<TurnFile> = [
  { path: "sculptor/backend/models/user.py", status: "modified" },
  { path: "sculptor/backend/utils/validators.py", status: "modified" },
  { path: "sculptor/backend/tests/test_user.py", status: "modified" },
];

describe("TurnFooter", () => {
  it("renders with data-testid", () => {
    renderWithProviders(<TurnFooter metrics={METRICS} />);
    expect(screen.getByTestId(ElementIds.TURN_FOOTER)).toBeTruthy();
  });

  it("renders even when neither metrics nor stopped are provided", () => {
    renderWithProviders(<TurnFooter />);
    expect(screen.getByTestId(ElementIds.TURN_FOOTER)).toBeTruthy();
  });

  it("renders with only files and no metrics", () => {
    renderWithProviders(<TurnFooter files={SINGLE_FILE} />);
    const footer = screen.getByTestId(ElementIds.TURN_FOOTER);
    expect(footer).toBeTruthy();
    expect(screen.getByText("1 file changed")).toBeTruthy();
  });

  it("renders duration", () => {
    renderWithProviders(<TurnFooter metrics={METRICS} />);
    const footer = screen.getByTestId(ElementIds.TURN_FOOTER);
    expect(footer.textContent).toContain("8.0s");
  });

  it("renders token count", () => {
    renderWithProviders(<TurnFooter metrics={METRICS} />);
    expect(screen.getByText("900 tokens")).toBeTruthy();
  });

  it("renders Stopped label when stopped", () => {
    renderWithProviders(<TurnFooter stopped={true} metrics={METRICS} />);
    expect(screen.getByText("Stopped")).toBeTruthy();
  });

  describe("file changes", () => {
    it("shows file count trigger for a single file", () => {
      renderWithProviders(<TurnFooter metrics={METRICS} files={SINGLE_FILE} />);
      expect(screen.getByText("1 file changed")).toBeTruthy();
    });

    it("shows file count trigger for multiple files", () => {
      renderWithProviders(<TurnFooter metrics={METRICS} files={MULTI_FILES} />);
      expect(screen.getByText("3 files changed")).toBeTruthy();
    });

    it("does not show file changes when files prop is undefined", () => {
      renderWithProviders(<TurnFooter metrics={METRICS} />);
      const footer = screen.getByTestId(ElementIds.TURN_FOOTER);
      expect(footer.textContent).not.toContain("file");
    });

    it("does not show file changes when files array is empty", () => {
      renderWithProviders(<TurnFooter metrics={METRICS} files={[]} />);
      const footer = screen.getByTestId(ElementIds.TURN_FOOTER);
      expect(footer.textContent).toBe("8.0s · 900 tokens");
    });

    it("shows middot separator between tokens and file changes", () => {
      renderWithProviders(<TurnFooter metrics={METRICS} files={SINGLE_FILE} />);
      const footer = screen.getByTestId(ElementIds.TURN_FOOTER);
      expect(footer.textContent).toContain("tokens");
      expect(footer.textContent).toContain("1 file changed");
    });

    it("opens popover with file list when file count is clicked", async () => {
      renderWithProviders(<TurnFooter metrics={METRICS} files={MULTI_FILES} />);

      fireEvent.click(screen.getByText("3 files changed"));

      await waitFor(() => {
        expect(screen.getByText("user.py")).toBeTruthy();
      });

      expect(screen.getByText("validators.py")).toBeTruthy();
      expect(screen.getByText("test_user.py")).toBeTruthy();
    });

    it("calls onFileClick when a popover file row is clicked", async () => {
      const handleFileClick = vi.fn();
      renderWithProviders(<TurnFooter metrics={METRICS} files={SINGLE_FILE} onFileClick={handleFileClick} />);

      fireEvent.click(screen.getByText("1 file changed"));

      await waitFor(() => {
        expect(screen.getByText("pagination.py")).toBeTruthy();
      });

      const fileRow = screen.getByText("pagination.py").closest("[role='button']");
      expect(fileRow).toBeTruthy();
      fireEvent.click(fileRow!);

      expect(handleFileClick).toHaveBeenCalledWith("sculptor/backend/utils/pagination.py");
    });

    it("keeps popover open after clicking a file row even if scroll fires", async () => {
      const handleFileClick = vi.fn();
      renderWithProviders(<TurnFooter metrics={METRICS} files={MULTI_FILES} onFileClick={handleFileClick} />);

      fireEvent.click(screen.getByText("3 files changed"));

      await waitFor(() => {
        expect(screen.getByText("user.py")).toBeTruthy();
      });

      const fileRow = screen.getByText("user.py").closest("[role='button']");
      fireEvent.click(fileRow!);

      // Simulate a scroll event (e.g. from diff panel opening and resizing the layout)
      fireEvent.scroll(window);

      expect(screen.getByText("user.py")).toBeTruthy();
      expect(screen.getByText("validators.py")).toBeTruthy();
      expect(screen.getByText("test_user.py")).toBeTruthy();
    });

    it("shows file changes alongside stopped label", () => {
      renderWithProviders(<TurnFooter stopped={true} metrics={METRICS} files={SINGLE_FILE} />);
      expect(screen.getByText("Stopped")).toBeTruthy();
      expect(screen.getByText("1 file changed")).toBeTruthy();
    });

    it("navigates file rows via keyboard Enter key", async () => {
      const handleFileClick = vi.fn();
      renderWithProviders(<TurnFooter metrics={METRICS} files={SINGLE_FILE} onFileClick={handleFileClick} />);

      fireEvent.click(screen.getByText("1 file changed"));

      await waitFor(() => {
        expect(screen.getByText("pagination.py")).toBeTruthy();
      });

      const fileRow = screen.getByText("pagination.py").closest("[role='button']");
      expect(fileRow).toBeTruthy();
      fireEvent.keyDown(fileRow!, { key: "Enter" });

      expect(handleFileClick).toHaveBeenCalledWith("sculptor/backend/utils/pagination.py");
    });

    it("navigates file rows via keyboard Space key", async () => {
      const handleFileClick = vi.fn();
      renderWithProviders(<TurnFooter metrics={METRICS} files={SINGLE_FILE} onFileClick={handleFileClick} />);

      fireEvent.click(screen.getByText("1 file changed"));

      await waitFor(() => {
        expect(screen.getByText("pagination.py")).toBeTruthy();
      });

      const fileRow = screen.getByText("pagination.py").closest("[role='button']");
      expect(fileRow).toBeTruthy();
      fireEvent.keyDown(fileRow!, { key: " " });

      expect(handleFileClick).toHaveBeenCalledWith("sculptor/backend/utils/pagination.py");
    });
  });

  describe("token popover", () => {
    it("opens token popover when token count is clicked", async () => {
      renderWithProviders(<TurnFooter metrics={METRICS} />);

      fireEvent.click(screen.getByText("900 tokens"));

      await waitFor(() => {
        expect(screen.getByTestId(ElementIds.TOKEN_POPOVER)).toBeTruthy();
      });

      expect(screen.getByText("Input")).toBeTruthy();
      expect(screen.getByText("Output")).toBeTruthy();
    });

    it("shows reasoning tokens in popover when present", async () => {
      const metricsWithReasoning: TurnMetrics = {
        durationSeconds: 8.0,
        inputTokens: 500,
        outputTokens: 400,
        reasoningTokens: 200,
      };
      renderWithProviders(<TurnFooter metrics={metricsWithReasoning} />);

      // Total is 500 + 400 + 200 = 1,100
      fireEvent.click(screen.getByText("1,100 tokens"));

      await waitFor(() => {
        expect(screen.getByTestId(ElementIds.TOKEN_POPOVER)).toBeTruthy();
      });

      expect(screen.getByText("Reasoning")).toBeTruthy();
      expect(screen.getByText("200")).toBeTruthy();
    });

    it("includes reasoning tokens in total count", () => {
      const metricsWithReasoning: TurnMetrics = {
        durationSeconds: 8.0,
        inputTokens: 500,
        outputTokens: 400,
        reasoningTokens: 100,
      };
      renderWithProviders(<TurnFooter metrics={metricsWithReasoning} />);
      // Total should be 500 + 400 + 100 = 1,000
      expect(screen.getByText("1,000 tokens")).toBeTruthy();
    });
  });

  describe("edge cases", () => {
    it("shows only file changes when metrics are absent", () => {
      renderWithProviders(<TurnFooter files={MULTI_FILES} />);
      const footer = screen.getByTestId(ElementIds.TURN_FOOTER);
      expect(footer.textContent).toContain("3 files changed");
      expect(footer.textContent).not.toContain("tokens");
      // No duration should appear (no "X.Xs" pattern)
      expect(footer.textContent).not.toMatch(/\d+\.\d+s/);
    });

    it("shows stopped with duration but no tokens when metrics have no token counts", () => {
      const metricsNoTokens: TurnMetrics = {
        durationSeconds: 3.5,
      } as TurnMetrics;
      renderWithProviders(<TurnFooter stopped={true} metrics={metricsNoTokens} />);
      expect(screen.getByText("Stopped")).toBeTruthy();
      const footer = screen.getByTestId(ElementIds.TURN_FOOTER);
      expect(footer.textContent).toContain("3.5s");
    });

    it("renders an empty footer when no props are provided", () => {
      renderWithProviders(<TurnFooter />);
      const footer = screen.getByTestId(ElementIds.TURN_FOOTER);
      expect(footer.textContent).toBe("");
    });
  });
});
