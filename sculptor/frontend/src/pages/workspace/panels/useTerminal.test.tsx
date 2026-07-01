import { act, render, renderHook } from "@testing-library/react";
import { getDefaultStore } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { commandActionsAtom } from "~/components/CommandPalette/commandActions.ts";

import type { TerminalConnectionStatus } from "./useTerminal.ts";
import {
  containsTerminalQuery,
  shouldClearActiveTerminal,
  shouldForwardQueryResponse,
  useTerminal,
} from "./useTerminal.ts";

// Mock xterm.js and its addons so the hook's terminal-init effect runs to
// completion in jsdom (setting `isXtermReady`, which gates the WebSocket
// effect) without a real canvas/WebGL terminal. The mocks implement only the
// members the hook touches.
vi.mock("@xterm/xterm", () => ({
  Terminal: class {
    rows = 24;
    cols = 80;
    options: Record<string, unknown> = {};
    buffer = { active: { cursorY: 0, baseY: 0, getLine: (): null => null } };
    loadAddon(): void {}
    open(): void {}
    onData(): void {}
    attachCustomKeyEventHandler(): void {}
    dispose(): void {}
    focus(): void {}
    blur(): void {}
    refresh(): void {}
    clear(): void {}
    write(): void {}
  },
}));
vi.mock("@xterm/addon-fit", () => ({
  FitAddon: class {
    fit(): void {}
  },
}));
vi.mock("@xterm/addon-web-links", () => ({
  WebLinksAddon: class {
    constructor(_handler: unknown) {}
  },
}));
vi.mock("@xterm/addon-webgl", () => ({
  WebglAddon: class {
    onContextLoss(): void {}
    dispose(): void {}
  },
}));

// jsdom's KeyboardEvent constructor drops metaKey/ctrlKey from the init
// dict, so the existing `ShortcutUtils.test.ts` plain-object pattern is the
// canonical way to build a key event the matcher will inspect.
type KeyEventOverrides = {
  key: string;
  code?: string;
  metaKey?: boolean;
  ctrlKey?: boolean;
  altKey?: boolean;
  shiftKey?: boolean;
};

const fakeKeyEvent = (overrides: KeyEventOverrides): KeyboardEvent =>
  ({
    key: overrides.key,
    code: overrides.code ?? "",
    metaKey: overrides.metaKey ?? false,
    ctrlKey: overrides.ctrlKey ?? false,
    altKey: overrides.altKey ?? false,
    shiftKey: overrides.shiftKey ?? false,
    preventDefault: vi.fn(),
    stopImmediatePropagation: vi.fn(),
  }) as unknown as KeyboardEvent;

