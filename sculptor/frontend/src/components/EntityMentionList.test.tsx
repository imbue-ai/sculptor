import { Theme } from "@radix-ui/themes";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { SuggestionProps } from "@tiptap/suggestion";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";

import { EntityMentionList } from "./EntityMentionList";
import type { SuggestionListRef } from "./SuggestionListContainer";
import { SuggestionItem } from "./SuggestionUtils";

// `@tanstack/react-virtual` needs measurable scroll containers, which jsdom
// can't provide — pass items through directly.
vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: ({ count }: { count: number }): unknown => ({
    getVirtualItems: (): Array<{ index: number; start: number; size: number; key: number }> =>
      Array.from({ length: count }, (_, i) => ({ index: i, start: i * 28, size: 28, key: i })),
    getTotalSize: (): number => count * 28,
    scrollToIndex: (): void => {},
  }),
}));

type Row =
  | {
      id: string;
      label: string;
      entityType: "repository" | "workspace" | "agent";
      entityId: string;
      entityDisplayName: string;
      subtitle: string;
      parentId?: string;
    }
  | { id: string; label: string; isSectionHeader: true; isFirstInList?: boolean }
  | {
      id: string;
      label: string;
      isTypeRow: true;
      entityType: "repository" | "workspace" | "agent";
      description: string;
    };

const makeEntity = (
  entityType: "repository" | "workspace" | "agent",
  entityId: string,
  entityDisplayName: string,
  subtitle = "",
  parentId?: string,
): Row => ({
  ...new SuggestionItem(entityId, entityDisplayName),
  entityType,
  entityId,
  entityDisplayName,
  subtitle,
  parentId,
});

const makeHeader = (label: string, isFirstInList = false): Row => ({
  ...new SuggestionItem(`__section-${label}`, label),
  isSectionHeader: true,
  isFirstInList,
});

const makeTypeRow = (entityType: "repository" | "workspace" | "agent", label: string, description: string): Row => ({
  ...new SuggestionItem(`__type-${entityType}`, label),
  isTypeRow: true,
  entityType,
  description,
});

// Mock a TipTap editor chain just enough for the drill-in flow: every call
// returns the same `chain` object (so `.focus().deleteRange(...).insertContentAt(...).run()`
// resolves without throwing) and `.run()` ends the chain.
const makeMockEditor = (): { editor: unknown; chainRuns: Array<unknown> } => {
  const chainRuns: Array<unknown> = [];
  const chain = {
    focus: (): unknown => chain,
    deleteRange: (): unknown => chain,
    insertContentAt: (): unknown => chain,
    run: (): void => {
      chainRuns.push({});
    },
  };
  const editor = { chain: (): unknown => chain };
  return { editor, chainRuns };
};

const makeProps = (
  items: Array<Row>,
  query = "",
): { props: SuggestionProps; command: ReturnType<typeof vi.fn>; chainRuns: Array<unknown> } => {
  const command = vi.fn();
  const { editor, chainRuns } = makeMockEditor();
  const props = {
    items,
    command,
    query,
    editor,
    range: { from: 0, to: 1 },
    clientRect: null,
    decorationNode: null,
  } as unknown as SuggestionProps;
  return { props, command, chainRuns };
};

const pressKey = (ref: React.RefObject<SuggestionListRef>, key: string, shiftKey = false): void => {
  act(() => {
    const event = { key, shiftKey } as unknown as KeyboardEvent;
    ref.current!.onKeyDown({ event });
  });
};

const renderList = (
  rows: Array<Row>,
  query = "",
): {
  command: ReturnType<typeof vi.fn>;
  ref: React.RefObject<SuggestionListRef>;
  chainRuns: Array<unknown>;
} => {
  const { props, command, chainRuns } = makeProps(rows, query);
  const ref = createRef<SuggestionListRef>();
  const Wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={createStore()}>
      <Theme>{children}</Theme>
    </Provider>
  );
  render(
    <Wrapper>
      <EntityMentionList ref={ref} {...props} />
    </Wrapper>,
  );
  return { command, ref, chainRuns };
};

afterEach(() => {
  cleanup();
});

