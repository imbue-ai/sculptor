import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CodingAgentTaskView, Project, Workspace } from "~/api";
import { ElementIds } from "~/api";
import { projectAtomFamily } from "~/common/state/atoms/projects.ts";
import { taskAtomFamily } from "~/common/state/atoms/tasks.ts";
import { workspaceAtomFamily } from "~/common/state/atoms/workspaces.ts";
import { diffPanelOpenAtom, diffPanelStateAtomFamily } from "~/pages/workspace/components/diffPanel/atoms.ts";
import { FILE_VIEW_PREFIX } from "~/pages/workspace/components/diffPanel/types.ts";
import { fileBrowserStateAtomFamily, focusFolderAtom } from "~/pages/workspace/panels/fileBrowser/atoms.ts";

import { MentionChip, type MentionChipProps } from "./MentionChip.tsx";

// Spy on useImbueNavigate so the entity-chip tests can assert on the calls
// the chip makes without depending on URL introspection. `vi.hoisted` moves
// the spy declarations above vi.mock's hoisted factory so the factory can
// close over the same mock-fn instances the tests inspect.
const { navigateToWorkspaceSpy, navigateToAgentSpy } = vi.hoisted(() => ({
  navigateToWorkspaceSpy: vi.fn(),
  navigateToAgentSpy: vi.fn(),
}));
vi.mock("~/common/NavigateUtils", () => ({
  useImbueNavigate: (): {
    navigateToWorkspace: (id: string) => void;
    navigateToAgent: (wsId: string, agentId: string) => void;
  } => ({
    navigateToWorkspace: navigateToWorkspaceSpy,
    navigateToAgent: navigateToAgentSpy,
  }),
  useWorkspacePageParams: (): { workspaceID: string } => ({ workspaceID: "ws-123" }),
}));

type Store = ReturnType<typeof createStore>;

const WORKSPACE_ID = "ws-123";

type RenderOptions = {
  workspaceID?: string | null;
  store?: Store;
};

const renderChip = (props: MentionChipProps, options: RenderOptions = {}): { store: Store; container: HTMLElement } => {
  const store = options.store ?? createStore();
  const workspaceID = options.workspaceID === undefined ? WORKSPACE_ID : options.workspaceID;

  const Wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>
      <Theme>{children}</Theme>
    </Provider>
  );

  // When workspaceID is null, render under a route with no :workspaceID param.
  const initialEntry = workspaceID === null ? "/no-workspace" : `/workspaces/${workspaceID}`;
  const routePath = workspaceID === null ? "/no-workspace" : "/workspaces/:workspaceID";

  const { container } = render(
    <Wrapper>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path={routePath} element={<MentionChip {...props} />} />
        </Routes>
      </MemoryRouter>
    </Wrapper>,
  );

  return { store, container };
};

const getChip = (): HTMLElement => screen.getByTestId(ElementIds.MENTION_SPAN);

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

beforeEach(() => {
  // atomWithStorage persists to localStorage across tests; clear to isolate.
  localStorage.clear();
});