describe("shouldClearActiveTerminal", () => {
  let container: HTMLDivElement;
  let inside: HTMLInputElement;
  let outside: HTMLInputElement;
  const savedSculptor = window.sculptor;

  beforeEach(() => {
    // Force the "Meta means Cmd" branch of shouldHandleKeybinding so the
    // tests read like the spec's macOS scenario.
    window.sculptor = { platform: "darwin" } as unknown as typeof window.sculptor;

    container = document.createElement("div");
    inside = document.createElement("input");
    container.appendChild(inside);
    outside = document.createElement("input");
    document.body.appendChild(container);
    document.body.appendChild(outside);
  });

  afterEach(() => {
    if (savedSculptor === undefined) {
      delete (window as unknown as Record<string, unknown>).sculptor;
    } else {
      window.sculptor = savedSculptor;
    }
    container.remove();
    outside.remove();
  });

  it("returns true when the binding matches and the focused element is inside the container", () => {
    inside.focus();
    expect(
      shouldClearActiveTerminal(fakeKeyEvent({ key: "k", metaKey: true, shiftKey: true }), "Meta+Shift+K", container),
    ).toBe(true);
  });

  it("returns false when the focused element is outside the container", () => {
    // This is the "Cmd+Shift+K in the chat input" scenario from the spec —
    // the binding matches but the terminal isn't focused, so nothing should
    // fire and the event must keep propagating to other handlers.
    outside.focus();
    expect(
      shouldClearActiveTerminal(fakeKeyEvent({ key: "k", metaKey: true, shiftKey: true }), "Meta+Shift+K", container),
    ).toBe(false);
  });

  it("returns false when no element is focused (document.activeElement is body)", () => {
    (document.activeElement as HTMLElement | null)?.blur();
    expect(document.activeElement).toBe(document.body);
    expect(
      shouldClearActiveTerminal(fakeKeyEvent({ key: "k", metaKey: true, shiftKey: true }), "Meta+Shift+K", container),
    ).toBe(false);
  });

  it("returns false when the container is null (terminal not yet mounted)", () => {
    inside.focus();
    expect(
      shouldClearActiveTerminal(fakeKeyEvent({ key: "k", metaKey: true, shiftKey: true }), "Meta+Shift+K", null),
    ).toBe(false);
  });

  it("returns false when the binding is null (user cleared the shortcut)", () => {
    inside.focus();
    expect(shouldClearActiveTerminal(fakeKeyEvent({ key: "k", metaKey: true, shiftKey: true }), null, container)).toBe(
      false,
    );
  });

  it("returns false when the event does not match the binding combo", () => {
    inside.focus();
    // Plain "K" without modifiers — same key, wrong combo.
    expect(shouldClearActiveTerminal(fakeKeyEvent({ key: "k" }), "Meta+Shift+K", container)).toBe(false);
  });

  it("respects a user-rebound combo (Ctrl+Shift+L)", () => {
    // Per spec: rebinding works through the normal registry path. The
    // predicate just receives whatever resolved binding string came in.
    inside.focus();
    expect(
      shouldClearActiveTerminal(fakeKeyEvent({ key: "l", ctrlKey: true, shiftKey: true }), "Ctrl+Shift+L", container),
    ).toBe(true);
  });
});

describe("containsTerminalQuery", () => {
  const ESC = "";

  it("detects a DSR cursor-position query (ESC[6n)", () => {
    // The query gh's survey library issues before blocking to read the reply.
    expect(containsTerminalQuery(`${ESC}[6n`)).toBe(true);
  });

  it("detects a DSR query embedded in surrounding output", () => {
    expect(containsTerminalQuery(`some prompt ${ESC}[6n trailing`)).toBe(true);
  });

  it("detects Device Attributes queries (ESC[c, ESC[>c, ESC[0c)", () => {
    expect(containsTerminalQuery(`${ESC}[c`)).toBe(true);
    expect(containsTerminalQuery(`${ESC}[>c`)).toBe(true);
    expect(containsTerminalQuery(`${ESC}[0c`)).toBe(true);
  });

  it("detects an OSC color query (ESC]11;?)", () => {
    expect(containsTerminalQuery(`${ESC}]11;?`)).toBe(true);
  });

  it("ignores plain text", () => {
    expect(containsTerminalQuery("hello world\n$ ")).toBe(false);
  });

  it("ignores SGR colour and cursor/erase sequences (xterm answers none of these)", () => {
    // SGR ends in 'm', cursor home in 'H', clear in 'J' — none are queries.
    expect(containsTerminalQuery(`${ESC}[1;31mred${ESC}[0m`)).toBe(false);
    expect(containsTerminalQuery(`${ESC}[2J${ESC}[H`)).toBe(false);
    // Private-mode sets (bracketed paste, cursor show/hide) end in h/l.
    expect(containsTerminalQuery(`${ESC}[?2004h${ESC}[?25l`)).toBe(false);
  });
});

describe("shouldForwardQueryResponse", () => {
  it("forwards a response that closely follows a live query (solicited)", () => {
    // gh's CPR arrives a few ms after its DSR query — it must reach the PTY.
    expect(shouldForwardQueryResponse(1000, 990)).toBe(true);
    expect(shouldForwardQueryResponse(1000, 1000)).toBe(true);
  });

  it("drops a response with no recent live query (spurious: focus / replay)", () => {
    // No live query has ever been seen on this connection.
    expect(shouldForwardQueryResponse(1234, Number.NEGATIVE_INFINITY)).toBe(false);
    // A query was seen, but far too long ago to be the cause of this response.
    expect(shouldForwardQueryResponse(5000, 990)).toBe(false);
  });
});