describe("EntityMentionList — structure", () => {
  it("carries ENTITY_MENTION_LIST test id on its outer wrapper", () => {
    renderList([makeHeader("REPOSITORIES", true), makeEntity("repository", "r1", "Core")]);
    expect(screen.getByTestId(ElementIds.ENTITY_MENTION_LIST)).toBeTruthy();
  });

  it("also exposes the shared MENTION_LIST test id via the inner container", () => {
    // Both ids resolve for Playwright queries — one per wrapper layer.
    renderList([makeHeader("REPOSITORIES", true), makeEntity("repository", "r1", "Core")]);
    expect(screen.getByTestId(ElementIds.MENTION_LIST)).toBeTruthy();
  });

  it("renders section-header rows as non-selectable labels", () => {
    renderList([
      makeHeader("REPOSITORIES", true),
      makeEntity("repository", "r1", "Core"),
      makeHeader("WORKSPACES"),
      makeEntity("workspace", "w1", "Main"),
    ]);
    // Headers render via renderItem — their labels appear but they carry
    // no ENTITY_MENTION_ITEM test id.
    expect(screen.getByText("REPOSITORIES")).toBeTruthy();
    expect(screen.getByText("WORKSPACES")).toBeTruthy();
    const items = screen.getAllByTestId(ElementIds.ENTITY_MENTION_ITEM);
    expect(items).toHaveLength(2);
  });

  it("shows 'No results' when the list is empty", () => {
    renderList([]);
    expect(screen.getByText("No results")).toBeTruthy();
  });
});

describe("EntityMentionList — keyboard navigation", () => {
  it("Enter commits the first selectable item (skipping the leading header)", () => {
    const { command, ref } = renderList([
      makeHeader("REPOSITORIES", true),
      makeEntity("repository", "r1", "Core"),
      makeEntity("repository", "r2", "Other"),
    ]);
    pressKey(ref, "Enter");
    expect(command).toHaveBeenCalledTimes(1);
    expect(command).toHaveBeenCalledWith(
      expect.objectContaining({
        entityId: "r1",
        entityType: "repository",
      }),
    );
  });

  it("ArrowDown jumps across a section header", () => {
    const { command, ref } = renderList([
      makeHeader("REPOSITORIES", true),
      makeEntity("repository", "r1", "Core"),
      makeHeader("WORKSPACES"),
      makeEntity("workspace", "w1", "Main"),
    ]);
    // From the first selectable (r1), ArrowDown should land on w1 (skipping
    // the "Workspaces" header), and Enter commits w1.
    pressKey(ref, "ArrowDown");
    pressKey(ref, "Enter");
    expect(command).toHaveBeenCalledWith(
      expect.objectContaining({
        entityId: "w1",
        entityType: "workspace",
      }),
    );
  });

  it("Enter does nothing when the list is empty", () => {
    const { command, ref } = renderList([]);
    pressKey(ref, "Enter");
    expect(command).not.toHaveBeenCalled();
  });
});

describe("EntityMentionList — mouse interaction", () => {
  it("clicking an entity row commits it with the correct payload", () => {
    const { command } = renderList([
      makeHeader("REPOSITORIES", true),
      makeEntity("repository", "r1", "Core"),
      makeEntity("repository", "r2", "Other"),
    ]);
    const items = screen.getAllByTestId(ElementIds.ENTITY_MENTION_ITEM);
    fireEvent.click(items[1]);
    expect(command).toHaveBeenCalledWith(
      expect.objectContaining({
        entityId: "r2",
        entityDisplayName: "Other",
      }),
    );
  });
});

describe("EntityMentionList — query highlighting", () => {
  it("wraps the matching substring in the display name with a highlight span", () => {
    renderList([makeHeader("REPOSITORIES", true), makeEntity("repository", "r1", "Sculptor")], "sculp");
    const highlights = document.querySelectorAll("strong");
    expect(highlights.length).toBeGreaterThanOrEqual(1);
    expect(Array.from(highlights).some((el) => el.textContent === "Sculp")).toBe(true);
  });
});

