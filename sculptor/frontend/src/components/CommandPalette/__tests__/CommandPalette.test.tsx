import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { createStore } from "jotai";
import { posthog } from "posthog-js";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";
import { renderWithProviders } from "~/common/testUtils.tsx";

import { commandPaletteOpenAtom, commandPalettePagesAtom, commandPalettePendingAtom } from "../atoms.ts";
import { CommandPalette } from "../CommandPalette.tsx";
import { commandRegistry } from "../registry.ts";
import type { Command } from "../types.ts";

// jsdom doesn't define `scrollIntoView`. cmdk calls it during keyboard
// navigation. We stub it on the prototype for the duration of each test
// and restore the original descriptor in `afterEach` so the global
// doesn't leak across files.
let originalScrollIntoViewDescriptor: PropertyDescriptor | undefined;
let hasInstalledScrollIntoViewStub = false;
const installScrollIntoViewStub = (): void => {
  originalScrollIntoViewDescriptor = Object.getOwnPropertyDescriptor(Element.prototype, "scrollIntoView");
  if (typeof (Element.prototype as unknown as { scrollIntoView?: unknown }).scrollIntoView !== "function") {
    Object.defineProperty(Element.prototype, "scrollIntoView", {
      value: () => {},
      writable: true,
      configurable: true,
    });
    hasInstalledScrollIntoViewStub = true;
  }
};

const restoreScrollIntoViewStub = (): void => {
  if (!hasInstalledScrollIntoViewStub) return;
  if (originalScrollIntoViewDescriptor) {
    Object.defineProperty(Element.prototype, "scrollIntoView", originalScrollIntoViewDescriptor);
  } else {
    delete (Element.prototype as unknown as { scrollIntoView?: unknown }).scrollIntoView;
  }
  hasInstalledScrollIntoViewStub = false;
  originalScrollIntoViewDescriptor = undefined;
};

const originalHash = window.location.hash;

afterEach(() => {
  cleanup();
  commandRegistry.reset();
  vi.restoreAllMocks();
  window.location.hash = originalHash;
  restoreScrollIntoViewStub();
});

const reg = (cmd: Partial<Command> & Pick<Command, "id" | "title" | "perform">): Command =>
  ({ group: "navigation", ...cmd }) as Command;

const setupOpenStore = (): ReturnType<typeof createStore> => {
  const store = createStore();
  store.set(commandPaletteOpenAtom, true);
  return store;
};

const renderPalette = (store: ReturnType<typeof createStore>): ReturnType<typeof renderWithProviders> => {
  return renderWithProviders(<CommandPalette />, { store, initialEntries: ["/home"] });
};

