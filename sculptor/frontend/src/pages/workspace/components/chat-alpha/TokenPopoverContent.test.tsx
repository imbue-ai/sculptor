import { Theme } from "@radix-ui/themes";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { TurnMetrics } from "~/api";
import { ElementIds } from "~/api";

import { TokenPopoverContent } from "./TokenPopoverContent.tsx";

const renderWithProviders = (ui: React.ReactElement): ReturnType<typeof render> => render(<Theme>{ui}</Theme>);

afterEach(cleanup);

describe("TokenPopoverContent", () => {
  it("renders input and output token rows", () => {
    const metrics: TurnMetrics = {
      durationSeconds: 5.0,
      inputTokens: 1234,
      outputTokens: 567,
    };
    renderWithProviders(<TokenPopoverContent turnMetrics={metrics} />);

    expect(screen.getByText("Input")).toBeTruthy();
    expect(screen.getByText("1,234")).toBeTruthy();
    expect(screen.getByText("Output")).toBeTruthy();
    expect(screen.getByText("567")).toBeTruthy();
  });

  it("shows reasoning tokens row when reasoning tokens are present and > 0", () => {
    const metrics: TurnMetrics = {
      durationSeconds: 5.0,
      inputTokens: 100,
      outputTokens: 200,
      reasoningTokens: 350,
    };
    renderWithProviders(<TokenPopoverContent turnMetrics={metrics} />);

    expect(screen.getByText("Reasoning")).toBeTruthy();
    expect(screen.getByText("350")).toBeTruthy();
  });

  it("hides reasoning tokens row when reasoning tokens are 0", () => {
    const metrics: TurnMetrics = {
      durationSeconds: 5.0,
      inputTokens: 100,
      outputTokens: 200,
      reasoningTokens: 0,
    };
    renderWithProviders(<TokenPopoverContent turnMetrics={metrics} />);

    expect(screen.queryByText("Reasoning")).toBeNull();
  });

  it("hides reasoning tokens row when reasoning tokens are undefined", () => {
    const metrics: TurnMetrics = {
      durationSeconds: 5.0,
      inputTokens: 100,
      outputTokens: 200,
    };
    renderWithProviders(<TokenPopoverContent turnMetrics={metrics} />);

    expect(screen.queryByText("Reasoning")).toBeNull();
  });

  it("formats large numbers with locale separators", () => {
    const metrics: TurnMetrics = {
      durationSeconds: 5.0,
      inputTokens: 12450,
      outputTokens: 8321,
      reasoningTokens: 3200,
    };
    renderWithProviders(<TokenPopoverContent turnMetrics={metrics} />);

    expect(screen.getByText("12,450")).toBeTruthy();
    expect(screen.getByText("8,321")).toBeTruthy();
    expect(screen.getByText("3,200")).toBeTruthy();
  });

  it("renders with data-testid", () => {
    const metrics: TurnMetrics = {
      durationSeconds: 5.0,
      inputTokens: 100,
      outputTokens: 200,
    };
    renderWithProviders(<TokenPopoverContent turnMetrics={metrics} />);

    expect(screen.getByTestId(ElementIds.TOKEN_POPOVER)).toBeTruthy();
  });

  it("displays 0 for input/output tokens when they are nullish", () => {
    const metrics: TurnMetrics = {
      durationSeconds: 5.0,
    } as TurnMetrics;
    renderWithProviders(<TokenPopoverContent turnMetrics={metrics} />);

    const zeros = screen.getAllByText("0");
    expect(zeros).toHaveLength(2);
  });
});