describe("EntityMentionList — type picker drill-in", () => {
  // Production picker only emits two type rows now — agents are reached by
  // drilling into a workspace row, not via a top-level "Agents" type row.
  const topLevelRows = (): Array<Row> => [
    makeTypeRow("repository", "Repositories", "Git projects connected to Sculptor"),
    makeTypeRow("workspace", "Workspaces", "Task workspaces — drill in for their agents"),
    makeHeader("WORKSPACES"),
    makeEntity("workspace", "w1", "Main", "", "p1"),
    makeEntity("workspace", "w2", "Feature branch", "", "p1"),
    makeHeader("AGENTS"),
    makeEntity("agent", "a1", "Agent Alpha", "", "w1"),
    makeEntity("agent", "a2", "Agent Beta", "", "w2"),
  ];

  it("renders the type rows at the top with their descriptions", () => {
    renderList(topLevelRows());
    expect(screen.getByText("Repositories")).toBeTruthy();
    expect(screen.getByText("Workspaces")).toBeTruthy();
    // No "Agents" type row exists in the new design — agents are reached by
    // drilling into a workspace.
    expect(screen.queryByText("Running or completed coding agents")).toBeNull();
    expect(screen.getByText("Task workspaces — drill in for their agents")).toBeTruthy();
  });

  it("pressing Enter on a highlighted type row narrows to that type and hides other rows", () => {
    // Selection starts on the first selectable row (the "Repositories" type
    // row). ArrowDown moves to the "Workspaces" type row.
    const { ref, command } = renderList(topLevelRows());
    pressKey(ref, "ArrowDown"); // repository → workspace type row
    pressKey(ref, "Enter");

    // The suggestion-config command MUST NOT be invoked — drill-in is
    // handled locally by the List.
    expect(command).not.toHaveBeenCalled();

    // Workspace entities are visible; agent entities are filtered out.
    expect(screen.getByText("Main")).toBeTruthy();
    expect(screen.queryByText("Agent Alpha")).toBeNull();
    // Type rows themselves are gone too.
    expect(screen.queryByText("Repositories")).toBeNull();
  });

  it("pressing Tab on a type row also drills in (alias for Enter)", () => {
    const { ref, command } = renderList(topLevelRows());
    // First selectable is the "Repositories" type row.
    pressKey(ref, "Tab");
    expect(command).not.toHaveBeenCalled();
    // Repositories section would be empty (no repo entities in the fixture),
    // so the "No results" state replaces the list.
    expect(screen.getByText("No results")).toBeTruthy();
  });

  it("clicking a type row drills in", () => {
    const { command } = renderList(topLevelRows());
    // Type rows share the ENTITY_MENTION_ITEM test id with entity rows.
    // The second item (index 1) is the Workspaces type row.
    const items = screen.getAllByTestId(ElementIds.ENTITY_MENTION_ITEM);
    fireEvent.click(items[1]);

    expect(command).not.toHaveBeenCalled();
    expect(screen.getByText("Main")).toBeTruthy();
    expect(screen.queryByText("Agent Alpha")).toBeNull();
  });

  it("Shift+Tab pops back to the top picker from a narrowed view", () => {
    const { ref } = renderList(topLevelRows());
    pressKey(ref, "ArrowDown"); // → Workspaces type row
    pressKey(ref, "Enter"); // narrow to workspaces

    // Confirm narrowed state — agent row hidden under type drill.
    expect(screen.queryByText("Agent Alpha")).toBeNull();

    // Pop back.
    pressKey(ref, "Tab", /* shiftKey */ true);

    // Top-level rows are visible again.
    expect(screen.getByText("Workspaces")).toBeTruthy();
    expect(screen.getByText("Agent Alpha")).toBeTruthy();
  });

  it("after narrowing, Enter on an entity row commits that entity", () => {
    const { ref, command } = renderList(topLevelRows());
    pressKey(ref, "ArrowDown"); // → Workspaces type row
    pressKey(ref, "Enter"); // narrow to workspaces

    // Now the first selectable row is the first workspace (w1). Enter
    // should commit it through the suggestion-config command.
    pressKey(ref, "Enter");
    expect(command).toHaveBeenCalledTimes(1);
    expect(command).toHaveBeenCalledWith(
      expect.objectContaining({
        entityId: "w1",
        entityType: "workspace",
      }),
    );
  });
});

