import { Theme } from "@radix-ui/themes";
import { cleanup, render as rtlRender } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ToolResultBlock, ToolUseBlock } from "~/api";
import type { SubagentTreeNode } from "~/pages/workspace/utils/subagentTree.ts";

import { ToolBlockGroup } from "./AlphaToolGroup.tsx";

// The component reads workspace params and per-harness capability hooks; mock
// them so the group renders without the full app/router/jotai context.
vi.mock("~/common/NavigateUtils.ts", () => ({
  useWorkspacePageParams: (): { workspaceID: string; agentID: string } => ({
    workspaceID: "ws-1",
    agentID: "agent-1",
  }),
}));

vi.mock("~/common/state/hooks/useTaskHelpers.ts", () => ({
  useTaskSupportsSubAgents: (): boolean => true,
  useTaskSupportsInteractiveBackchannel: (): boolean => true,
}));

const ThemeWrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;
const render = (ui: ReactElement): ReturnType<typeof rtlRender> => rtlRender(ui, { wrapper: ThemeWrapper });

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

// A top-level (EnterPlanMode) tool_use block routes through the `topLevelBlocks`
// branch, which sets `isExecuting = inProgressMessageId != null && !hasResult`.
// ToolLine renders a PulsingDot when executing, otherwise a chevron icon.
function planModeBlock(): ToolUseBlock {
  return { type: "tool_use", id: "tool-1", name: "EnterPlanMode", input: {} };
}

function emptyNode(): SubagentTreeNode {
  return { children: new Map() } as SubagentTreeNode;
}

describe("ToolBlockGroup", () => {
  // Regression: the executing check used `inProgressMessageId !== null`, so an
  // `undefined` value slipped past (undefined !== null is true) and rendered the
  // tool as in-progress. The fix uses `!= null`, which is false for undefined.
  it("does not render a tool as executing when inProgressMessageId is undefined", () => {
    const { container } = render(
      <ToolBlockGroup
        blocks={[planModeBlock()]}
        node={emptyNode()}
        toolResultMap={new Map<string, ToolResultBlock>()}
        subagentMetadataMap={new Map()}
        inProgressMessageId={undefined}
        isActive={false}
      />,
    );

    // The pulsing dot is the executing/in-progress indicator. With the old
    // `!== null` check, undefined would have rendered it.
    expect(container.querySelector('[class*="pulsingDot"]')).toBeNull();
    // Sanity: the tool line itself rendered, just not in the executing state.
    expect(container.querySelector('[class*="toolName"]')!.textContent).toBe("EnterPlanMode");
  });

  it("renders the tool as executing when inProgressMessageId is a real id (and no result yet)", () => {
    const { container } = render(
      <ToolBlockGroup
        blocks={[planModeBlock()]}
        node={emptyNode()}
        toolResultMap={new Map<string, ToolResultBlock>()}
        subagentMetadataMap={new Map()}
        inProgressMessageId="msg-1"
        isActive={true}
      />,
    );

    // A genuine in-progress message id keeps the executing indicator showing,
    // confirming the test distinguishes executing from non-executing.
    expect(container.querySelector('[class*="pulsingDot"]')).not.toBeNull();
  });
});
