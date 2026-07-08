import { Theme } from "@radix-ui/themes";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ToolUseBlock } from "~/api";
import { ChatMessageRole } from "~/api";
import type { SubagentMetadata, SubagentTreeNode } from "~/pages/workspace/utils/subagentTree.ts";

import { AlphaSubagentPopover } from "../AlphaSubagentPopover.tsx";
import { ChatTaskProvider } from "../ChatTaskContext.tsx";
import { ToolNavigationProvider, useToolNavigation } from "../ToolNavigationContext.tsx";

// AlphaToolPillRow is mocked to a single clickable div that, when clicked,
// sets the openItemId on whatever ToolNavigationProvider it's nested
// inside. That gives us a tiny lever to prove the inner pills' nav
// context is or is not the same instance as the outer provider. The
// element is a div with role="button" rather than a raw HTML button to
// avoid the raw_html_button_in_tsx ratchet (which matches every .tsx
// under sculptor/frontend/src, including test files).
vi.mock("../AlphaToolPillRow.tsx", () => ({
  AlphaToolPillRow: (): ReactElement => {
    const nav = useToolNavigation();
    return (
      <div data-testid="mock-inner-pill" role="button" tabIndex={0} onClick={() => nav?.setOpenItemId("inner-pill-id")}>
        inner pill
      </div>
    );
  },
}));

const TOOL_USE_ID = "toolu_subagent_001";

const makeParentBlock = (): ToolUseBlock => ({
  id: TOOL_USE_ID,
  name: "Agent",
  type: "tool_use",
  input: { prompt: "Explore", description: "Explore" },
});

const makeChildNodes = (): Array<SubagentTreeNode> => {
  const childToolUse: ToolUseBlock = {
    id: "toolu_inner_001",
    name: "Read",
    type: "tool_use",
    input: { file_path: "/tmp/inner.txt" },
  };
  // Cast through `unknown` because we only need the shape that
  // AlphaSubagentPopover's `collectLeafToolBlocks` actually inspects
  // (`role`, `content`). Filling in every required ChatMessage field would
  // add noise without changing the test's behavior.
  const message = {
    id: "msg-inner",
    role: ChatMessageRole.ASSISTANT,
    content: [childToolUse],
    parentToolUseId: TOOL_USE_ID,
    approximateCreationTime: 0,
  } as unknown as SubagentTreeNode["message"];
  return [{ message, children: new Map() }];
};

type Nav = NonNullable<ReturnType<typeof useToolNavigation>>;

let capturedOuterNav: Nav | null = null;
const OuterNavCapture = ({ children }: { children: ReactNode }): ReactElement => {
  // Test-only: capture the hook's value into an outer variable so assertions can
  // read it. This render-time write is intentional and safe in a test harness.
  // eslint-disable-next-line react-hooks/globals
  capturedOuterNav = useToolNavigation();
  return <>{children}</>;
};

const renderPopover = (
  options: {
    metadata?: SubagentMetadata;
    isThinking?: boolean;
    childNodes?: Array<SubagentTreeNode>;
  } = {},
): ReturnType<typeof render> => {
  capturedOuterNav = null;
  const store = createStore();
  return render(
    <Provider store={store}>
      <Theme>
        {/* AlphaMarkdownBlock (the Response body) reads the chat panel's
            identity and the workspace route params, so the popover needs a
            ChatTaskProvider ancestor and a workspace route, just like in the
            real chat surface. */}
        <MemoryRouter initialEntries={["/workspaces/ws-test"]}>
          <Routes>
            <Route
              path="/workspaces/:workspaceID"
              element={
                <ChatTaskProvider workspaceId="ws-test" taskId="task-test">
                  <ToolNavigationProvider>
                    <OuterNavCapture>
                      <AlphaSubagentPopover
                        parentBlock={makeParentBlock()}
                        childNodes={options.childNodes ?? makeChildNodes()}
                        toolResultMap={new Map()}
                        metadata={options.metadata}
                        isThinking={options.isThinking ?? false}
                      />
                    </OuterNavCapture>
                  </ToolNavigationProvider>
                </ChatTaskProvider>
              }
            />
          </Routes>
        </MemoryRouter>
      </Theme>
    </Provider>,
  );
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("AlphaSubagentPopover", () => {
  it("isolates inner tool pills' nav context from the parent provider", () => {
    // Regression: previously the subagent pill and its inner tool pills shared
    // a single ToolNavigationProvider's `openItemId`. Opening any inner pill
    // would set openItemId to that pill's id, which flipped the subagent
    // pill's `isOpen` (computed as `openItemId === parentBlock.id`) to false
    // and collapsed the entire subagent popover.
    renderPopover();

    expect(capturedOuterNav).not.toBeNull();
    expect(capturedOuterNav!.openItemId).toBeNull();

    const innerPill = screen.getByTestId("mock-inner-pill");
    act(() => {
      fireEvent.click(innerPill);
    });

    // The outer provider's openItemId must stay null — the inner click only
    // affects the nested provider that wraps AlphaToolPillRow.
    expect(capturedOuterNav!.openItemId).toBeNull();
  });

  // SCU-1792: background agents (explicit run_in_background or harness-
  // converted async agents) get a user-facing status body instead of the
  // agent-facing launch-ack, plus a note that the tool list is incomplete.
  describe("background agents", () => {
    it("shows a running status line while the agent is still working", () => {
      renderPopover({ metadata: { isBackground: true }, isThinking: true });
      expect(screen.getByText(/Running in the background/)).toBeTruthy();
    });

    it("shows a response-unavailable status when the agent finished without a captured response", () => {
      renderPopover({ metadata: { isBackground: true, stillRunning: false }, isThinking: false });
      expect(screen.getByText(/response wasn't captured/)).toBeTruthy();
    });

    it("shows the real response once it arrives, not a status line", () => {
      renderPopover({ metadata: { isBackground: true, responseText: "All done." }, isThinking: false });
      expect(screen.getByText("All done.")).toBeTruthy();
      expect(screen.queryByText(/Running in the background/)).toBeNull();
    });

    it("notes that only pre-conversion tool calls are shown when some are present", () => {
      renderPopover({ metadata: { isBackground: true }, isThinking: true });
      expect(screen.getByText(/Only tool calls from before the agent moved to the background/)).toBeTruthy();
    });

    it("notes that tool calls aren't shown at all when none streamed inline", () => {
      renderPopover({ metadata: { isBackground: true }, isThinking: true, childNodes: [] });
      expect(screen.getByText(/tool calls run in the background and aren't shown/)).toBeTruthy();
    });

    it("renders neither status nor note for foreground agents", () => {
      renderPopover({ metadata: {}, isThinking: true });
      expect(screen.queryByText(/Running in the background/)).toBeNull();
      expect(screen.queryByText(/moved to the background/)).toBeNull();
    });
  });
});