describe("CommandPalette", () => {
  beforeEach(() => {
    // jsdom does not supply hash routing; force a sane location for our hook.
    window.location.hash = "#/home";
    installScrollIntoViewStub();
  });

  it("renders nothing when closed", () => {
    const store = createStore();
    store.set(commandPaletteOpenAtom, false);
    renderPalette(store);
    expect(screen.queryByTestId(ElementIds.COMMAND_PALETTE)).toBeNull();
  });

  it("renders the empty-state element when the registry has no commands", () => {
    const store = setupOpenStore();
    renderPalette(store);
    expect(screen.getByTestId(ElementIds.COMMAND_PALETTE)).toBeTruthy();
    expect(screen.getByTestId(ElementIds.COMMAND_PALETTE_EMPTY).textContent).toContain("No commands");
  });

  it("renders registered commands and runs them on selection (auto-close)", async () => {
    const onPerform = vi.fn();
    commandRegistry.register(reg({ id: "test.run", title: "Run me", perform: onPerform }));
    const store = setupOpenStore();
    renderPalette(store);

    const item = document.querySelector('[data-command-id="test.run"]');
    expect(item).not.toBeNull();
    fireEvent.click(item!);
    expect(onPerform).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(store.get(commandPaletteOpenAtom)).toBe(false));
  });

  it("keepOpen commands stay open after run", () => {
    const onPerform = vi.fn();
    commandRegistry.register(reg({ id: "test.toggle", title: "Toggle me", perform: onPerform, keepOpen: true }));
    const store = setupOpenStore();
    renderPalette(store);
    const item = document.querySelector('[data-command-id="test.toggle"]');
    fireEvent.click(item!);
    expect(onPerform).toHaveBeenCalled();
    expect(store.get(commandPaletteOpenAtom)).toBe(true);
  });

  it("filters commands when a query is typed", () => {
    commandRegistry.registerMany([
      reg({ id: "a.alpha", title: "Alpha", perform: vi.fn() }),
      reg({ id: "b.beta", title: "Beta", perform: vi.fn() }),
    ]);
    const store = setupOpenStore();
    renderPalette(store);
    const input = screen.getByTestId(ElementIds.COMMAND_PALETTE_INPUT) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "alph" } });
    expect(document.querySelector('[data-command-id="a.alpha"]')).not.toBeNull();
    expect(document.querySelector('[data-command-id="b.beta"]')).toBeNull();
  });

  it("logs and continues when a command's perform throws synchronously", async () => {
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    commandRegistry.register(
      reg({
        id: "test.boom",
        title: "Boom",
        perform: () => {
          throw new Error("kaboom");
        },
      }),
    );
    const store = setupOpenStore();
    renderPalette(store);
    fireEvent.click(document.querySelector('[data-command-id="test.boom"]')!);
    await waitFor(() => expect(errSpy).toHaveBeenCalled());
    // Palette still auto-closes after a sync throw — the runner doesn't
    // distinguish error from success, just logs.
    await waitFor(() => expect(store.get(commandPaletteOpenAtom)).toBe(false));
    errSpy.mockRestore();
  });

  it("logs and continues when a command's perform returns a rejected promise", async () => {
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    commandRegistry.register(
      reg({
        id: "test.async_boom",
        title: "Async boom",
        perform: () => Promise.reject(new Error("async-kaboom")),
      }),
    );
    const store = setupOpenStore();
    renderPalette(store);
    fireEvent.click(document.querySelector('[data-command-id="test.async_boom"]')!);
    await waitFor(() => expect(errSpy).toHaveBeenCalled());
    await waitFor(() => expect(store.get(commandPaletteOpenAtom)).toBe(false));
    errSpy.mockRestore();
  });

  it("Cmd+Enter runs the auto-highlighted active command with keepOpen", async () => {
    const onPerform = vi.fn();
    commandRegistry.register(reg({ id: "test.cmd_enter", title: "Cmd-enter target", perform: onPerform }));
    const store = setupOpenStore();
    renderPalette(store);

    // The palette auto-highlights the first row on open, so Cmd+Enter
    // works without any priming arrow-key.
    const input = screen.getByTestId(ElementIds.COMMAND_PALETTE_INPUT);
    await waitFor(() => {
      expect(document.querySelector('[data-command-id="test.cmd_enter"][data-selected="true"]')).not.toBeNull();
    });
    fireEvent.keyDown(input, { key: "Enter", metaKey: true });
    expect(onPerform).toHaveBeenCalledTimes(1);
    // keepOpen via Cmd+Enter — palette remains open.
    expect(store.get(commandPaletteOpenAtom)).toBe(true);
  });

  it("Tab on a page-opener pushes its sub-page; Shift+Tab pops back", async () => {
    // Tab is repurposed: it walks INTO a sub-group rather than navigating
    // up/down the row list. Pressing Tab on a row that declares a
    // pageId (a page-opener) is equivalent to Enter on it — push the
    // sub-page. Shift+Tab from a sub-page pops back to the parent.
    // Tab on a row without a pageId is a no-op (and is swallowed so
    // Radix Dialog's focus trap doesn't shift focus out of the input).
    commandRegistry.register(
      reg({ id: "test.tab_opener", title: "Open Sub", perform: () => {}, pageId: "theme.appearance" }),
    );
    commandRegistry.register(
      reg({ id: "test.tab_in_sub", title: "Inside Sub", perform: () => {}, onPage: "theme.appearance" }),
    );
    const store = setupOpenStore();
    renderPalette(store);

    // First row (the page-opener) is auto-highlighted on open.
    await waitFor(() => {
      expect(document.querySelector('[data-command-id="test.tab_opener"][data-selected="true"]')).not.toBeNull();
    });

    // Tab → push the sub-page.
    const input = screen.getByTestId(ElementIds.COMMAND_PALETTE_INPUT);
    fireEvent.keyDown(input, { key: "Tab" });
    await waitFor(() => expect(store.get(commandPalettePagesAtom)).toEqual(["theme.appearance"]));

    // Shift+Tab from the sub-page → pop back to root.
    fireEvent.keyDown(input, { key: "Tab", shiftKey: true });
    await waitFor(() => expect(store.get(commandPalettePagesAtom)).toEqual([]));
  });

  it("Tab on a non-page-opener row is a no-op (and is swallowed so focus stays on input)", async () => {
    commandRegistry.register(reg({ id: "test.tab_plain", title: "Plain row", perform: () => {} }));
    const store = setupOpenStore();
    renderPalette(store);

    await waitFor(() => {
      expect(document.querySelector('[data-command-id="test.tab_plain"][data-selected="true"]')).not.toBeNull();
    });
    const input = screen.getByTestId(ElementIds.COMMAND_PALETTE_INPUT);
    fireEvent.keyDown(input, { key: "Tab" });
    // No sub-page pushed; selection unchanged.
    expect(store.get(commandPalettePagesAtom)).toEqual([]);
    expect(document.querySelector('[data-command-id="test.tab_plain"][data-selected="true"]')).not.toBeNull();
  });

  it("Shift+Tab at root with no current sub-page is a no-op", async () => {
    commandRegistry.register(reg({ id: "test.shift_tab_root", title: "Plain", perform: () => {} }));
    const store = setupOpenStore();
    renderPalette(store);
    const input = screen.getByTestId(ElementIds.COMMAND_PALETTE_INPUT);
    fireEvent.keyDown(input, { key: "Tab", shiftKey: true });
    expect(store.get(commandPalettePagesAtom)).toEqual([]);
    expect(store.get(commandPaletteOpenAtom)).toBe(true);
  });

  it("Backspace on empty input pops a sub-page", async () => {
    // Drive this via the realistic flow: open palette → click a
    // page-opener → see breadcrumb → press Backspace → breadcrumb gone.
    commandRegistry.register(
      reg({ id: "test.opener", title: "Open Sub", perform: () => {}, pageId: "theme.appearance" }),
    );
    commandRegistry.register(
      reg({ id: "test.in_sub", title: "In Sub", perform: () => {}, onPage: "theme.appearance" }),
    );
    const store = setupOpenStore();
    renderPalette(store);

    fireEvent.click(document.querySelector('[data-command-id="test.opener"]')!);
    await waitFor(() => {
      expect(screen.queryByTestId(ElementIds.COMMAND_PALETTE_PAGE_BREADCRUMB)).not.toBeNull();
    });
    expect(store.get(commandPalettePagesAtom)).toEqual(["theme.appearance"]);

    const input = screen.getByTestId(ElementIds.COMMAND_PALETTE_INPUT);
    fireEvent.keyDown(input, { key: "Backspace" });
    await waitFor(() => expect(store.get(commandPalettePagesAtom)).toEqual([]));
  });

  it("ArrowRight on a page-opener pushes its sub-page; ArrowLeft pops back", async () => {
    // Mirrors Tab/Shift+Tab. Useful because the chevron-right glyph on
    // page-opener rows visually invites Right Arrow; Left then takes you
    // back. Caret is at the end of empty input on open, so the
    // caret-at-edge guard is satisfied trivially.
    commandRegistry.register(
      reg({ id: "test.arrow_opener", title: "Open Sub", perform: () => {}, pageId: "theme.appearance" }),
    );
    commandRegistry.register(
      reg({ id: "test.arrow_in_sub", title: "Inside Sub", perform: () => {}, onPage: "theme.appearance" }),
    );
    const store = setupOpenStore();
    renderPalette(store);

    await waitFor(() => {
      expect(document.querySelector('[data-command-id="test.arrow_opener"][data-selected="true"]')).not.toBeNull();
    });

    const input = screen.getByTestId(ElementIds.COMMAND_PALETTE_INPUT);
    fireEvent.keyDown(input, { key: "ArrowRight" });
    await waitFor(() => expect(store.get(commandPalettePagesAtom)).toEqual(["theme.appearance"]));

    fireEvent.keyDown(input, { key: "ArrowLeft" });
    await waitFor(() => expect(store.get(commandPalettePagesAtom)).toEqual([]));
  });

  it("ArrowRight on a row without a pageId is a no-op", async () => {
    commandRegistry.register(reg({ id: "test.arrow_plain", title: "Plain row", perform: () => {} }));
    const store = setupOpenStore();
    renderPalette(store);

    await waitFor(() => {
      expect(document.querySelector('[data-command-id="test.arrow_plain"][data-selected="true"]')).not.toBeNull();
    });
    const input = screen.getByTestId(ElementIds.COMMAND_PALETTE_INPUT);
    fireEvent.keyDown(input, { key: "ArrowRight" });
    expect(store.get(commandPalettePagesAtom)).toEqual([]);
  });

  it("ArrowLeft at root with no current sub-page is a no-op", async () => {
    commandRegistry.register(reg({ id: "test.arrow_left_root", title: "Plain", perform: () => {} }));
    const store = setupOpenStore();
    renderPalette(store);
    const input = screen.getByTestId(ElementIds.COMMAND_PALETTE_INPUT);
    fireEvent.keyDown(input, { key: "ArrowLeft" });
    expect(store.get(commandPalettePagesAtom)).toEqual([]);
    expect(store.get(commandPaletteOpenAtom)).toBe(true);
  });

  it("ArrowRight does NOT push a sub-page when the caret is mid-text (text-cursor wins)", async () => {
    // If the user is moving through typed text, Right Arrow is text
    // navigation, not sub-page navigation. Only when the caret is at the
    // end of the input do we hijack it.
    commandRegistry.register(
      reg({ id: "test.arrow_midtext", title: "Open Sub", perform: () => {}, pageId: "theme.appearance" }),
    );
    commandRegistry.register(
      reg({ id: "test.arrow_midtext_in_sub", title: "Inside", perform: () => {}, onPage: "theme.appearance" }),
    );
    const store = setupOpenStore();
    renderPalette(store);

    const input = screen.getByTestId(ElementIds.COMMAND_PALETTE_INPUT) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "Op" } });
    await waitFor(() => expect(input.value).toBe("Op"));
    // Caret in the middle of "Op" (between 'O' and 'p').
    input.setSelectionRange(1, 1);

    await waitFor(() => {
      expect(document.querySelector('[data-command-id="test.arrow_midtext"][data-selected="true"]')).not.toBeNull();
    });

    fireEvent.keyDown(input, { key: "ArrowRight" });
    // Sub-page NOT pushed — the input keeps the keystroke for caret movement.
    expect(store.get(commandPalettePagesAtom)).toEqual([]);
  });

  it("Shift+ArrowLeft is NOT hijacked (selection-extend still works inside the input)", async () => {
    commandRegistry.register(
      reg({ id: "test.arrow_shift_opener", title: "Open Sub", perform: () => {}, pageId: "theme.appearance" }),
    );
    commandRegistry.register(
      reg({ id: "test.arrow_shift_in_sub", title: "Inside", perform: () => {}, onPage: "theme.appearance" }),
    );
    const store = setupOpenStore();
    renderPalette(store);
    fireEvent.click(document.querySelector('[data-command-id="test.arrow_shift_opener"]')!);
    await waitFor(() => expect(store.get(commandPalettePagesAtom)).toEqual(["theme.appearance"]));

    const input = screen.getByTestId(ElementIds.COMMAND_PALETTE_INPUT);
    fireEvent.keyDown(input, { key: "ArrowLeft", shiftKey: true });
    // With a modifier, this is a text-edit gesture — sub-page must NOT pop.
    expect(store.get(commandPalettePagesAtom)).toEqual(["theme.appearance"]);
  });

  it("selecting a page-opener pushes a sub-page and does NOT close the palette", () => {
    const performSpy = vi.fn();
    commandRegistry.register(
      reg({
        id: "settings.open",
        title: "Open Settings",
        perform: performSpy,
        pageId: "settings.section",
      }),
    );
    commandRegistry.register(
      reg({
        id: "settings.page.general",
        title: "General",
        perform: vi.fn(),
        onPage: "settings.section",
      }),
    );
    const store = setupOpenStore();
    renderPalette(store);

    fireEvent.click(document.querySelector('[data-command-id="settings.open"]')!);
    expect(store.get(commandPaletteOpenAtom)).toBe(true);
    expect(store.get(commandPalettePagesAtom)).toEqual(["settings.section"]);
    // page-opener commands have their perform invoked once for telemetry —
    // current contract calls perform.
    expect(performSpy).toHaveBeenCalledTimes(1);
    // The page-scoped row should now be visible.
    expect(document.querySelector('[data-command-id="settings.page.general"]')).not.toBeNull();
  });

  it("re-renders when the registry mutates while the palette is open", async () => {
    const store = setupOpenStore();
    renderPalette(store);
    expect(document.querySelector('[data-command-id="test.late"]')).toBeNull();
    commandRegistry.register(reg({ id: "test.late", title: "Late arrival", perform: vi.fn() }));
    await waitFor(() => {
      expect(document.querySelector('[data-command-id="test.late"]')).not.toBeNull();
    });
  });

  it("hides page-scoped commands at root with empty query", () => {
    commandRegistry.registerMany([
      reg({ id: "root.cmd", title: "Root cmd", perform: vi.fn() }),
      reg({
        id: "page.scoped",
        title: "Page scoped",
        perform: vi.fn(),
        onPage: "settings.section",
      }),
    ]);
    const store = setupOpenStore();
    renderPalette(store);
    expect(document.querySelector('[data-command-id="root.cmd"]')).not.toBeNull();
    expect(document.querySelector('[data-command-id="page.scoped"]')).toBeNull();
  });

  it("reveals page-scoped commands at root once the user starts typing", async () => {
    commandRegistry.registerMany([
      reg({ id: "root.cmd", title: "Alpha", perform: vi.fn() }),
      reg({
        id: "page.scoped",
        title: "Beta",
        perform: vi.fn(),
        onPage: "settings.section",
      }),
    ]);
    const store = setupOpenStore();
    renderPalette(store);
    const input = screen.getByTestId(ElementIds.COMMAND_PALETTE_INPUT) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "bet" } });
    await waitFor(() => {
      expect(document.querySelector('[data-command-id="page.scoped"]')).not.toBeNull();
    });
  });

  it("ranks a top-level match above a page-scoped match for the same query at root", async () => {
    // Both commands match "open" — the top-level one as a word prefix on
    // "Open" (score 0.8), the page-scoped one as a prefix on "Open page"
    // (score 0.9). Without the page-scoped penalty the page-scoped item
    // would render first; with it the top-level item must come first.
    commandRegistry.registerMany([
      reg({ id: "root.match", title: "Open settings", group: "navigation", perform: vi.fn() }),
      reg({
        id: "page.match",
        title: "Open page",
        group: "navigation",
        perform: vi.fn(),
        onPage: "settings.section",
      }),
    ]);
    const store = setupOpenStore();
    renderPalette(store);
    const input = screen.getByTestId(ElementIds.COMMAND_PALETTE_INPUT) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "open" } });
    await waitFor(() => {
      expect(document.querySelector('[data-command-id="page.match"]')).not.toBeNull();
    });
    const items = Array.from(document.querySelectorAll<HTMLElement>("[data-command-id]"));
    const ids = items.map((el) => el.getAttribute("data-command-id"));
    expect(ids.indexOf("root.match")).toBeGreaterThanOrEqual(0);
    expect(ids.indexOf("root.match")).toBeLessThan(ids.indexOf("page.match"));
  });

  it("refuses to close while a command is pending", async () => {
    // Block the perform on a never-resolving promise so the pending state
    // sticks. We then dispatch Escape and confirm the palette stays open.
    let resolvePerform!: () => void;
    const slow = new Promise<void>((res) => {
      resolvePerform = res;
    });
    commandRegistry.register(reg({ id: "slow.cmd", title: "Slow", perform: () => slow }));
    const store = setupOpenStore();
    renderPalette(store);
    fireEvent.click(document.querySelector('[data-command-id="slow.cmd"]')!);
    // Pending is set synchronously by the runner before awaiting.
    await waitFor(() => expect(store.get(commandPalettePendingAtom)).toBe("slow.cmd"));
    // Try to close via Escape on the input. The palette must NOT close
    // while a command is in flight.
    const input = screen.getByTestId(ElementIds.COMMAND_PALETTE_INPUT);
    fireEvent.keyDown(input, { key: "Escape" });
    expect(store.get(commandPaletteOpenAtom)).toBe(true);
    // Resolve the perform so the test cleans up.
    resolvePerform();
    await waitFor(() => expect(store.get(commandPalettePendingAtom)).toBeNull());
  });

  it("releases pending state after a 30s timeout when perform never resolves", async () => {
    // A command whose `perform` never resolves used to leave
    // `commandPalettePendingAtom` set forever, which made `handleOpenChange`
    // refuse to close the palette. The runner now races perform against a
    // 30s timeout and clears pending so the user can recover.
    vi.useFakeTimers();
    try {
      const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
      commandRegistry.register(
        reg({
          id: "test.hung",
          title: "Hung command",
          // Never resolves — simulates a perform that's stuck (e.g., an
          // awaited fetch that never returns).
          perform: () => new Promise(() => {}),
        }),
      );
      const store = setupOpenStore();
      renderPalette(store);

      fireEvent.click(document.querySelector('[data-command-id="test.hung"]')!);

      // Pending is set synchronously by the runner before awaiting.
      await vi.waitFor(() => expect(store.get(commandPalettePendingAtom)).toBe("test.hung"));

      // Advance past the 30s safety timeout.
      await vi.advanceTimersByTimeAsync(30_001);

      await vi.waitFor(() => expect(store.get(commandPalettePendingAtom)).toBeNull());
      expect(warnSpy).toHaveBeenCalled();
      const warnMessages = warnSpy.mock.calls.map((c) => String(c[0]));
      expect(warnMessages.some((m) => m.includes("did not complete"))).toBe(true);
      warnSpy.mockRestore();
    } finally {
      vi.useRealTimers();
    }
  });

  it("emits a command_palette.command_run telemetry event when a command runs", async () => {
    const captureSpy = vi.spyOn(posthog, "capture").mockImplementation(() => undefined as never);
    commandRegistry.register(reg({ id: "test.tracked", title: "Tracked", perform: vi.fn(), group: "navigation" }));
    const store = setupOpenStore();
    renderPalette(store);
    fireEvent.click(document.querySelector('[data-command-id="test.tracked"]')!);
    await waitFor(() => expect(captureSpy).toHaveBeenCalled());
    const runEvents = captureSpy.mock.calls.filter((c) => c[0] === "command_palette.command_run");
    expect(runEvents).toHaveLength(1);
    const [, props] = runEvents[0]!;
    expect(props).toMatchObject({
      command_id: "test.tracked",
      group: "navigation",
      keep_open: false,
      timed_out: false,
      threw: false,
    });
    expect(typeof (props as Record<string, unknown>).elapsed_ms).toBe("number");
    expect(props).not.toHaveProperty("is_page_opener");
    captureSpy.mockRestore();
  });

  it("does NOT emit a command_palette.command_run event for page-opener commands", async () => {
    const captureSpy = vi.spyOn(posthog, "capture").mockImplementation(() => undefined as never);
    commandRegistry.register(
      reg({
        id: "test.opener_no_event",
        title: "Open Sub",
        perform: () => {},
        pageId: "theme.appearance",
      }),
    );
    const store = setupOpenStore();
    renderPalette(store);
    fireEvent.click(document.querySelector('[data-command-id="test.opener_no_event"]')!);
    // Wait for the run to complete (page push happens synchronously).
    await waitFor(() => expect(store.get(commandPalettePagesAtom)).toEqual(["theme.appearance"]));
    await Promise.resolve();
    const runEvents = captureSpy.mock.calls.filter((c) => c[0] === "command_palette.command_run");
    expect(runEvents).toHaveLength(0);
    captureSpy.mockRestore();
  });

  it("Cmd+Enter on the auto-highlighted page-opener pushes the sub-page (with keepOpen)", async () => {
    commandRegistry.register(
      reg({
        id: "test.cmdenter_opener",
        title: "Open Sub",
        perform: () => {},
        pageId: "theme.appearance",
      }),
    );
    commandRegistry.register(
      reg({ id: "test.cmdenter_subitem", title: "Sub Item", perform: () => {}, onPage: "theme.appearance" }),
    );
    const store = setupOpenStore();
    renderPalette(store);
    const input = screen.getByTestId(ElementIds.COMMAND_PALETTE_INPUT);
    // First row is auto-highlighted on open.
    await waitFor(() => {
      expect(document.querySelector('[data-command-id="test.cmdenter_opener"][data-selected="true"]')).not.toBeNull();
    });
    fireEvent.keyDown(input, { key: "Enter", metaKey: true });
    await waitFor(() => expect(store.get(commandPalettePagesAtom)).toEqual(["theme.appearance"]));
    expect(store.get(commandPaletteOpenAtom)).toBe(true);
  });

  it("auto-highlights the first row on open so Enter works immediately", async () => {
    commandRegistry.register(reg({ id: "test.initial_select", title: "Pick me first", perform: () => {} }));
    const store = setupOpenStore();
    renderPalette(store);
    // cmdk's natural mount-time auto-selection is allowed through —
    // the controlled `value` is no longer pinned to "" on open.
    await waitFor(() => {
      expect(document.querySelector('[data-command-id="test.initial_select"][data-selected="true"]')).not.toBeNull();
    });
  });

  it("auto-highlights the top-scoring match while typing", async () => {
    commandRegistry.registerMany([
      reg({ id: "test.search_top", title: "Apple", perform: () => {} }),
      reg({ id: "test.search_other", title: "Banana", perform: () => {} }),
    ]);
    const store = setupOpenStore();
    renderPalette(store);
    const input = screen.getByTestId(ElementIds.COMMAND_PALETTE_INPUT) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "appl" } });
    // cmdk re-runs its auto-selection after every search change, so the
    // top-scoring match is the active row without any priming arrow-key.
    await waitFor(() => {
      expect(document.querySelector('[data-command-id="test.search_top"][data-selected="true"]')).not.toBeNull();
    });
  });

  it("ignores cursor position until the cursor actually moves", async () => {
    // The user can be mid-mouse-motion when they hit Cmd+K. The first
    // pointermove that fires under the freshly-mounted dialog must NOT
    // override the keyboard-selected first row — only subsequent moves
    // (proof of intentional cursor motion) grab the row under the
    // pointer.
    commandRegistry.registerMany([
      reg({ id: "test.cursor_first", title: "First row", perform: () => {} }),
      reg({ id: "test.cursor_second", title: "Second row", perform: () => {} }),
    ]);
    const store = setupOpenStore();
    renderPalette(store);

    await waitFor(() => {
      expect(document.querySelector('[data-command-id="test.cursor_first"][data-selected="true"]')).not.toBeNull();
    });

    const secondRow = document.querySelector('[data-command-id="test.cursor_second"]')!;
    // First pointermove (the "cursor was already in flight when palette
    // opened" simulation) is swallowed.
    fireEvent.pointerMove(secondRow);
    expect(document.querySelector('[data-command-id="test.cursor_first"][data-selected="true"]')).not.toBeNull();
    expect(document.querySelector('[data-command-id="test.cursor_second"][data-selected="true"]')).toBeNull();

    // Second pointermove — the cursor has now demonstrably moved, so we
    // honor it and grab the row under it.
    fireEvent.pointerMove(secondRow);
    await waitFor(() => {
      expect(document.querySelector('[data-command-id="test.cursor_second"][data-selected="true"]')).not.toBeNull();
    });
  });

  it("during search, hides page-openers whose sub-page already has a matching item", async () => {
    // The page-opener "Workspace actions..." is redundant once
    // "Delete workspace" (its child) is on screen, so we drop the
    // opener from the rendered list.
    commandRegistry.register(
      reg({ id: "ws.actions.open", title: "Workspace actions...", perform: () => {}, pageId: "workspace.actions" }),
    );
    commandRegistry.register(
      reg({
        id: "ws.action.delete",
        title: "Delete workspace: Untitled",
        perform: () => {},
        onPage: "workspace.actions",
      }),
    );
    const store = setupOpenStore();
    renderPalette(store);
    const input = screen.getByTestId(ElementIds.COMMAND_PALETTE_INPUT) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "delete" } });
    await waitFor(() => {
      expect(document.querySelector('[data-command-id="ws.action.delete"]')).not.toBeNull();
    });
    expect(document.querySelector('[data-command-id="ws.actions.open"]')).toBeNull();
  });

  it("during search, keeps the page-opener visible when no child of its sub-page matches", async () => {
    // Without a matching child, the page-opener is the only path to
    // the sub-page, so we keep it.
    commandRegistry.register(
      reg({ id: "ws.actions.open2", title: "Workspace actions...", perform: () => {}, pageId: "workspace.actions" }),
    );
    commandRegistry.register(
      reg({
        id: "ws.action.rename",
        title: "Rename: Untitled",
        perform: () => {},
        onPage: "workspace.actions",
      }),
    );
    const store = setupOpenStore();
    renderPalette(store);
    const input = screen.getByTestId(ElementIds.COMMAND_PALETTE_INPUT) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "workspace" } });
    await waitFor(() => {
      expect(document.querySelector('[data-command-id="ws.actions.open2"]')).not.toBeNull();
    });
  });

  it("renders no footer", () => {
    commandRegistry.register(reg({ id: "test.no_footer", title: "No footer please", perform: () => {} }));
    const store = setupOpenStore();
    renderPalette(store);
    expect(screen.queryByTestId(ElementIds.COMMAND_PALETTE_FOOTER)).toBeNull();
  });

  it("opens directly to a sub-page when seeded via commandPaletteInitialPageAtom (Cmd+P flow)", async () => {
    // The Cmd+P keybinding wants to open the palette already on the
    // workspaces.switch sub-page in one gesture. It does this by
    // setting `commandPaletteInitialPageAtom` and flipping isOpen in
    // the same React batch. The reset effect should seed the page
    // stack with [initial] instead of clobbering to [].
    commandRegistry.register(
      reg({
        id: "test.initial_page_subitem",
        title: "Sub Item",
        perform: () => {},
        onPage: "theme.appearance",
      }),
    );
    const store = createStore();
    // Start CLOSED so the open transition fires.
    store.set(commandPaletteOpenAtom, false);
    // Seed initial page, then open in the same tick.
    const { commandPaletteInitialPageAtom } = await import("../atoms.ts");
    store.set(commandPaletteInitialPageAtom, "theme.appearance");
    store.set(commandPaletteOpenAtom, true);
    renderPalette(store);

    await waitFor(() => {
      expect(store.get(commandPalettePagesAtom)).toEqual(["theme.appearance"]);
    });
    // The atom should be cleared after consumption so the next plain
    // open() doesn't accidentally re-land on the same sub-page.
    expect(store.get(commandPaletteInitialPageAtom)).toBeNull();
  });
});
