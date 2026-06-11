/**
 * Unit tests for ``useHomeToggle``.
 *
 * The hook gates "toggle off /home" on whether there is at least one
 * *visible* tab to land on. Invisible pseudo-tabs (``__home__`` and stale
 * ``__new_workspace_<draftId>__``) must NOT count, because they have no
 * TabDefinition in WorkspaceTabs and the user can't see them — counting
 * them would let a stale localStorage entry slip past the safety check
 * and silently navigate the user to a defunct ``lastNonHomeLocation``.
 *
 * These tests pin the predicate down across all the tab-id shapes the
 * codebase produces, plus the obvious golden-path cases.
 */

import { renderHook } from "@testing-library/react";
import type { WritableAtom } from "jotai";
import { Provider } from "jotai";
import { useHydrateAtoms } from "jotai/utils";
import type { ReactNode } from "react";
import { act } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// ── Mocks ───────────────────────────────────────────────────────────────

// vi.hoisted runs alongside vi.mock factories, before regular module
// initialization. Putting the spies + the mutable route flag here lets the
// mock factories below close over real ``vi.fn`` instances without TDZ.
const { mockNavigate, mockNavigateToHome, routeState } = vi.hoisted(() => ({
  mockNavigate: vi.fn<(path: string) => void>(),
  mockNavigateToHome: vi.fn<() => void>(),
  routeState: { isHomeRoute: false },
}));

// Replace the derived ``effectiveOpenTabIdsAtom`` (read-only) with a
// writable primitive atom for tests. The hook only reads from it, so
// the substitution is transparent — and it lets us hydrate concrete
// tab-id arrays per case without standing up the upstream
// workspace-state machinery.
vi.mock("../atoms/workspaces", async () => {
  const actual = await vi.importActual<object>("../atoms/workspaces");
  const { atom: jotaiAtom } = await import("jotai");
  return {
    ...actual,
    effectiveOpenTabIdsAtom: jotaiAtom<ReadonlyArray<string>>([]),
    lastNonHomeLocationAtom: jotaiAtom<string | null>(null),
  };
});

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<object>("react-router-dom");
  return { ...actual, useNavigate: (): typeof mockNavigate => mockNavigate };
});

vi.mock("~/common/NavigateUtils.ts", () => ({
  useImbueNavigate: (): Record<string, unknown> => ({
    navigateToHome: mockNavigateToHome,
    navigateToAgent: vi.fn(),
    navigateToWorkspace: vi.fn(),
    navigateToSetup: vi.fn(),
    navigateToGlobalSettings: vi.fn(),
    navigateToComponentGallery: vi.fn(),
    navigateToRoot: vi.fn(),
  }),
  useImbueLocation: (): Record<string, unknown> => ({
    isHomeRoute: routeState.isHomeRoute,
    isAgentRoute: false,
    isWorkspaceRoute: false,
    isSettingsRoute: false,
    isComponentGalleryRoute: false,
  }),
}));

import { effectiveOpenTabIdsAtom, lastNonHomeLocationAtom, newWorkspaceTabId } from "../atoms/workspaces";
import { useHomeToggle } from "./useHomeToggle";

// ── Wrapper ─────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/array-type
type AnyWritableAtom = WritableAtom<unknown, any[], any>;
type AtomInitialValues = Array<readonly [AnyWritableAtom, unknown]>;

const HydrateAtoms = ({
  initialValues,
  children,
}: {
  initialValues: AtomInitialValues;
  children: ReactNode;
}): ReactNode => {
  useHydrateAtoms(initialValues);
  return children;
};

const renderToggle = (
  options: {
    onHome?: boolean;
    tabIds?: ReadonlyArray<string>;
    lastNonHome?: string | null;
  } = {},
): { toggle: () => void; isToggleNoOp: boolean } => {
  routeState.isHomeRoute = options.onHome ?? false;

  const initialValues: AtomInitialValues = [
    [effectiveOpenTabIdsAtom as unknown as AnyWritableAtom, options.tabIds ?? []],
    [lastNonHomeLocationAtom as unknown as AnyWritableAtom, options.lastNonHome ?? null],
  ];

  const { result } = renderHook(() => useHomeToggle(), {
    wrapper: ({ children }: { children: ReactNode }): ReactNode => (
      <Provider>
        <HydrateAtoms initialValues={initialValues}>{children}</HydrateAtoms>
      </Provider>
    ),
  });

  return { toggle: result.current.toggleHome, isToggleNoOp: result.current.isToggleNoOp };
};

// ── Tests ───────────────────────────────────────────────────────────────

