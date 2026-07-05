import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ToolResultBlock, ToolUseBlock } from "~/api";
import { ElementIds } from "~/api";

import { CommandPopover } from "../CommandPopover.tsx";

// Avoid timer side effects in tests
vi.mock("../useElapsedTime.ts", () => ({
  useElapsedTime: (): { elapsed: string } => ({ elapsed: "1.5" }),
}));

const TOOL_USE_ID = "toolu_bash_001";

const createToolUse = (overrides: Partial<ToolUseBlock> = {}): ToolUseBlock => ({
  id: TOOL_USE_ID,
  name: "Bash",
  type: "tool_use",
  input: { command: "ls -la" },
  ...overrides,
});

const createToolResult = (overrides: Partial<ToolResultBlock> = {}): ToolResultBlock => ({
  toolUseId: TOOL_USE_ID,
  toolName: "Bash",
  invocationString: "Bash(command='ls -la')",
  content: { contentType: "generic", text: "" },
  isError: false,
  durationSeconds: 0.0,
  ...overrides,
});

const renderPopover = (
  props: {
    toolName?: "Bash" | "Monitor";
    block?: ToolUseBlock;
    result?: ToolResultBlock;
    isExecuting?: boolean;
  } = {},
): ReturnType<typeof render> => {
  return render(
    <Theme>
      <CommandPopover
        toolName={props.toolName ?? "Bash"}
        block={props.block}
        result={props.result}
        isExecuting={props.isExecuting ?? false}
      />
    </Theme>,
  );
};

beforeEach(() => {
  // Mock the clipboard API — jsdom doesn't implement it.
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("CommandPopover", () => {
  it("renders the command in the header title", () => {
    const { container } = renderPopover({ block: createToolUse({ input: { command: "ls -la" } }) });
    const title = container.querySelector(".title");
    expect(title).toBeInTheDocument();
    expect(title?.textContent).toContain("ls -la");
  });

  it("shows the description above the command in the header when present", () => {
    const { container } = renderPopover({
      block: createToolUse({ input: { command: "ls -la", description: "List files" } }),
    });
    const title = container.querySelector(".title");
    expect(title?.textContent).toContain("ls -la");
    expect(title?.textContent).toContain("List files");
  });

  it("omits the description when no description is set", () => {
    const { container } = renderPopover({
      block: createToolUse({ input: { command: "ls -la" } }),
    });
    const title = container.querySelector(".title");
    expect(title?.textContent).toBe("ls -la");
  });

  it("formats the duration from result.durationSeconds when not executing", () => {
    renderPopover({
      block: createToolUse(),
      result: createToolResult({ durationSeconds: 5.0 }),
      isExecuting: false,
    });
    expect(screen.getByText("5.0s")).toBeInTheDocument();
  });

  it("uses live elapsed timer while executing", () => {
    renderPopover({
      block: createToolUse(),
      result: undefined,
      isExecuting: true,
    });
    // The mocked useElapsedTime returns "1.5"; formatDuration renders it as "1.5s".
    expect(screen.getByText("1.5s")).toBeInTheDocument();
  });

  it("renders the output text when result has generic content", () => {
    renderPopover({
      block: createToolUse(),
      result: createToolResult({
        content: { contentType: "generic", text: "hello\nworld" },
        durationSeconds: 1.0,
      }),
    });
    const output = screen.getByTestId(ElementIds.ALPHA_CHAT_BASH_OUTPUT);
    expect(output.textContent).toContain("hello");
    expect(output.textContent).toContain("world");
  });

  it("calls clipboard.writeText with the command when copy command is clicked", () => {
    const writeTextSpy = vi.spyOn(navigator.clipboard, "writeText");
    renderPopover({
      block: createToolUse({ input: { command: "echo hi" } }),
      result: createToolResult(),
    });

    fireEvent.click(screen.getByLabelText("Copy command"));

    expect(writeTextSpy).toHaveBeenCalledWith("echo hi");
  });

  it("calls clipboard.writeText with the output when copy output is clicked", () => {
    const writeTextSpy = vi.spyOn(navigator.clipboard, "writeText");
    renderPopover({
      block: createToolUse(),
      result: createToolResult({
        content: { contentType: "generic", text: "captured output" },
      }),
    });

    fireEvent.click(screen.getByLabelText("Copy output"));

    expect(writeTextSpy).toHaveBeenCalledWith("captured output");
  });

  describe("Monitor", () => {
    it("renders the Monitor command and description in the header title", () => {
      const { container } = renderPopover({
        toolName: "Monitor",
        block: createToolUse({
          name: "Monitor",
          input: { command: 'tail -f deploy.log | grep "ERROR"', description: "errors in deploy.log" },
        }),
      });
      const title = container.querySelector(".title");
      expect(title?.textContent).toContain("errors in deploy.log");
      expect(title?.textContent).toContain('tail -f deploy.log | grep "ERROR"');
    });

    it("does not emit the bash output testID for Monitor popovers", () => {
      renderPopover({
        toolName: "Monitor",
        block: createToolUse({ name: "Monitor", input: { command: "tail -f log" } }),
        result: createToolResult({
          toolName: "Monitor",
          content: { contentType: "generic", text: "event" },
        }),
      });
      expect(screen.queryByTestId(ElementIds.ALPHA_CHAT_BASH_OUTPUT)).not.toBeInTheDocument();
    });
  });
});
