import { beforeEach, describe, expect, it, vi } from "vitest";

import { CommandRegistry } from "../registry.ts";
import type { Command, PaletteContext } from "../types.ts";

const ROOT_CTX: PaletteContext = {
  route: { isHome: true, isWorkspace: false, isSettings: false, isAddWorkspace: false, isAgent: false },
  activeWorkspaceId: null,
  activeAgentId: null,
  hasChatPanel: false,
  hasTerminalPanel: false,
  isSectionMaximized: false,
  page: null,
};

const SETTINGS_PAGE_CTX: PaletteContext = { ...ROOT_CTX, page: "settings.section" };

const baseCommand = (overrides: Partial<Command>): Command => ({
  id: "test.cmd",
  title: "Test command",
  group: "navigation",
  perform: vi.fn(),
  ...overrides,
});

describe("CommandRegistry", () => {
  let registry: CommandRegistry;
  beforeEach(() => {
    registry = new CommandRegistry();
  });

  it("registers and lists commands", () => {
    registry.register(baseCommand({ id: "a", title: "A" }));
    registry.register(baseCommand({ id: "b", title: "B" }));
    const ids = registry.list(ROOT_CTX).map((c) => c.id);
    expect(ids).toEqual(expect.arrayContaining(["a", "b"]));
  });

  it("returns an unregister function from register()", () => {
    const unregister = registry.register(baseCommand({ id: "a" }));
    expect(registry.size()).toBe(1);
    unregister();
    expect(registry.size()).toBe(0);
  });

  it("registerMany returns a single unregister for the whole batch", () => {
    const unregister = registry.registerMany([baseCommand({ id: "a" }), baseCommand({ id: "b" })]);
    expect(registry.size()).toBe(2);
    unregister();
    expect(registry.size()).toBe(0);
  });

  it("filters out commands whose `when` returns false", () => {
    registry.register(baseCommand({ id: "always" }));
    registry.register(baseCommand({ id: "ws_only", when: (ctx) => ctx.route.isWorkspace }));
    const ids = registry.list(ROOT_CTX).map((c) => c.id);
    expect(ids).toContain("always");
    expect(ids).not.toContain("ws_only");
  });

  it("logs once when `when` throws and continues to filter the command", () => {
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    registry.register(
      baseCommand({
        id: "boom",
        when: () => {
          throw new Error("boom");
        },
      }),
    );
    expect(registry.list(ROOT_CTX).map((c) => c.id)).not.toContain("boom");
    expect(registry.list(ROOT_CTX).map((c) => c.id)).not.toContain("boom"); // second call: still excluded
    expect(errSpy).toHaveBeenCalledTimes(1);
    errSpy.mockRestore();
  });

  it("filters by onPage", () => {
    registry.register(baseCommand({ id: "root_only" }));
    registry.register(baseCommand({ id: "settings_only", onPage: "settings.section" }));
    const rootIds = registry.list(ROOT_CTX).map((c) => c.id);
    expect(rootIds).toContain("root_only");
    expect(rootIds).not.toContain("settings_only");
    const pageIds = registry.list(SETTINGS_PAGE_CTX).map((c) => c.id);
    expect(pageIds).toContain("settings_only");
    expect(pageIds).not.toContain("root_only");
  });

  it("includeAllPages reveals page-scoped commands at the root", () => {
    registry.register(baseCommand({ id: "root_only" }));
    registry.register(baseCommand({ id: "settings_only", onPage: "settings.section" }));
    const ids = registry.list(ROOT_CTX, { includeAllPages: true }).map((c) => c.id);
    expect(ids).toContain("root_only");
    expect(ids).toContain("settings_only");
  });

  it("includeAllPages does NOT leak workspaces.switch contents", () => {
    // Regression-lock: per the design, fuzzy search at root must NOT
    // surface every open workspace. The user has to enter the workspace
    // switcher sub-menu first.
    registry.register(baseCommand({ id: "ws_entry", onPage: "workspaces.switch" }));
    registry.register(baseCommand({ id: "settings_entry", onPage: "settings.section" }));
    const ids = registry.list(ROOT_CTX, { includeAllPages: true }).map((c) => c.id);
    expect(ids).toContain("settings_entry");
    expect(ids).not.toContain("ws_entry");
  });

  it("includeAllPages does NOT leak agents.switch contents", () => {
    // Regression-lock: agents do not flood the root either. They live
    // exclusively under the agent switcher sub-menu.
    registry.register(baseCommand({ id: "agent_entry", onPage: "agents.switch" }));
    registry.register(baseCommand({ id: "settings_entry", onPage: "settings.section" }));
    const ids = registry.list(ROOT_CTX, { includeAllPages: true }).map((c) => c.id);
    expect(ids).toContain("settings_entry");
    expect(ids).not.toContain("agent_entry");
  });

  it("includeAllPages has no effect when not at root", () => {
    registry.register(baseCommand({ id: "settings_only", onPage: "settings.section" }));
    registry.register(baseCommand({ id: "theme_only", onPage: "theme.appearance" }));
    const ids = registry.list(SETTINGS_PAGE_CTX, { includeAllPages: true }).map((c) => c.id);
    expect(ids).toContain("settings_only");
    expect(ids).not.toContain("theme_only");
  });

  it("supports onPage as an array of PageIds (multi-page commands)", () => {
    registry.register(
      baseCommand({
        id: "multi",
        onPage: ["settings.section", "theme.appearance"],
      }),
    );

    // Visible on each declared page.
    expect(registry.list(SETTINGS_PAGE_CTX).map((c) => c.id)).toContain("multi");
    const themeCtx: PaletteContext = { ...ROOT_CTX, page: "theme.appearance" };
    expect(registry.list(themeCtx).map((c) => c.id)).toContain("multi");

    // Not visible at the root (it's page-scoped).
    expect(registry.list(ROOT_CTX).map((c) => c.id)).not.toContain("multi");

    // Revealed at the root with includeAllPages, since none of its
    // declared pages set hideFromRootSearch.
    const revealed = registry.list(ROOT_CTX, { includeAllPages: true }).map((c) => c.id);
    expect(revealed).toContain("multi");
    // Yielded exactly once even though it has multiple onPage entries.
    expect(revealed.filter((id) => id === "multi")).toHaveLength(1);
  });

  it("dynamic providers contribute commands", () => {
    registry.registerProvider({
      id: "p",
      produce: () => [baseCommand({ id: "dyn", title: "Dyn" })],
    });
    expect(registry.list(ROOT_CTX).map((c) => c.id)).toContain("dyn");
  });

  it("dynamic provider errors are logged but do not break listing", () => {
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    registry.registerProvider({
      id: "bad",
      produce: () => {
        throw new Error("kaboom");
      },
    });
    registry.register(baseCommand({ id: "still_here" }));
    expect(registry.list(ROOT_CTX).map((c) => c.id)).toContain("still_here");
    expect(errSpy).toHaveBeenCalled();
    errSpy.mockRestore();
  });

  it("byId looks up a registered command", () => {
    registry.register(baseCommand({ id: "x" }));
    expect(registry.byId("x")?.id).toBe("x");
    expect(registry.byId("nope")).toBeUndefined();
  });

  it("notifies subscribers on changes", () => {
    const listener = vi.fn();
    const unsubscribe = registry.subscribe(listener);
    registry.register(baseCommand({ id: "a" }));
    expect(listener).toHaveBeenCalledTimes(1);
    registry.register(baseCommand({ id: "b" }));
    expect(listener).toHaveBeenCalledTimes(2);
    unsubscribe();
    registry.register(baseCommand({ id: "c" }));
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it("dynamic provider commands override static commands with the same id", () => {
    registry.register(baseCommand({ id: "dup", title: "Static" }));
    registry.registerProvider({
      id: "p",
      produce: () => [baseCommand({ id: "dup", title: "Dynamic" })],
    });
    const dup = registry.list(ROOT_CTX).find((c) => c.id === "dup");
    expect(dup?.title).toBe("Dynamic");
  });

  it("warns once when two commands claim the same shortcut id", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    registry.register(baseCommand({ id: "a", shortcut: "next_tab" }));
    registry.register(baseCommand({ id: "b", shortcut: "next_tab" }));
    registry.list(ROOT_CTX);
    // Second list call should NOT re-warn for the same shortcut.
    registry.list(ROOT_CTX);
    const collisionWarns = warnSpy.mock.calls.filter((args) => String(args[0]).includes("shortcut"));
    expect(collisionWarns.length).toBe(1);
    expect(String(collisionWarns[0]?.[0])).toContain("next_tab");
    warnSpy.mockRestore();
  });

  it("does not warn when the same command id appears in static + dynamic with one shortcut", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    registry.register(baseCommand({ id: "x", shortcut: "next_tab" }));
    registry.registerProvider({
      id: "p",
      produce: () => [baseCommand({ id: "x", shortcut: "next_tab" })],
    });
    registry.list(ROOT_CTX);
    const collisionWarns = warnSpy.mock.calls.filter((args) => String(args[0]).includes("shortcut "));
    expect(collisionWarns).toHaveLength(0);
    warnSpy.mockRestore();
  });
});