describe("MentionChip", () => {
  describe("file mention", () => {
    it("renders with a pointer-cursor clickable class", () => {
      renderChip({ id: "@src/utils.ts" });
      const chip = getChip();
      expect(chip.className).toMatch(/clickableMention/);
    });

    it("clicking opens a file view tab via openFileViewTabAtom", () => {
      const { store } = renderChip({ id: "@src/utils.ts" });
      fireEvent.click(getChip());

      const state = store.get(diffPanelStateAtomFamily(WORKSPACE_ID));
      expect(state.openTabs).toHaveLength(1);
      const tab = state.openTabs[0];
      expect(tab.kind).toBe("file-view");
      // File view tabs use FILE_VIEW_PREFIX + realPath as their identity key.
      expect(tab.filePath).toBe(`${FILE_VIEW_PREFIX}src/utils.ts`);
      if (tab.kind === "file-view") {
        expect(tab.realPath).toBe("src/utils.ts");
      }
      expect(state.activeTabPath).toBe(`${FILE_VIEW_PREFIX}src/utils.ts`);
      expect(store.get(diffPanelOpenAtom)).toBe(true);
    });

    it("click does not trigger folder reveal", () => {
      const { store } = renderChip({ id: "@src/utils.ts" });
      fireEvent.click(getChip());
      expect(store.get(focusFolderAtom)).toBeNull();
    });

    // HoverCard in this app suppresses the first hover-open until a real
    // `mousemove` is observed on `document` (see HoverCard.tsx:
    // `hasUserMovedSinceMountRef`). jsdom does not synthesize mousemove from
    // userEvent.hover, so the content is not rendered in tests. We skip the
    // user-facing hover assertion and instead rely on MentionChip's structure
    // being covered by the other tests.
    it.skip("hover-card content includes 'Click to open'", () => {
      // Intentionally skipped — see comment above.
    });

    it("renders the basename by default (no displayLabel override)", () => {
      renderChip({ id: "@sculptor/sculptor-plugin/skills/create-html-mock" });
      expect(getChip().textContent).toBe("create-html-mock");
    });

    it("renders the displayLabel override when provided (used to disambiguate sibling chips)", () => {
      renderChip({
        id: "@sculptor/sculptor-plugin/skills/create-html-mock",
        displayLabel: "sculptor-plugin/.../create-html-mock",
      });
      expect(getChip().textContent).toBe("sculptor-plugin/.../create-html-mock");
    });

    it("ignores a null displayLabel and falls back to the basename", () => {
      renderChip({ id: "@src/utils.ts", displayLabel: null });
      expect(getChip().textContent).toBe("utils.ts");
    });
  });

  describe("folder mention", () => {
    it("renders with the clickable class", () => {
      renderChip({ id: "@src/components/" });
      const chip = getChip();
      expect(chip.className).toMatch(/clickableMention/);
    });

    it("clicking fires revealFolderAtom and populates focusFolderAtom", () => {
      const { store } = renderChip({ id: "@src/components/" });
      const before = Date.now();
      fireEvent.click(getChip());
      const after = Date.now();

      const focus = store.get(focusFolderAtom);
      expect(focus).not.toBeNull();
      if (focus) {
        expect(focus.workspaceId).toBe(WORKSPACE_ID);
        // Trailing slash stripped by revealFolderAtom.
        expect(focus.path).toBe("src/components");
        expect(typeof focus.nonce).toBe("number");
        expect(focus.nonce).toBeGreaterThanOrEqual(before);
        expect(focus.nonce).toBeLessThanOrEqual(after);
      }
    });

    it("clicking expands ancestor folders", () => {
      const { store } = renderChip({ id: "@src/components/" });
      fireEvent.click(getChip());

      const browserState = store.get(fileBrowserStateAtomFamily(WORKSPACE_ID));
      // Ancestors of "src/components" are ["src", "src/components"].
      expect(browserState.expandedFolders).toEqual(expect.arrayContaining(["src", "src/components"]));
    });

    it("click does not open a file tab", () => {
      const { store } = renderChip({ id: "@src/components/" });
      fireEvent.click(getChip());

      const state = store.get(diffPanelStateAtomFamily(WORKSPACE_ID));
      expect(state.openTabs).toEqual([]);
      expect(state.activeTabPath).toBeNull();
    });
  });

  describe("skill mention", () => {
    it("renders the raw id text", () => {
      renderChip({ id: "/batch" });
      const chip = getChip();
      expect(chip.textContent).toBe("/batch");
    });

    it("clicking does not fire any atom", () => {
      const { store } = renderChip({ id: "/batch" });
      fireEvent.click(getChip());

      expect(store.get(focusFolderAtom)).toBeNull();
      const state = store.get(diffPanelStateAtomFamily(WORKSPACE_ID));
      expect(state.openTabs).toEqual([]);
    });
  });

  describe("outside workspace (no workspaceID param)", () => {
    it("file chip click is a no-op", () => {
      const { store } = renderChip({ id: "@src/utils.ts" }, { workspaceID: null });
      fireEvent.click(getChip());

      // No workspaceID means handleClick returns before set-atom calls.
      // The diff panel state for any plausible workspace id should remain
      // at the default (empty). Check both the id we used elsewhere and an
      // empty-string id as a sanity check that nothing leaked.
      const stateForWs = store.get(diffPanelStateAtomFamily(WORKSPACE_ID));
      expect(stateForWs.openTabs).toEqual([]);
      const stateEmpty = store.get(diffPanelStateAtomFamily(""));
      expect(stateEmpty.openTabs).toEqual([]);
    });

    it("folder chip click is a no-op", () => {
      const { store } = renderChip({ id: "@src/components/" }, { workspaceID: null });
      fireEvent.click(getChip());

      expect(store.get(focusFolderAtom)).toBeNull();
    });
  });

  describe("event propagation", () => {
    const renderChipInParent = (props: MentionChipProps, onParentClick: () => void): { store: Store } => {
      const store = createStore();
      render(
        <Provider store={store}>
          <Theme>
            <MemoryRouter initialEntries={[`/workspaces/${WORKSPACE_ID}`]}>
              <Routes>
                <Route
                  path="/workspaces/:workspaceID"
                  element={
                    <div data-testid="parent" onClick={onParentClick}>
                      <MentionChip {...props} />
                    </div>
                  }
                />
              </Routes>
            </MemoryRouter>
          </Theme>
        </Provider>,
      );
      return { store };
    };

    it("click on file chip stops propagation", () => {
      const parentSpy = vi.fn();
      renderChipInParent({ id: "@src/utils.ts" }, parentSpy);
      fireEvent.click(getChip());
      expect(parentSpy).not.toHaveBeenCalled();
    });

    it("click on folder chip stops propagation", () => {
      const parentSpy = vi.fn();
      renderChipInParent({ id: "@src/components/" }, parentSpy);
      fireEvent.click(getChip());
      expect(parentSpy).not.toHaveBeenCalled();
    });

    it("click on a workspace entity chip stops propagation", () => {
      const parentSpy = vi.fn();
      const store = createStore();
      store.set(workspaceAtomFamily("ws-abc"), {
        objectId: "ws-abc",
        projectId: "proj-1",
        organizationReference: "org",
        description: "WS",
        createdAt: "2024-01-01T00:00:00Z",
        isDeleted: false,
        isOpen: true,
      } as unknown as Workspace);
      render(
        <Provider store={store}>
          <Theme>
            <MemoryRouter initialEntries={[`/workspaces/${WORKSPACE_ID}`]}>
              <Routes>
                <Route
                  path="/workspaces/:workspaceID"
                  element={
                    <div data-testid="parent" onClick={parentSpy}>
                      <MentionChip kind="entity" entityType="workspace" entityId="ws-abc" entityDisplayName="WS" />
                    </div>
                  }
                />
              </Routes>
            </MemoryRouter>
          </Theme>
        </Provider>,
      );
      fireEvent.click(screen.getByTestId(ElementIds.ENTITY_MENTION_CHIP));
      expect(parentSpy).not.toHaveBeenCalled();
    });
  });
});

