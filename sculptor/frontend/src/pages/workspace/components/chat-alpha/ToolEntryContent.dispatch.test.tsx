import { Theme } from "@radix-ui/themes";
import { cleanup, render as rtlRender, screen } from "@testing-library/react";
import type { ComponentType, ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ToolResultBlock, ToolUseBlock } from "~/api";
import { PluginErrorBoundary } from "~/plugins/PluginErrorBoundary.tsx";
import type { PluginToolVisualization } from "~/plugins/pluginRegistry.ts";
import type { ToolCallView } from "~/plugins/types.ts";

import type * as PluginToolViz from "./pluginToolViz.ts";

// The registry dispatch reads the current workspace/task; stub it so the entry
// renders without the full app/router/jotai context. The visualization the
// dispatch returns is controlled per-test via the mock below.
vi.mock("~/common/NavigateUtils.ts", () => ({
  useWorkspacePageParams: (): { workspaceID: string; agentID: string } => ({ workspaceID: "ws-1", agentID: "a-1" }),
}));

const dispatch = vi.hoisted(() => ({ visualization: null as PluginToolVisualization | null }));

vi.mock("./pluginToolViz.ts", async (importOriginal) => {
  const actual = await importOriginal<typeof PluginToolViz>();
  return {
    ...actual,
    usePluginToolVisualization: (inputs: {
      block: ToolUseBlock | null;
      result: ToolResultBlock | null;
    }): { visualization: PluginToolVisualization | null; call: ToolCallView } => ({
      visualization: dispatch.visualization,
      call: actual.buildToolCallView({ ...inputs, pillState: "completed", agentType: "claude" }),
    }),
  };
});

// Imported after the mocks so the component picks up the stubbed dispatch.
const { ToolEntryContent } = await import("./AlphaToolPopover.tsx");

const ThemeWrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;
const render = (ui: ReactElement): ReturnType<typeof rtlRender> => rtlRender(ui, { wrapper: ThemeWrapper });

const makeVisualization = (body: ComponentType<{ call: ToolCallView }>): PluginToolVisualization => ({
  definition: {
    id: "viz",
    toolNames: ["Workflow"],
    body,
    summary: () => ({ title: "Plugin summary" }),
  },
  // The wrapped body the chat actually mounts renders the plugin body inside the
  // real error boundary, so a body crash degrades to the host-supplied
  // `fallback` — mirroring the loader's wrap.
  wrappedBody: ({ call, fallback }): ReactElement => {
    const Body = body;
    return (
      <PluginErrorBoundary pluginId="plugin-viz" pluginName="viz" fallback={fallback}>
        <Body call={call} />
      </PluginErrorBoundary>
    );
  },
  pluginId: "plugin-viz",
});

const block: ToolUseBlock = { type: "tool_use", id: "t-1", name: "Workflow", input: { script: "s" } };
const result: ToolResultBlock = {
  type: "tool_result",
  toolUseId: "t-1",
  toolName: "Workflow",
  invocationString: "Workflow(...)",
  content: { contentType: "generic", text: "stock body text" },
};

afterEach(() => {
  dispatch.visualization = null;
  vi.clearAllMocks();
  cleanup();
});

describe("ToolEntryContent plugin dispatch", () => {
  it("renders the built-in DefaultEntry when no plugin matches", () => {
    dispatch.visualization = null;
    render(<ToolEntryContent toolName="Workflow" block={block} result={result} workspaceCodePath={null} />);
    expect(screen.getByText("stock body text")).toBeTruthy();
    expect(screen.queryByText("Plugin summary")).toBeNull();
  });

  it("renders the plugin summary and body when a visualization matches", () => {
    dispatch.visualization = makeVisualization(() => <div>plugin body</div>);
    render(<ToolEntryContent toolName="Workflow" block={block} result={result} workspaceCodePath={null} />);
    expect(screen.getByText("Plugin summary")).toBeTruthy();
    expect(screen.getByText("plugin body")).toBeTruthy();
  });

  it("degrades a crashing plugin body to the stock rendering", () => {
    dispatch.visualization = makeVisualization(() => {
      throw new Error("body crash");
    });
    render(<ToolEntryContent toolName="Workflow" block={block} result={result} workspaceCodePath={null} />);
    // The summary header still renders; the body falls back to the stock entry.
    expect(screen.getByText("Plugin summary")).toBeTruthy();
    expect(screen.getByText("stock body text")).toBeTruthy();
  });
});