// We use the default Jotai store and let the hook discover the
// `clear_terminal` binding through KEYBINDING_DEFINITIONS. We do NOT mock
// xterm.js: the hook's first effect early-returns when
// `terminalContainerRef.current` is null (which it is in renderHook), so
// xterm is never constructed and the WebSocket path is never entered. The
// effects under test (commandActions registration + window keydown listener)
// don't depend on xterm being initialised.

const noopWrapper = ({ children }: { children: ReactNode }): ReactElement => <>{children}</>;

describe("useTerminal — commandActions registration", () => {
  const store = getDefaultStore();

  afterEach(() => {
    // Reset the action map so other tests don't see leaked registrations.
    store.set(commandActionsAtom, {});
  });

  it("registers `terminal.clearActive` while isVisible=true", () => {
    expect(store.get(commandActionsAtom)["terminal.clearActive"]).toBeUndefined();

    renderHook(() => useTerminal({ terminalPath: "/api/v1/workspaces/ws_test/terminal/0/ws", isVisible: true }), {
      wrapper: noopWrapper,
    });

    expect(store.get(commandActionsAtom)["terminal.clearActive"]).toBeTypeOf("function");
  });

  it("does NOT register `terminal.clearActive` when isVisible=false", () => {
    renderHook(() => useTerminal({ terminalPath: "/api/v1/workspaces/ws_test/terminal/0/ws", isVisible: false }), {
      wrapper: noopWrapper,
    });
    expect(store.get(commandActionsAtom)["terminal.clearActive"]).toBeUndefined();
  });

  it("unregisters on unmount", () => {
    const { unmount } = renderHook(
      () => useTerminal({ terminalPath: "/api/v1/workspaces/ws_test/terminal/0/ws", isVisible: true }),
      {
        wrapper: noopWrapper,
      },
    );
    expect(store.get(commandActionsAtom)["terminal.clearActive"]).toBeTypeOf("function");
    unmount();
    expect(store.get(commandActionsAtom)["terminal.clearActive"]).toBeUndefined();
  });

  it("unregisters when isVisible flips from true to false", () => {
    // The "active tab owns the slot" handoff: when a user switches to
    // another terminal tab, the previous tab's slot must be cleared so the
    // new tab can claim it.
    const { rerender } = renderHook(
      ({ isVisible }: { isVisible: boolean }) =>
        useTerminal({ terminalPath: "/api/v1/workspaces/ws_test/terminal/0/ws", isVisible }),
      { wrapper: noopWrapper, initialProps: { isVisible: true } },
    );
    expect(store.get(commandActionsAtom)["terminal.clearActive"]).toBeTypeOf("function");
    rerender({ isVisible: false });
    expect(store.get(commandActionsAtom)["terminal.clearActive"]).toBeUndefined();
  });

  it("when two instances cycle visibility, the visible one's slot survives the hidden one's unmount", () => {
    // Regression-lock for the same-ref equality guard. Tab A registers,
    // tab B registers (overwriting A), then A unmounts. A's cleanup must
    // NOT clear B's slot — otherwise switching tabs would leave the palette
    // command with no active receiver.
    const a = renderHook(
      () => useTerminal({ terminalPath: "/api/v1/workspaces/ws_test/terminal/0/ws", isVisible: true }),
      {
        wrapper: noopWrapper,
      },
    );
    const aCallback = store.get(commandActionsAtom)["terminal.clearActive"];
    expect(aCallback).toBeTypeOf("function");

    const b = renderHook(
      () => useTerminal({ terminalPath: "/api/v1/workspaces/ws_test/terminal/1/ws", isVisible: true }),
      {
        wrapper: noopWrapper,
      },
    );
    const bCallback = store.get(commandActionsAtom)["terminal.clearActive"];
    expect(bCallback).toBeTypeOf("function");
    expect(bCallback).not.toBe(aCallback);

    a.unmount();
    // B's registration is still intact.
    expect(store.get(commandActionsAtom)["terminal.clearActive"]).toBe(bCallback);

    b.unmount();
    expect(store.get(commandActionsAtom)["terminal.clearActive"]).toBeUndefined();
  });
});

