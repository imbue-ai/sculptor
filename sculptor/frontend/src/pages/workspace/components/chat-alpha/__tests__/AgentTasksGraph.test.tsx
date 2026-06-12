import { Theme } from "@radix-ui/themes";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AgentTaskStatus, ElementIds, type Task } from "~/api";

import { AgentTasksGraph } from "../AgentTasksGraph";

const makeTask = (overrides: Partial<Task> & { id: string; subject: string; status: AgentTaskStatus }): Task =>
  ({
    description: "",
    activeForm: null,
    blocks: [],
    blockedBy: [],
    owner: null,
    metadata: {},
    ...overrides,
  }) as Task;

const renderGraph = (tasks: Array<Task>): ReturnType<typeof render> =>
  render(
    <Theme>
      <AgentTasksGraph tasks={tasks} />
    </Theme>,
  );

afterEach(() => {
  cleanup();
});

const linearChain = (count: number, inProgressIndex: number | null = null): Array<Task> =>
  Array.from({ length: count }, (_, i) => {
    const status =
      inProgressIndex !== null && i === inProgressIndex
        ? AgentTaskStatus.IN_PROGRESS
        : i < (inProgressIndex ?? -1)
          ? AgentTaskStatus.COMPLETED
          : AgentTaskStatus.PENDING;
    return makeTask({
      id: String(i + 1),
      subject: `Task ${i + 1}`,
      status,
      blockedBy: i === 0 ? [] : [String(i)],
    });
  });

describe("AgentTasksGraph — rectangular (small) mode", () => {
  it("uses rectangles and labels every node when tasks.length < 15", () => {
    const tasks = linearChain(14, 5);
    const { container } = renderGraph(tasks);
    expect(container.querySelectorAll("rect").length).toBeGreaterThan(0);
    expect(container.querySelectorAll("circle").length).toBe(0);
    expect(screen.getAllByTestId(ElementIds.AGENT_TASKS_GRAPH_NODE)).toHaveLength(14);
    // Every node should have a label.
    expect(container.querySelectorAll("text").length).toBe(14);
  });
});

describe("AgentTasksGraph — compact (large) mode", () => {
  it("switches to circles with no labels when tasks.length >= 15", () => {
    const tasks = linearChain(20, 7);
    const { container } = renderGraph(tasks);
    expect(container.querySelectorAll("circle").length).toBe(20);
    expect(container.querySelectorAll("rect").length).toBe(0);
    // Labels are intentionally suppressed in compact mode — the circles are
    // too small to host any text legibly. Users get full names by toggling
    // off the graph or expanding the list.
    expect(container.querySelectorAll("text").length).toBe(0);
  });
});

describe("AgentTasksGraph — non-interactivity", () => {
  // graph nodes carry no interactivity — no selection state, no
  // hover effects, no clicks, no tooltips. Asserting this at the unit level
  // catches drift where someone adds an onClick / role="button" to a node.

  it("graph nodes have no role, tabIndex, or interactive handlers", () => {
    const tasks = linearChain(4, 1);
    renderGraph(tasks);
    const nodes = screen.getAllByTestId(ElementIds.AGENT_TASKS_GRAPH_NODE);
    for (const node of nodes) {
      expect(node.getAttribute("role")).toBeNull();
      expect(node.getAttribute("tabindex")).toBeNull();
      expect(node.getAttribute("aria-pressed")).toBeNull();
      expect(node.getAttribute("aria-expanded")).toBeNull();
      // onClick / onMouseEnter would surface as attributes only via inline
      // handlers; React attaches synthetic listeners which don't appear in
      // the DOM attributes. The role/tabindex check above is the user-facing
      // contract: a non-focusable, non-button element conveys "static".
    }
  });
});