// ---------------------------------------------------------------------------
// Entity mention — the third MentionChip variant.
// ---------------------------------------------------------------------------

const makeTask = (overrides: Partial<CodingAgentTaskView>): CodingAgentTaskView =>
  ({
    id: "task-1",
    projectId: "proj-1",
    createdAt: "2024-01-01T00:00:00Z",
    updatedAt: "2024-01-01T00:00:00Z",
    taskStatus: "RUNNING",
    isAutoCompacting: false,
    artifactNames: [],
    initialPrompt: "Test prompt",
    titleOrSomethingLikeIt: "Test task",
    interface: "API",
    systemPrompt: null,
    model: "CLAUDE_4_SONNET",
    isSmoothStreamingSupported: true,
    isArchived: false,
    isDeleted: false,
    title: "Task",
    status: "RUNNING",
    goal: "Goal",
    workspaceId: "ws-1",
    ...overrides,
  }) as CodingAgentTaskView;

const makeWorkspace = (overrides: Partial<Workspace>): Workspace =>
  ({
    objectId: "ws-1",
    projectId: "proj-1",
    organizationReference: "org",
    description: "WS",
    createdAt: "2024-01-01T00:00:00Z",
    isDeleted: false,
    isOpen: true,
    ...overrides,
  }) as unknown as Workspace;

const makeProject = (overrides: Partial<Project>): Project =>
  ({
    objectId: "proj-1",
    organizationReference: "org",
    name: "Proj",
    userGitRepoUrl: "git@example.com:o/r.git",
    ...overrides,
  }) as unknown as Project;

const renderEntityChip = (
  props: Extract<MentionChipProps, { kind: "entity" }>,
  options: { store?: Store } = {},
): { store: Store; container: HTMLElement } => {
  const store = options.store ?? createStore();
  const { container } = render(
    <Provider store={store}>
      <Theme>
        <MemoryRouter initialEntries={[`/workspaces/${WORKSPACE_ID}`]}>
          <Routes>
            <Route path="/workspaces/:workspaceID" element={<MentionChip {...props} />} />
          </Routes>
        </MemoryRouter>
      </Theme>
    </Provider>,
  );
  return { store, container };
};

const getEntityChip = (): HTMLElement => screen.getByTestId(ElementIds.ENTITY_MENTION_CHIP);