describe("useTerminal — clear-terminal keydown listener lifecycle", () => {
  let addSpy: ReturnType<typeof vi.spyOn>;
  let removeSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    addSpy = vi.spyOn(window, "addEventListener");
    removeSpy = vi.spyOn(window, "removeEventListener");
  });

  afterEach(() => {
    addSpy.mockRestore();
    removeSpy.mockRestore();
  });

  const keydownAddCalls = (): Array<Parameters<typeof window.addEventListener>> =>
    addSpy.mock.calls.filter((call: Parameters<typeof window.addEventListener>) => call[0] === "keydown") as Array<
      Parameters<typeof window.addEventListener>
    >;

  const keydownRemoveCalls = (): Array<Parameters<typeof window.removeEventListener>> =>
    removeSpy.mock.calls.filter(
      (call: Parameters<typeof window.removeEventListener>) => call[0] === "keydown",
    ) as Array<Parameters<typeof window.removeEventListener>>;

  it("attaches a capture-phase keydown listener when isVisible=true", () => {
    renderHook(() => useTerminal({ terminalPath: "/api/v1/workspaces/ws_test/terminal/0/ws", isVisible: true }));
    const captureAdds = keydownAddCalls().filter((call) => {
      const opts = call[2];
      return typeof opts === "object" && opts != null && "capture" in opts && opts.capture === true;
    });
    // Capture phase is the load-bearing detail per the in-source comment:
    // a rebound combo overlapping with command_palette must be consumed
    // BEFORE the page-layout bubble handler sees it.
    expect(captureAdds.length).toBeGreaterThanOrEqual(1);
  });

  it("does NOT attach the keydown listener when isVisible=false", () => {
    renderHook(() => useTerminal({ terminalPath: "/api/v1/workspaces/ws_test/terminal/0/ws", isVisible: false }));
    const captureAdds = keydownAddCalls().filter((call) => {
      const opts = call[2];
      return typeof opts === "object" && opts != null && "capture" in opts && opts.capture === true;
    });
    expect(captureAdds).toHaveLength(0);
  });

  it("removes the listener on unmount", () => {
    const { unmount } = renderHook(() =>
      useTerminal({ terminalPath: "/api/v1/workspaces/ws_test/terminal/0/ws", isVisible: true }),
    );
    const beforeUnmount = keydownRemoveCalls().length;
    unmount();
    const afterUnmount = keydownRemoveCalls().length;
    expect(afterUnmount).toBeGreaterThan(beforeUnmount);
  });
});

// A minimal WebSocket stand-in. Each construction is recorded so a reconnect is
// observable as a second instance; the hook assigns `onclose`, which the tests
// invoke to drive the real close handler.
class FakeWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  static instances: Array<FakeWebSocket> = [];

  binaryType = "blob";
  readyState: number = FakeWebSocket.CONNECTING;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }

  send(): void {}

  close(): void {
    this.readyState = FakeWebSocket.CLOSED;
  }
}