describe("useHomeToggle", () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    mockNavigateToHome.mockClear();
    routeState.isHomeRoute = false;
  });

  describe("from a non-home route", () => {
    it("navigates to /home regardless of tabs or lastNonHomeLocation", () => {
      const { toggle } = renderToggle({
        onHome: false,
        tabIds: [],
        lastNonHome: null,
      });

      act(() => toggle());

      expect(mockNavigateToHome).toHaveBeenCalledTimes(1);
      expect(mockNavigate).not.toHaveBeenCalled();
    });

    it("navigates to /home even when invisible pseudo-tabs are present", () => {
      const { toggle } = renderToggle({
        onHome: false,
        tabIds: ["__home__", newWorkspaceTabId("draft-xyz")],
        lastNonHome: "/ws/ws-1",
      });

      act(() => toggle());

      expect(mockNavigateToHome).toHaveBeenCalledTimes(1);
      expect(mockNavigate).not.toHaveBeenCalled();
    });
  });

  describe("from /home — safety guard (no visible tab → no-op)", () => {
    it("is a no-op when tabOrder is empty", () => {
      const { toggle } = renderToggle({
        onHome: true,
        tabIds: [],
        lastNonHome: "/ws/ws-1",
      });

      act(() => toggle());

      expect(mockNavigate).not.toHaveBeenCalled();
      expect(mockNavigateToHome).not.toHaveBeenCalled();
    });

    it("is a no-op when only the __home__ pseudo-tab is in tabOrder (the bug fix)", () => {
      // This is the exact case that motivated the safety-check fix:
      // a stale ``__home__`` carried over from an older session sits in
      // tabOrderAtom (persisted in localStorage) but has no
      // TabDefinition, so the user perceives "no tabs". Toggling Home
      // must NOT navigate them off /home.
      const { toggle } = renderToggle({
        onHome: true,
        tabIds: ["__home__"],
        lastNonHome: "/ws/ws-stale",
      });

      act(() => toggle());

      expect(mockNavigate).not.toHaveBeenCalled();
      expect(mockNavigateToHome).not.toHaveBeenCalled();
    });

    it("is a no-op when only a stale __new_workspace_<draftId>__ pseudo-tab is in tabOrder", () => {
      // The other invisible-tab variety: a stale draft pseudo-tab
      // left over from a pre-modal session. Same reasoning as above.
      const { toggle } = renderToggle({
        onHome: true,
        tabIds: [newWorkspaceTabId("draft-abc-123")],
        lastNonHome: "/ws/ws-stale",
      });

      act(() => toggle());

      expect(mockNavigate).not.toHaveBeenCalled();
      expect(mockNavigateToHome).not.toHaveBeenCalled();
    });

    it("is a no-op when tabOrder contains only invisible pseudo-tabs in any combination", () => {
      const { toggle } = renderToggle({
        onHome: true,
        tabIds: ["__home__", newWorkspaceTabId("d1"), newWorkspaceTabId("d2")],
        lastNonHome: "/ws/ws-stale",
      });

      act(() => toggle());

      expect(mockNavigate).not.toHaveBeenCalled();
      expect(mockNavigateToHome).not.toHaveBeenCalled();
    });

    it("is a no-op when there ARE visible tabs but lastNonHomeLocation is null", () => {
      // Fresh session: user hasn't been anywhere yet, so even with
      // workspace tabs available we have no remembered destination.
      const { toggle } = renderToggle({
        onHome: true,
        tabIds: ["ws-1"],
        lastNonHome: null,
      });

      act(() => toggle());

      expect(mockNavigate).not.toHaveBeenCalled();
      expect(mockNavigateToHome).not.toHaveBeenCalled();
    });
  });

  describe("from /home — toggle-off path (visible tab present → navigate)", () => {
    it("navigates to lastNonHomeLocation when a real workspace tab is open", () => {
      const { toggle } = renderToggle({
        onHome: true,
        tabIds: ["ws-1"],
        lastNonHome: "/ws/ws-1",
      });

      act(() => toggle());

      expect(mockNavigate).toHaveBeenCalledExactlyOnceWith("/ws/ws-1");
      expect(mockNavigateToHome).not.toHaveBeenCalled();
    });

    it("counts __settings__ as a visible tab (Settings has a TabDefinition)", () => {
      const { toggle } = renderToggle({
        onHome: true,
        tabIds: ["__settings__"],
        lastNonHome: "/settings",
      });

      act(() => toggle());

      expect(mockNavigate).toHaveBeenCalledExactlyOnceWith("/settings");
    });

    it("counts __component_gallery__ as a visible tab", () => {
      const { toggle } = renderToggle({
        onHome: true,
        tabIds: ["__component_gallery__"],
        lastNonHome: "/component-gallery",
      });

      act(() => toggle());

      expect(mockNavigate).toHaveBeenCalledExactlyOnceWith("/component-gallery");
    });

    it("ignores invisible pseudo-tabs when at least one visible tab is also present", () => {
      // Mixed state: stale __home__ alongside a real workspace.
      // The visible workspace gates the toggle through.
      const { toggle } = renderToggle({
        onHome: true,
        tabIds: ["__home__", "ws-1", newWorkspaceTabId("stale-draft")],
        lastNonHome: "/ws/ws-1/agent/agent-1",
      });

      act(() => toggle());

      expect(mockNavigate).toHaveBeenCalledExactlyOnceWith("/ws/ws-1/agent/agent-1");
    });
  });

  describe("isToggleNoOp (drives the Home button's aria-disabled)", () => {
    it("is false off /home (the toggle always navigates home there)", () => {
      expect(renderToggle({ onHome: false, tabIds: [], lastNonHome: null }).isToggleNoOp).toBe(false);
    });

    it("is true on /home with no visible tab", () => {
      expect(renderToggle({ onHome: true, tabIds: ["__home__"], lastNonHome: "/ws/ws-1" }).isToggleNoOp).toBe(true);
    });

    it("is true on /home with a visible tab but no remembered location", () => {
      expect(renderToggle({ onHome: true, tabIds: ["ws-1"], lastNonHome: null }).isToggleNoOp).toBe(true);
    });

    it("is false on /home when there's a visible tab and a remembered location", () => {
      expect(renderToggle({ onHome: true, tabIds: ["ws-1"], lastNonHome: "/ws/ws-1" }).isToggleNoOp).toBe(false);
    });
  });
});
