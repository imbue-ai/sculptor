// Subscription-hygiene tests for useVisibleCommands: the palette host stays
// mounted for the whole session, so while the palette is CLOSED it must not
// re-render on task/layout churn — and on open it must still build the list
// (including dynamic-provider rows) from current state.

import { act, cleanup } from "@testing-library/react";
import { createStore } from "jotai";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CodingAgentTaskView } from "~/api";
import { taskAtomFamily, taskIdsAtom, tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { renderWithProviders } from "~/common/utils/renderWithProviders.tsx";
import { activeWorkspaceIdAtom, workspaceLayoutAtom } from "~/pages/workspace/layout/atoms/section.ts";
import { EMPTY_WORKSPACE_LAYOUT } from "~/pages/workspace/layout/persistence/snapshot.ts";

import { commandPaletteOpenAtom } from "../atoms/commandPalette.ts";
import { usePaletteContext, useVisibleCommands } from "../hooks/useCommandPalette.ts";
import { CommandRegistryProvider } from "../registryContext.tsx";
import type { Command } from "../types/commandPalette.ts";
import { CommandRegistry } from "../utils/registry.ts";

const taskFor = (id: string, workspaceId: string, overrides: Partial<CodingAgentTaskView> = {}): CodingAgentTaskView =>
  ({ id, workspaceId, isDeleted: false, ...overrides }) as CodingAgentTaskView;

// A vi.fn() recorder keeps the component body free of outer-variable
// reassignment (react-hooks compiler rule): render count = call count,
// latest hook result = last call's argument.
const recordRender = vi.fn<(commands: ReadonlyArray<Command>) => void>();
const hostRenderCount = (): number => recordRender.mock.calls.length;
const latestCommands = (): ReadonlyArray<Command> => recordRender.mock.lastCall?.[0] ?? [];

const Host = (): ReactElement => {
  const ctx = usePaletteContext();
  recordRender(useVisibleCommands(ctx));
  return <div />;
};

type Store = ReturnType<typeof createStore>;

const renderHost = (store: Store, registry: CommandRegistry): void => {
  renderWithProviders(
    <CommandRegistryProvider value={registry}>
      <Host />
    </CommandRegistryProvider>,
    { store, initialEntries: ["/home"] },
  );
};

// A provider that mirrors the production pattern: `produce` reads the store
// imperatively, so the list content depends on the subscriptions in
// useVisibleCommands to stay fresh.
const registryWithTaskProvider = (store: Store): CommandRegistry => {
  const registry = new CommandRegistry();
  registry.registerProvider({
    id: "test.tasks",
    produce: () =>
      (store.get(tasksArrayAtom) ?? []).map(
        (task) =>
          ({
            id: `test.task.${task.id}`,
            title: `Task ${task.id}`,
            group: "navigation",
            perform: (): void => {},
          }) as Command,
      ),
  });
  return registry;
};

describe("useVisibleCommands", () => {
  beforeEach(() => {
    localStorage.clear();
    recordRender.mockClear();
  });

  afterEach(() => {
    cleanup();
  });

  it("does not re-render the host on task or layout churn while the palette is closed", () => {
    const store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-test");
    renderHost(store, new CommandRegistry());
    const rendersAfterMount = hostRenderCount();

    act(() => {
      store.set(taskIdsAtom, ["t1"]);
      store.set(taskAtomFamily("t1"), taskFor("t1", "ws-test"));
    });
    act(() => {
      store.set(taskAtomFamily("t1"), taskFor("t1", "ws-test", { title: "tick" }));
    });
    act(() => {
      store.set(workspaceLayoutAtom, { ...EMPTY_WORKSPACE_LAYOUT });
    });

    expect(hostRenderCount()).toBe(rendersAfterMount);
  });

  it("builds the first-open list from state written while the palette was closed", () => {
    const store = createStore();
    const registry = registryWithTaskProvider(store);
    renderHost(store, registry);

    act(() => {
      store.set(taskIdsAtom, ["t1"]);
      store.set(taskAtomFamily("t1"), taskFor("t1", "ws-test"));
    });
    // Closed: the memo short-circuits, so nothing is listed yet.
    expect(latestCommands()).toEqual([]);

    act(() => {
      store.set(commandPaletteOpenAtom, true);
    });
    expect(latestCommands().map((cmd) => cmd.id)).toContain("test.task.t1");
  });

  it("recomputes the list when a provider input changes while the palette is open", () => {
    const store = createStore();
    store.set(commandPaletteOpenAtom, true);
    const registry = registryWithTaskProvider(store);
    renderHost(store, registry);
    expect(latestCommands()).toEqual([]);

    act(() => {
      store.set(taskIdsAtom, ["t1"]);
      store.set(taskAtomFamily("t1"), taskFor("t1", "ws-test"));
    });

    expect(latestCommands().map((cmd) => cmd.id)).toContain("test.task.t1");
  });
});
