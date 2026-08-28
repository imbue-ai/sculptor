import { Theme } from "@radix-ui/themes";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { AgentTaskStatus, ElementIds, type Task } from "~/api";

import { AgentTasksPanel } from "../AgentTasksPanel";

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

const renderPanel = (tasks: Array<Task> | null): ReturnType<typeof render> =>
  render(
    <Theme>
      <AgentTasksPanel tasks={tasks} />
    </Theme>,
  );

beforeAll(() => {
  // jsdom doesn't implement scrollIntoView; AgentTasksPanel calls it on mount.
  Element.prototype.scrollIntoView = (): void => {};
});

afterEach(() => {
  cleanup();
});

describe("AgentTasksPanel — waiting badge summary", () => {
  it("shows the full list of #ids when blockedBy.length <= MAX_INLINE_BLOCKED_BY", () => {
    const tasks = [
      makeTask({ id: "1", subject: "A", status: AgentTaskStatus.COMPLETED }),
      makeTask({ id: "2", subject: "B", status: AgentTaskStatus.COMPLETED }),
      makeTask({ id: "3", subject: "C", status: AgentTaskStatus.IN_PROGRESS, blockedBy: ["1", "2"] }),
    ];
    renderPanel(tasks);
    const badges = screen.getAllByTestId(ElementIds.AGENT_TASKS_WAITING_BADGE);
    expect(badges).toHaveLength(1);
    expect(badges[0].textContent).toContain("Waiting on #1, #2");
    expect(badges[0].textContent).not.toContain("more");
  });

  it("collapses to '+K more' when blockedBy.length > MAX_INLINE_BLOCKED_BY", () => {
    const tasks = [
      makeTask({ id: "1", subject: "A", status: AgentTaskStatus.COMPLETED }),
      makeTask({ id: "2", subject: "B", status: AgentTaskStatus.COMPLETED }),
      makeTask({ id: "3", subject: "C", status: AgentTaskStatus.COMPLETED }),
      makeTask({ id: "4", subject: "D", status: AgentTaskStatus.IN_PROGRESS, blockedBy: ["1", "2", "3"] }),
    ];
    renderPanel(tasks);
    const badges = screen.getAllByTestId(ElementIds.AGENT_TASKS_WAITING_BADGE);
    expect(badges).toHaveLength(1);
    expect(badges[0].textContent).toContain("Waiting on #1, #2, +1 more");
  });

  it("renders 'Waiting on #1' for a single predecessor", () => {
    const tasks = [
      makeTask({ id: "1", subject: "A", status: AgentTaskStatus.COMPLETED }),
      makeTask({ id: "2", subject: "B", status: AgentTaskStatus.IN_PROGRESS, blockedBy: ["1"] }),
    ];
    renderPanel(tasks);
    const badges = screen.getAllByTestId(ElementIds.AGENT_TASKS_WAITING_BADGE);
    expect(badges[0].textContent).toContain("Waiting on #1");
  });
});

describe("AgentTasksPanel — fade-by-tier", () => {
  it("fades pending tasks that sit downstream of the live tier", () => {
    const tasks = [
      makeTask({ id: "1", subject: "A", status: AgentTaskStatus.IN_PROGRESS }),
      makeTask({ id: "2", subject: "B", status: AgentTaskStatus.PENDING, blockedBy: ["1"] }),
      makeTask({ id: "3", subject: "C", status: AgentTaskStatus.PENDING, blockedBy: ["2"] }),
    ];
    renderPanel(tasks);
    const rows = screen.getAllByTestId(ElementIds.AGENT_TASKS_ROW);
    const wrappers = rows.map((row) => row.parentElement as HTMLElement);
    // Live tier is task 1 (tier 0); task 2 sits at tier 1, task 3 at tier 2.
    expect(wrappers[0].style.opacity).toBe("");
    expect(wrappers[1].style.opacity).toBe("1");
    expect(parseFloat(wrappers[2].style.opacity)).toBeCloseTo(0.85, 2);
  });

  it("does not fade when no task is in_progress", () => {
    const tasks = [
      makeTask({ id: "1", subject: "A", status: AgentTaskStatus.PENDING }),
      makeTask({ id: "2", subject: "B", status: AgentTaskStatus.PENDING, blockedBy: ["1"] }),
    ];
    renderPanel(tasks);
    const wrappers = screen.getAllByTestId(ElementIds.AGENT_TASKS_ROW).map((row) => row.parentElement as HTMLElement);
    expect(wrappers[0].style.opacity).toBe("");
    expect(wrappers[1].style.opacity).toBe("");
  });

  it("does not fade completed tasks", () => {
    const tasks = [
      makeTask({ id: "1", subject: "A", status: AgentTaskStatus.IN_PROGRESS }),
      makeTask({ id: "2", subject: "B", status: AgentTaskStatus.COMPLETED, blockedBy: ["1"] }),
    ];
    renderPanel(tasks);
    const wrappers = screen.getAllByTestId(ElementIds.AGENT_TASKS_ROW).map((row) => row.parentElement as HTMLElement);
    expect(wrappers[1].style.opacity).toBe("");
  });
});
