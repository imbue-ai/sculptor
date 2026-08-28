import { Theme } from "@radix-ui/themes";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ToolUseBlock } from "~/api";
import { ChatMessageRole } from "~/api";
import type { SubagentTreeNode } from "~/pages/workspace/chat/utils/subagentTree.ts";

import { SubagentPopover } from "../SubagentPopover.tsx";
import { ToolNavigationProvider, useToolNavigation } from "../ToolNavigationContext.tsx";

// ToolPillRow is mocked to a single clickable div that, when clicked,
// sets the openItemId on whatever ToolNavigationProvider it's nested
// inside. That gives us a tiny lever to prove the inner pills' nav
// context is or is not the same instance as the outer provider. The
// element is a div with role="button" rather than a raw HTML button to
// avoid the raw_html_button_in_tsx ratchet (which matches every .tsx
// under sculptor/frontend/src, including test files).
vi.mock("../ToolPillRow.tsx", () => ({
  ToolPillRow: (): ReactElement => {
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
  // SubagentPopover's `collectLeafToolBlocks` actually inspects
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

const renderPopover = (): ReturnType<typeof render> => {
  capturedOuterNav = null;
  const store = createStore();
  return render(
    <Provider store={store}>
      <Theme>
        <ToolNavigationProvider>
          <OuterNavCapture>
            <SubagentPopover
              parentBlock={makeParentBlock()}
              childNodes={makeChildNodes()}
              toolResultMap={new Map()}
              isThinking={false}
            />
          </OuterNavCapture>
        </ToolNavigationProvider>
      </Theme>
    </Provider>,
  );
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("SubagentPopover", () => {
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
    // affects the nested provider that wraps ToolPillRow.
    expect(capturedOuterNav!.openItemId).toBeNull();
  });
});