describe("EntityMentionList — workspace drill-in", () => {
  // Same fixture shape as the type-picker tests so we can hand-walk the
  // selection from the top-level rows down into a single workspace's
  // agents.
  const topLevelRows = (): Array<Row> => [
    makeTypeRow("repository", "Repositories", "Git projects connected to Sculptor"),
    makeTypeRow("workspace", "Workspaces", "Task workspaces — drill in for their agents"),
    makeHeader("WORKSPACES"),
    makeEntity("workspace", "w1", "Main", "", "p1"),
    makeEntity("workspace", "w2", "Feature branch", "", "p1"),
    makeHeader("AGENTS"),
    makeEntity("agent", "a1", "Agent Alpha", "", "w1"),
    makeEntity("agent", "a2", "Agent Beta", "", "w2"),
  ];

  it("Tab on a workspace row drills into that workspace and shows only its agents", () => {
    const { ref, command } = renderList(topLevelRows());
    // ArrowDown past the two type rows + WORKSPACES header lands us on w1.
    // Selectable indices skip the section header; ArrowDown twice gets us
    // from "Repositories" type-row → "Workspaces" type-row → first
    // workspace entity.
    pressKey(ref, "ArrowDown"); // workspace type row
    pressKey(ref, "ArrowDown"); // first workspace entity (w1)
    pressKey(ref, "Tab");

    // No commit fired — drill-in is handled locally.
    expect(command).not.toHaveBeenCalled();

    // Only w1's agent is visible. w2's agent and the workspace rows are gone.
    expect(screen.getByText("Agent Alpha")).toBeTruthy();
    expect(screen.queryByText("Agent Beta")).toBeNull();
    expect(screen.queryByText("Main")).toBeNull();
  });

  it("Enter on a workspace row commits the workspace (does not drill in)", () => {
    const { ref, command } = renderList(topLevelRows());
    pressKey(ref, "ArrowDown"); // workspace type row
    pressKey(ref, "ArrowDown"); // first workspace entity (w1)
    pressKey(ref, "Enter");

    expect(command).toHaveBeenCalledTimes(1);
    expect(command).toHaveBeenCalledWith(
      expect.objectContaining({
        entityId: "w1",
        entityType: "workspace",
      }),
    );
  });

  it("clicking a workspace row drills into it (mouse parity with Tab — SCU-1296)", () => {
    const { command } = renderList(topLevelRows());
    // Workspace rows: index in ENTITY_MENTION_ITEM is types(2) + workspace(0,1).
    const items = screen.getAllByTestId(ElementIds.ENTITY_MENTION_ITEM);
    // [0] = repo type, [1] = workspace type, [2] = w1, [3] = w2, [4] = a1, [5] = a2.
    fireEvent.click(items[2]);

    // No commit fired — clicking a workspace drills in, handled locally, the
    // same as Tab. A click on a workspace row used to commit it (the bug);
    // now it opens the workspace's agents.
    expect(command).not.toHaveBeenCalled();

    // Only w1's agent is visible; w2's agent and the workspace rows are gone.
    expect(screen.getByText("Agent Alpha")).toBeTruthy();
    expect(screen.queryByText("Agent Beta")).toBeNull();
    expect(screen.queryByText("Main")).toBeNull();
  });

  it("inside a drilled workspace, Enter on an agent commits it", () => {
    const { ref, command } = renderList(topLevelRows());
    pressKey(ref, "ArrowDown"); // workspace type row
    pressKey(ref, "ArrowDown"); // w1
    pressKey(ref, "Tab"); // drill into w1

    pressKey(ref, "Enter");
    expect(command).toHaveBeenCalledTimes(1);
    expect(command).toHaveBeenCalledWith(
      expect.objectContaining({
        entityId: "a1",
        entityType: "agent",
      }),
    );
  });

  it("Shift+Tab from inside a drilled workspace pops back to the top picker", () => {
    const { ref } = renderList(topLevelRows());
    pressKey(ref, "ArrowDown"); // workspace type row
    pressKey(ref, "ArrowDown"); // w1
    pressKey(ref, "Tab"); // drill into w1

    expect(screen.queryByText("Main")).toBeNull();

    pressKey(ref, "Tab", /* shiftKey */ true);

    // Top-level rows are visible again.
    expect(screen.getByText("Main")).toBeTruthy();
    expect(screen.getByText("Workspaces")).toBeTruthy();
  });
});