describe("useTerminal — WebSocket reconnect on close", () => {
  const TERMINAL_PATH = "/api/v1/workspaces/ws_test/terminal/0/ws";
  const RETRY_DELAY_MS = 2000; // mirrors TERMINAL_RECONNECT_RETRY_DELAY_MS

  // The hook only initialises xterm once the container reports non-zero
  // dimensions; jsdom reports 0, so force a size for the duration of these tests.
  const sizeOverride: PropertyDescriptor = { configurable: true, get: () => 100 };

  // Render a real element that wires the hook's container ref to the DOM, so the
  // terminal-init effect (and therefore the WebSocket effect) actually runs.
  const ReconnectHarness = ({
    onConnectionStatusChange,
  }: {
    onConnectionStatusChange?: (status: TerminalConnectionStatus) => void;
  }): ReactElement => {
    const { terminalContainerRef } = useTerminal({
      terminalPath: TERMINAL_PATH,
      isVisible: true,
      onConnectionStatusChange,
    });
    return <div ref={terminalContainerRef} />;
  };

  // The first connection resolves the WS URL through a promise, so drain the
  // microtask queue before asserting. Promise microtasks run independently of
  // fake timers, so this works without advancing them.
  const flushMicrotasks = async (): Promise<void> => {
    for (let i = 0; i < 5; i++) {
      await Promise.resolve();
    }
  };

  const mountAndConnect = async (
    onConnectionStatusChange?: (status: TerminalConnectionStatus) => void,
  ): Promise<ReturnType<typeof render>> => {
    const result = render(<ReconnectHarness onConnectionStatusChange={onConnectionStatusChange} />);
    await flushMicrotasks();
    expect(FakeWebSocket.instances).toHaveLength(1);
    return result;
  };

  // The close handler updates React state (the connection status), so dispatch it
  // through act() to flush that update and avoid "not wrapped in act" warnings.
  const fireClose = (socket: FakeWebSocket, code: number): void => {
    act(() => {
      socket.onclose?.({ code } as CloseEvent);
    });
  };

  beforeEach(() => {
    // Fake timers keep the 2s reconnect delay deterministic and near-instant
    // instead of waiting in real time.
    vi.useFakeTimers();
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
    // resolveTerminalWsBaseUrl reads the API_URL_BASE build-time global; define it
    // (as undefined) so the lookup falls through to the window.location fallback
    // instead of throwing a ReferenceError.
    vi.stubGlobal("API_URL_BASE", undefined);
    Object.defineProperty(HTMLElement.prototype, "clientWidth", sizeOverride);
    Object.defineProperty(HTMLElement.prototype, "clientHeight", sizeOverride);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    delete (HTMLElement.prototype as unknown as Record<string, unknown>).clientWidth;
    delete (HTMLElement.prototype as unknown as Record<string, unknown>).clientHeight;
  });

  it("reconnects after the connection drops with code 1006 (e.g. host sleep)", async () => {
    await mountAndConnect();

    // Simulate the socket being torn down out from under us — the close a macOS
    // sleep produces. The pre-fix handler only retried on code 4404, so this close
    // left the terminal frozen; the fix retries on any recoverable close.
    fireClose(FakeWebSocket.instances[0], 1006);
    vi.advanceTimersByTime(RETRY_DELAY_MS);

    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it("still reconnects when the backend has not started the PTY yet (close code 4404)", async () => {
    // The original retry case must keep working after the fix broadened the trigger.
    await mountAndConnect();

    fireClose(FakeWebSocket.instances[0], 4404);
    vi.advanceTimersByTime(RETRY_DELAY_MS);

    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it("does NOT reconnect after a normal close (code 1000)", async () => {
    // A clean, intentional close means nothing went wrong — retrying would be noise.
    await mountAndConnect();

    fireClose(FakeWebSocket.instances[0], 1000);
    vi.advanceTimersByTime(RETRY_DELAY_MS);

    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("does NOT reconnect when the session token is rejected (code 4401)", async () => {
    // The token is still invalid on a retry, so reconnecting would loop forever
    // until the user re-authenticates.
    await mountAndConnect();

    fireClose(FakeWebSocket.instances[0], 4401);
    vi.advanceTimersByTime(RETRY_DELAY_MS);

    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("does NOT reconnect when the close is our own teardown (unmount)", async () => {
    const { unmount } = await mountAndConnect();
    const initialSocket = FakeWebSocket.instances[0];

    // Unmounting flips the effect's `isCleanedUp` guard. A close firing after that
    // (the unmount closes the socket) must NOT schedule a reconnect, or tearing down
    // a terminal would resurrect its connection.
    unmount();
    // No state update here (the cleanup guard returns before touching status), so
    // dispatch directly rather than through act().
    initialSocket.onclose?.({ code: 1006 } as CloseEvent);
    vi.advanceTimersByTime(RETRY_DELAY_MS);

    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("reports connection status: reconnecting on a recoverable drop, disconnected when unrecoverable", async () => {
    const statuses: Array<TerminalConnectionStatus> = [];
    await mountAndConnect((status) => statuses.push(status));

    const lastStatus = (): TerminalConnectionStatus | undefined => statuses[statuses.length - 1];

    // A recoverable drop should read as reconnecting (the terminal will self-heal).
    fireClose(FakeWebSocket.instances[0], 1006);
    expect(lastStatus()).toBe("reconnecting");

    // An unrecoverable close should read as disconnected (no self-healing).
    fireClose(FakeWebSocket.instances[0], 4401);
    expect(lastStatus()).toBe("disconnected");
  });
});
