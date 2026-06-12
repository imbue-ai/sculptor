import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AlphaToolPill } from "../AlphaToolPill.tsx";
import type { PillData } from "../toolPill.types.ts";

const createPillData = (overrides: Partial<PillData> = {}): PillData => ({
  id: "pill-1",
  label: "Read",
  state: "completed",
  blocks: [],
  results: [],
  ...overrides,
});

type PillProps = React.ComponentProps<typeof AlphaToolPill>;

// Tooltip (Radix Themes) requires a TooltipProvider supplied by `Theme`.
const renderPill = (overrides: Partial<PillProps> = {}): ReturnType<typeof render> => {
  const defaultProps: PillProps = {
    pillData: createPillData(),
    isOpen: false,
    onToggle: vi.fn(),
    ...overrides,
  };
  return render(
    <Theme>
      <AlphaToolPill {...defaultProps} />
    </Theme>,
  );
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("AlphaToolPill", () => {
  describe("rendering", () => {
    it("renders the label", () => {
      renderPill({ pillData: createPillData({ label: "Grep" }) });
      expect(screen.getByText("Grep")).toBeInTheDocument();
    });

    it("renders as a button", () => {
      renderPill();
      expect(screen.getByRole("button")).toBeInTheDocument();
    });
  });

  describe("state classes", () => {
    it("applies open class when isOpen is true", () => {
      const { container } = renderPill({ isOpen: true });
      expect(container.querySelector(".pillOpen")).toBeInTheDocument();
    });

    it("does not apply open class when isOpen is false", () => {
      const { container } = renderPill({ isOpen: false });
      expect(container.querySelector(".pillOpen")).not.toBeInTheDocument();
    });

    it("applies error class when state is error", () => {
      const { container } = renderPill({
        pillData: createPillData({ state: "error" }),
      });
      expect(container.querySelector(".pillError")).toBeInTheDocument();
    });

    it("shows the executing status dot for an in-flight Bash pill", () => {
      renderPill({
        pillData: createPillData({ label: "Bash", state: "initializing" }),
      });
      expect(screen.getByLabelText("executing")).toBeInTheDocument();
    });

    it("hides the executing status dot for completed Bash pills", () => {
      renderPill({
        pillData: createPillData({ label: "Bash", state: "completed" }),
      });
      expect(screen.queryByLabelText("executing")).not.toBeInTheDocument();
    });
  });

  describe("interactions", () => {
    it("calls onToggle when clicked in completed state", () => {
      const onToggle = vi.fn();
      renderPill({ onToggle });
      fireEvent.click(screen.getByRole("button"));
      expect(onToggle).toHaveBeenCalledOnce();
    });

    it("calls onToggle when clicked in error state", () => {
      const onToggle = vi.fn();
      renderPill({ pillData: createPillData({ state: "error" }), onToggle });
      fireEvent.click(screen.getByRole("button"));
      expect(onToggle).toHaveBeenCalledOnce();
    });
  });
});