describe("MentionChip — entity mention", () => {
  beforeEach(() => {
    navigateToWorkspaceSpy.mockClear();
    navigateToAgentSpy.mockClear();
  });

  describe("repository", () => {
    it("renders with the ENTITY_MENTION_CHIP test id and data-entity-type", () => {
      const store = createStore();
      store.set(projectAtomFamily("proj-1"), makeProject({}));
      renderEntityChip(
        { kind: "entity", entityType: "repository", entityId: "proj-1", entityDisplayName: "Core" },
        { store },
      );
      const chip = getEntityChip();
      expect(chip.getAttribute("data-entity-type")).toBe("repository");
      // Repository chips are explicitly not clickable even when the entity
      // resolves; the chip must use the static `.mention` class, not
      // `.clickableMention`.
      expect(chip.className).not.toMatch(/clickable/);
      expect(chip.textContent).toContain("Core");
    });

    it("click fires no navigation atom", () => {
      const store = createStore();
      store.set(projectAtomFamily("proj-1"), makeProject({}));
      renderEntityChip(
        { kind: "entity", entityType: "repository", entityId: "proj-1", entityDisplayName: "Core" },
        { store },
      );
      fireEvent.click(getEntityChip());
      expect(navigateToWorkspaceSpy).not.toHaveBeenCalled();
      expect(navigateToAgentSpy).not.toHaveBeenCalled();
    });

    it("renders the deleted class when the project atom is null", () => {
      const store = createStore();
      // Project atom defaults to null with no seeding.
      renderEntityChip(
        { kind: "entity", entityType: "repository", entityId: "missing", entityDisplayName: "Gone" },
        { store },
      );
      expect(getEntityChip().className).toMatch(/deleted/);
    });
  });

  describe("workspace", () => {
    it("renders with workspace data attribute and clickable styling", () => {
      const store = createStore();
      store.set(workspaceAtomFamily("ws-1"), makeWorkspace({}));
      renderEntityChip(
        { kind: "entity", entityType: "workspace", entityId: "ws-1", entityDisplayName: "WS" },
        { store },
      );
      const chip = getEntityChip();
      expect(chip.getAttribute("data-entity-type")).toBe("workspace");
      // Workspace chips navigate on click — assert the clickable variant of
      // the shared mention palette is in play.
      expect(chip.className).toMatch(/clickable/);
    });

    it("click calls navigateToWorkspace with the entity id", () => {
      const store = createStore();
      store.set(workspaceAtomFamily("ws-1"), makeWorkspace({}));
      renderEntityChip(
        { kind: "entity", entityType: "workspace", entityId: "ws-1", entityDisplayName: "WS" },
        { store },
      );
      fireEvent.click(getEntityChip());
      expect(navigateToWorkspaceSpy).toHaveBeenCalledWith("ws-1");
      expect(navigateToAgentSpy).not.toHaveBeenCalled();
    });

    it("click is a no-op when the workspace is deleted", () => {
      const store = createStore();
      // No seeding — workspaceAtomFamily("ws-missing") returns null.
      renderEntityChip(
        { kind: "entity", entityType: "workspace", entityId: "ws-missing", entityDisplayName: "WS" },
        { store },
      );
      const chip = getEntityChip();
      expect(chip.className).toMatch(/deleted/);
      fireEvent.click(chip);
      expect(navigateToWorkspaceSpy).not.toHaveBeenCalled();
    });
  });

  describe("agent", () => {
    it("renders with agent data attribute and clickable styling when the task resolves", () => {
      const store = createStore();
      store.set(taskAtomFamily("task-1"), makeTask({}));
      renderEntityChip(
        { kind: "entity", entityType: "agent", entityId: "task-1", entityDisplayName: "Task" },
        { store },
      );
      const chip = getEntityChip();
      expect(chip.getAttribute("data-entity-type")).toBe("agent");
      expect(chip.className).toMatch(/clickable/);
    });

    it("click calls navigateToAgent with the task's workspaceId and entity id", () => {
      const store = createStore();
      store.set(taskAtomFamily("task-1"), makeTask({ workspaceId: "ws-parent" }));
      renderEntityChip(
        { kind: "entity", entityType: "agent", entityId: "task-1", entityDisplayName: "Task" },
        { store },
      );
      fireEvent.click(getEntityChip());
      expect(navigateToAgentSpy).toHaveBeenCalledWith("ws-parent", "task-1");
      expect(navigateToWorkspaceSpy).not.toHaveBeenCalled();
    });

    it("click is a no-op when the task has no workspaceId", () => {
      const store = createStore();
      store.set(taskAtomFamily("task-1"), makeTask({ workspaceId: null }));
      renderEntityChip(
        { kind: "entity", entityType: "agent", entityId: "task-1", entityDisplayName: "Task" },
        { store },
      );
      fireEvent.click(getEntityChip());
      expect(navigateToAgentSpy).not.toHaveBeenCalled();
    });

    it("click is a no-op when the agent is deleted", () => {
      const store = createStore();
      renderEntityChip(
        { kind: "entity", entityType: "agent", entityId: "missing", entityDisplayName: "Task" },
        { store },
      );
      const chip = getEntityChip();
      expect(chip.className).toMatch(/deleted/);
      fireEvent.click(chip);
      expect(navigateToAgentSpy).not.toHaveBeenCalled();
    });
  });

  it("strikes through the display name when the entity is deleted", () => {
    const store = createStore();
    const { container } = renderEntityChip(
      { kind: "entity", entityType: "workspace", entityId: "missing", entityDisplayName: "Ghost" },
      { store },
    );
    const display = container.querySelector(".strikethrough");
    expect(display).not.toBeNull();
    expect(display?.textContent).toBe("Ghost");
  });
});
