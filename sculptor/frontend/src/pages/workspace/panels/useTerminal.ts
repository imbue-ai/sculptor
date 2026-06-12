import "@xterm/xterm/css/xterm.css";

import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import { WebglAddon } from "@xterm/addon-webgl";
import type { ITheme } from "@xterm/xterm";
import { Terminal as XTerm } from "@xterm/xterm";
import { useAtomValue, useSetAtom } from "jotai";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { baseUrl } from "~/apiClient.ts";
import { getSessionToken, SESSION_TOKEN_HEADER_NAME } from "~/common/Auth.ts";
import { keybindingsMapAtom } from "~/common/keybindings/atoms.ts";
import { shouldHandleKeybinding } from "~/common/ShortcutUtils.ts";
import { useThemeAccentColor, useThemeGrayColor } from "~/common/state/hooks/useThemeBuilder.ts";
import { getColorScale, resolveGrayColor } from "~/common/theme/radixColorHexMap.ts";
import { useResolvedTheme } from "~/common/Utils.ts";
import { commandActionsAtom } from "~/components/CommandPalette/commandActions.ts";

// ---------------------------------------------------------------------------
// Pure helper functions (extracted for testability and readability)
// ---------------------------------------------------------------------------

// ESC character code (0x1B)
const ESC = "\u001b";

/**
 * Check if the data is a terminal query response that should not be sent to the PTY.
 *
 * When the terminal receives queries (e.g., from macOS on focus changes), xterm.js
 * generates responses that get sent via onData. These responses should be consumed
 * by the querying application, not echoed back to the shell where they appear as
 * garbage text.
 *
 * Common responses filtered:
 * - Primary Device Attributes (DA1): ESC [ ? ... c
 * - Secondary Device Attributes (DA2): ESC [ > ... c
 * - Cursor Position Report (CPR): ESC [ row ; col R
 * - OSC responses (colors, title): ESC ] ... (BEL or ST)
 * - Tertiary Device Attributes (DA3): ESC P ! | ... ST
 */
const isTerminalQueryResponse = (data: string): boolean => {
  if (!data.startsWith(ESC)) {
    return false;
  }

  // CSI responses: DA1 (ESC [ ? ... c), DA2 (ESC [ > ... c), DSR responses,
  // and CPR (Cursor Position Report: ESC [ row ; col R)
  if (data.length >= 3 && data[1] === "[") {
    if (data.endsWith("c") || data.endsWith("R")) {
      return true;
    }
  }

  // OSC responses: ESC ] ... (responses to color queries, title queries, etc.)
  if (data.length >= 3 && data[1] === "]") {
    return true;
  }

  // DCS responses: ESC P ... ST (used for DA3, DECRQSS responses)
  if (data.length >= 2 && data[1] === "P") {
    return true;
  }

  return false;
};

// BEL (0x07) — one of the OSC string terminators.
const BEL = "";

// Reused decoder for scanning live PTY output for terminal queries. UTF-8
// decoding preserves the ASCII bytes (ESC, digits, ';', 'n', 'c', '?', etc.)
// that query detection inspects, so it is safe for this purpose even on
// arbitrary binary output.
const TERMINAL_OUTPUT_DECODER = new TextDecoder();

// Window (ms) within which a query response is treated as solicited by a live
// query from the running program and forwarded to the PTY. It only needs to
// bridge xterm.js's write()->onData() latency; kept short so a stray spurious
// response is unlikely to fall inside it.
const SOLICITED_QUERY_RESPONSE_WINDOW_MS = 1000;

/**
 * Detect a terminal QUERY in live PTY output that xterm.js will answer with a
 * response `isTerminalQueryResponse` would otherwise filter.
 *
 * A real terminal always returns such a response to the program that asked, so
 * an interactive CLI keeps working — e.g. `gh auth login` issues a DSR
 * cursor-position query (ESC[6n) and blocks reading the reply. We mirror that
 * by forwarding a query response only when the running program issued a query
 * in the live output stream; responses with no preceding live query are
 * spurious (a focus change, or the buffered-output replay on reconnect) and
 * are dropped so they don't leak into the shell as garbage like "1;1R".
 *
 * Detected (matching what xterm.js answers with a filtered response):
 * - DSR (e.g. ESC[6n) and DA (e.g. ESC[c, ESC[>c): a CSI whose final byte is
 *   `n` or `c`. Normal display output uses other final bytes (m for SGR,
 *   H/J/K for cursor/erase), so this stays tight.
 * - OSC color/title queries (e.g. ESC]10;? / ESC]11;? / ESC]4;1;?): an OSC
 *   containing `?`.
 *
 * Implemented with a string scan rather than a regex so the ESC/BEL control
 * characters don't trip `no-control-regex` (mirrors `isTerminalQueryResponse`).
 */
export const containsTerminalQuery = (data: string): boolean => {
  for (let i = 0; i < data.length; i++) {
    if (data[i] !== ESC) {
      continue;
    }
    const introducer = data[i + 1];
    if (introducer === "[") {
      // CSI: skip the parameter/intermediate bytes, then test the final byte.
      for (let j = i + 2; j < data.length; j++) {
        const ch = data[j];
        if ((ch >= "0" && ch <= "9") || ch === ";" || ch === "?" || ch === ">" || ch === "=") {
          continue;
        }

        if (ch === "n" || ch === "c") {
          return true;
        }
        break; // some other final byte — not a query xterm answers as filtered
      }
    } else if (introducer === "]") {
      // OSC: a `?` before the string terminator marks a query.
      for (let j = i + 2; j < data.length; j++) {
        const ch = data[j];
        if (ch === BEL || ch === ESC) {
          break;
        }

        if (ch === "?") {
          return true;
        }
      }
    }
  }
  return false;
};

/**
 * Whether a query response should be forwarded to the PTY, given `now` and the
 * time the running program last issued a query in the live output stream.
 */
export const shouldForwardQueryResponse = (now: number, lastLiveQueryAt: number): boolean =>
  now - lastLiveQueryAt <= SOLICITED_QUERY_RESPONSE_WINDOW_MS;

/** Build the xterm.js theme from the resolved panel background and app theme.
 *
 * The panel background is computed from the Radix color scale in JS rather than
 * read from the DOM via getComputedStyle.  Reading CSS custom properties after a
 * theme toggle can return stale values because the Radix theme's CSS class change
 * may not have been applied by the time React's useEffect fires.
 */
const buildTerminalTheme = (panelBg: string, appTheme: string): ITheme => {
  if (appTheme === "dark") {
    return {
      background: panelBg,
      foreground: "#E6E2DC",
      cursor: "#E6E2DC",
      cursorAccent: panelBg,
      selectionBackground: "#4A4540",
    };
  }
  return {
    background: panelBg,
    foreground: "#3B352B",
    cursor: "#3B352B",
    cursorAccent: panelBg,
    selectionBackground: "#D4D0C8",
  };
};

/** Resolve the scheme + host portion of the terminal WebSocket URL. */
const resolveTerminalWsBaseUrl = async (terminalPath: string): Promise<string> => {
  // Prefer the already-resolved baseUrl (handles both default and custom-command backends).
  if (baseUrl) {
    const httpUrl = new URL(baseUrl);
    const wsProtocol = httpUrl.protocol === "https:" ? "wss:" : "ws:";
    return `${wsProtocol}//${httpUrl.host}${terminalPath}`;
  }

  if (API_URL_BASE) {
    const apiUrl = new URL(API_URL_BASE);
    const wsProtocol = apiUrl.protocol === "https:" ? "wss:" : "ws:";
    return `${wsProtocol}//${apiUrl.host}${terminalPath}`;
  }

  if (window.sculptor) {
    const port = await window.sculptor.getBackendPort();
    return `ws://localhost:${port}${terminalPath}`;
  }
  // Fallback for browser-only mode (e.g., testing)
  const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${wsProtocol}//${window.location.host}${terminalPath}`;
};

/** Construct the WebSocket URL for the terminal backend, including auth. */
const getWebSocketUrl = async (terminalPath: string): Promise<string> => {
  const wsUrl = await resolveTerminalWsBaseUrl(terminalPath);
  // Attach the session token for CSRF protection, mirroring useWebsocket.ts.
  // The handshake can't carry a custom header, so the token goes in the query
  // string. In the browser (non-Electron) path getSessionToken() is undefined
  // and the token rides along as a SameSite cookie instead. Use URL/searchParams
  // (like useWebsocket.ts) so encoding and an existing param are handled correctly.
  const sessionToken = getSessionToken();
  if (sessionToken) {
    const urlObj = new URL(wsUrl);
    urlObj.searchParams.set(SESSION_TOKEN_HEADER_NAME, sessionToken);
    return urlObj.toString();
  }
  return wsUrl;
};

/**
 * Attach a custom keyboard handler to xterm.js that sends readline-compatible
 * escape sequences for Alt+Arrow and explicit control characters for Ctrl+letter.
 *
 * Alt+Arrow keys: xterm.js generates CSI sequences like \x1b[1;3D that many
 * shells (bash/zsh) don't bind by default. Send the universally supported
 * Emacs-style sequences instead (\x1bb / \x1bf for word nav).
 *
 * Ctrl+letter: send the control character directly to the PTY, bypassing
 * xterm.js's internal handling which may not fire reliably on all platforms
 * (e.g., Chromium can intercept Ctrl+C for clipboard copy).
 *
 * Both branches call `stopImmediatePropagation` after sending so the event
 * never reaches the window-level Sculptor keybinding handler. Without this,
 * a user-bound Sculptor shortcut on (e.g.) Ctrl+L would fire alongside the
 * shell's own Ctrl+L handling — the terminal needs to fully own these keys
 * while it has focus.
 */
const attachKeyboardHandler = (xterm: XTerm, wsRef: React.RefObject<WebSocket | null>): void => {
  xterm.attachCustomKeyEventHandler((event: KeyboardEvent): boolean => {
    if (event.type !== "keydown") {
      return true;
    }

    const currentWs = wsRef.current;
    if (!currentWs || currentWs.readyState !== WebSocket.OPEN) {
      return true;
    }

    // Alt+Arrow: send readline/zsh word-navigation escape sequences.
    if (event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey) {
      if (event.key === "ArrowLeft") {
        currentWs.send(new TextEncoder().encode("\x1bb"));
        event.preventDefault();
        event.stopImmediatePropagation();
        return false;
      }

      if (event.key === "ArrowRight") {
        currentWs.send(new TextEncoder().encode("\x1bf"));
        event.preventDefault();
        event.stopImmediatePropagation();
        return false;
      }
    }

    // Ctrl+letter: send the control character (e.g., Ctrl+C → 0x03).
    if (event.ctrlKey && !event.shiftKey && !event.altKey && !event.metaKey) {
      const key = event.key.toLowerCase();
      if (key.length === 1 && key >= "a" && key <= "z") {
        const controlChar = String.fromCharCode(key.charCodeAt(0) - 96);
        currentWs.send(new TextEncoder().encode(controlChar));
        event.preventDefault();
        event.stopImmediatePropagation();
        return false;
      }
    }

    return true;
  });
};

/**
 * Pure predicate for "should the focused-terminal clear gesture fire?".
 *
 * Pulled out of the keydown listener so it's unit-testable without standing
 * up xterm.js + WebSocket + DOM layout in jsdom.
 *
 * `container.contains(document.activeElement)` is what gates per-tab focus:
 * only the tab whose xterm textarea currently holds focus matches, so a
 * background tab won't fire even if it's mounted.
 */
export const shouldClearActiveTerminal = (
  event: KeyboardEvent,
  binding: string | null,
  container: HTMLElement | null,
): boolean => {
  if (binding == null) return false;
  if (!shouldHandleKeybinding(event, binding)) return false;
  return container != null && container.contains(document.activeElement);
};

// ---------------------------------------------------------------------------
// useTerminal hook
// ---------------------------------------------------------------------------

type UseTerminalArgs = {
  /** The backend WebSocket path for this terminal's PTY, e.g.
   * `/api/v1/workspaces/{id}/terminal/{index}/ws` (workspace terminals) or
   * `/api/v1/agents/{id}/terminal/ws` (terminal agents). */
  terminalPath: string;
  isVisible: boolean;
  onOutput?: () => void;
};

type UseTerminalResult = {
  terminalContainerRef: React.RefObject<HTMLDivElement>;
};

export const useTerminal = ({ terminalPath, isVisible, onOutput }: UseTerminalArgs): UseTerminalResult => {
  const terminalContainerRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<XTerm | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  // Query/response correlation so solicited query responses (e.g. gh's CPR)
  // reach the PTY while spurious ones (focus changes, buffered replay on
  // reconnect) are dropped. See containsTerminalQuery / shouldForwardQueryResponse.
  const lastLiveQueryAtRef = useRef<number>(Number.NEGATIVE_INFINITY);
  const hasReceivedReplayRef = useRef<boolean>(false);
  const onOutputRef = useRef(onOutput);
  onOutputRef.current = onOutput;
  const appTheme = useResolvedTheme();
  const grayColor = useThemeGrayColor();
  const accentColor = useThemeAccentColor();
  const [isXtermReady, setIsXtermReady] = useState<boolean>(false);

  // Compute the terminal panel background from the Radix color scale in JS.
  // This avoids reading CSS custom properties via getComputedStyle, which can
  // return stale values during a theme toggle (the Radix CSS class change may
  // not be applied by the time React's useEffect fires).
  // --terminal-panel-bg is defined as var(--gray-2), i.e. step 2 (index 1).
  const panelBg = getColorScale(resolveGrayColor(grayColor, accentColor), appTheme)[1];

  const getTheme = useCallback(() => buildTerminalTheme(panelBg, appTheme), [panelBg, appTheme]);

  const handleResize = useCallback((): void => {
    const fitAddon = fitAddonRef.current;
    const ws = wsRef.current;
    const xterm = xtermRef.current;

    if (fitAddon && xterm) {
      fitAddon.fit();

      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(
          JSON.stringify({
            type: "resize",
            rows: xterm.rows,
            cols: xterm.cols,
          }),
        );
      }
    }
  }, []);

  // Initialize xterm instance (no network — just the terminal widget and addons)
  useEffect(() => {
    const container = terminalContainerRef.current;
    if (!container) {
      return;
    }

    let isCleanedUp = false;

    const initXterm = (): void => {
      if (isCleanedUp) return;

      // Wait for container to have proper dimensions before initializing
      if (container.clientWidth === 0 || container.clientHeight === 0) {
        requestAnimationFrame(initXterm);
        return;
      }

      const xterm = new XTerm({
        cursorBlink: true,
        fontSize: 12,
        fontFamily: 'Menlo, Monaco, "Courier New", monospace',
        theme: getTheme(),
        allowProposedApi: true,
        macOptionIsMeta: true,
      });
      xtermRef.current = xterm;

      const fitAddon = new FitAddon();
      fitAddonRef.current = fitAddon;
      xterm.loadAddon(fitAddon);
      xterm.loadAddon(
        new WebLinksAddon((_event, url) => {
          // The default handler opens about:blank first (for reverse-tabnapping
          // prevention), then sets location.href.  In Electron this breaks
          // because setWindowOpenHandler sees "about:blank" and never receives
          // the real URL.  Passing the URL directly works in both Electron
          // (intercepted by setWindowOpenHandler → shell.openExternal) and
          // browser contexts.
          //
          // Only allow http(s) schemes to avoid unexpected actions from other
          // URL schemes (e.g. file://, javascript:).  The addon's built-in
          // regex already filters to http(s), but this is defense-in-depth.
          if (/^https?:\/\//i.test(url)) {
            window.open(url, "_blank");
          }
        }),
      );

      xterm.open(container);
      fitAddon.fit();

      // Use WebGL for GPU-accelerated rendering when available. Falls back to
      // the default canvas renderer if WebGL2 is not supported.
      try {
        const webglAddon = new WebglAddon();
        webglAddon.onContextLoss(() => {
          webglAddon.dispose();
        });
        xterm.loadAddon(webglAddon);
      } catch {
        // WebGL2 not available — canvas renderer is used automatically.
      }

      // Keyboard handler reads wsRef at call time, so it works regardless of
      // which effect creates the WebSocket.
      attachKeyboardHandler(xterm, wsRef);

      // Forward user input to the PTY. Terminal query responses generated by
      // xterm.js are forwarded only when the running program solicited them (a
      // matching query appeared in the live output stream); otherwise they are
      // dropped so spurious responses (focus changes, buffered replay on
      // reconnect) don't leak into the shell as garbage.
      xterm.onData((data) => {
        if (
          isTerminalQueryResponse(data) &&
          !shouldForwardQueryResponse(performance.now(), lastLiveQueryAtRef.current)
        ) {
          return;
        }

        const currentWs = wsRef.current;
        if (currentWs && currentWs.readyState === WebSocket.OPEN) {
          currentWs.send(new TextEncoder().encode(data));
        }
      });

      setIsXtermReady(true);
    };

    initXterm();

    return (): void => {
      isCleanedUp = true;
      setIsXtermReady(false);
      xtermRef.current?.dispose();
      xtermRef.current = null;
      fitAddonRef.current = null;
    };
    // getTheme is intentionally excluded — the initial theme is set at creation
    // time and subsequent theme changes are handled by the theme-update effect.
    // Including it here would tear down and recreate the entire xterm instance
    // on every theme toggle (no_mixed_lifecycles).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Connect WebSocket to the terminal backend (separate lifecycle from xterm)
  useEffect(() => {
    if (!isXtermReady) return;

    let isCleanedUp = false;

    const connectWebSocket = async (wsUrl: string): Promise<void> => {
      if (isCleanedUp) return;

      wsRef.current?.close();

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      ws.binaryType = "arraybuffer";

      // A fresh connection replays the backend's buffered output as its first
      // frame; reset query tracking so replayed (stale) queries aren't treated
      // as live and don't resurrect the spurious-CPR leak.
      hasReceivedReplayRef.current = false;
      lastLiveQueryAtRef.current = Number.NEGATIVE_INFINITY;

      ws.onopen = (): void => {
        handleResize();
      };

      ws.onmessage = (event: MessageEvent): void => {
        const currentXterm = xtermRef.current;
        if (!currentXterm) return;

        let liveText: string | null = null;
        if (event.data instanceof ArrayBuffer) {
          const bytes = new Uint8Array(event.data);
          currentXterm.write(bytes);
          // Decode for query scanning only past the replay frame, and only when
          // an ESC is present (skips the common plain-text / bulk-output case).
          if (hasReceivedReplayRef.current && bytes.includes(0x1b)) {
            liveText = TERMINAL_OUTPUT_DECODER.decode(bytes);
          }
        } else if (typeof event.data === "string") {
          currentXterm.write(event.data);
          if (hasReceivedReplayRef.current && event.data.includes(ESC)) {
            liveText = event.data;
          }
        }

        // The first frame after (re)connect is the backend's buffered replay
        // (sent before any live output). Its queries are stale; treating them as
        // live would resurrect the spurious-CPR garbage the response filter
        // prevents. From the next frame on, a query in live output marks any
        // immediately-following query response as solicited.
        if (!hasReceivedReplayRef.current) {
          hasReceivedReplayRef.current = true;
        } else if (liveText !== null && containsTerminalQuery(liveText)) {
          lastLiveQueryAtRef.current = performance.now();
        }

        onOutputRef.current?.();
      };

      ws.onerror = (error: Event): void => {
        console.error("Terminal WebSocket error:", error);
      };

      // If the terminal isn't running yet (4404), retry after a delay.
      // This handles the case where the frontend has the terminal URL
      // (derived from environment ID) but the backend hasn't started the
      // PTY yet (e.g., workspace just created, first agent still starting).
      ws.onclose = (event: CloseEvent): void => {
        if (!isCleanedUp && event.code === 4404) {
          setTimeout(() => {
            if (!isCleanedUp) {
              connectWebSocket(wsUrl);
            }
          }, 2000);
        }
      };
    };

    const connect = async (): Promise<void> => {
      const wsUrl = await getWebSocketUrl(terminalPath);
      if (isCleanedUp) return;
      await connectWebSocket(wsUrl);
    };

    connect();

    return (): void => {
      isCleanedUp = true;
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [isXtermReady, terminalPath, handleResize]);

  // Observe container resizes and re-fit the terminal.
  // fit() itself can mutate the terminal's dimensions, so we coalesce via rAF
  // to avoid a resize → fit → resize feedback loop.
  useEffect(() => {
    const container = terminalContainerRef.current;
    if (!container) return;

    let rafId: number | null = null;
    const observer = new ResizeObserver((): void => {
      if (rafId != null) return;
      rafId = requestAnimationFrame(() => {
        rafId = null;
        handleResize();
      });
    });
    observer.observe(container);

    return (): void => {
      observer.disconnect();
      if (rafId != null) {
        cancelAnimationFrame(rafId);
      }
    };
  }, [handleResize]);

  // Refresh terminal display on visibility change and window focus.
  // When switching back to the app, the xterm canvas may not repaint automatically
  // and macOS may have sent escape sequences that corrupt terminal state.
  useEffect(() => {
    const handleVisibilityChange = (): void => {
      if (document.visibilityState === "visible") {
        const currentXterm = xtermRef.current;
        currentXterm?.refresh(0, currentXterm.rows - 1);
      }
    };

    const handleWindowFocus = (): void => {
      const currentXterm = xtermRef.current;
      if (!currentXterm) return;

      currentXterm.refresh(0, currentXterm.rows - 1);

      // Reset keyboard state if the terminal had focus
      const container = terminalContainerRef.current;
      if (container && document.activeElement === container) {
        currentXterm.blur();
        currentXterm.focus();
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("focus", handleWindowFocus);

    return (): void => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("focus", handleWindowFocus);
    };
  }, []);

  // Update theme when it changes.
  // useLayoutEffect ensures the xterm canvas repaints before the browser
  // paints, so the terminal background updates in the same frame as the
  // rest of the UI (which updates via CSS cascade).
  useLayoutEffect(() => {
    const xterm = xtermRef.current;
    if (xterm) {
      xterm.options.theme = getTheme();
    }
  }, [getTheme]);

  // Track whether this is the first time isVisible becomes true (initial mount).
  // We skip auto-focusing the terminal on initial mount so it doesn't steal
  // focus from the chat input when navigating to a new workspace.
  const hasBeenVisibleRef = useRef(false);

  // Re-fit when this terminal becomes visible (container dimensions may have changed).
  // Also expose __xterm for integration tests only when this terminal is the active one.
  useEffect(() => {
    if (isVisible) {
      window.__xterm = xtermRef.current ?? undefined;

      const shouldFocus = hasBeenVisibleRef.current;
      hasBeenVisibleRef.current = true;

      // Re-fit after a frame so the container has its final dimensions.
      // Only focus the terminal when the user explicitly toggles it visible
      // (not on initial mount, which would steal focus from the chat input).
      requestAnimationFrame(() => {
        handleResize();
        if (shouldFocus) {
          xtermRef.current?.focus();
        }
      });
    }

    return (): void => {
      if (window.__xterm === xtermRef.current) {
        delete window.__xterm;
      }
    };
  }, [isVisible, handleResize]);

  // ── Clear-terminal keybinding (focus-gated) ────────────────────────
  //
  // Mirrors the `interrupt_agent` pattern in ChatInput.tsx — we read the
  // resolved binding from the keybindings registry and attach a window-level
  // keydown listener that only fires when this terminal instance has
  // keyboard focus. We use capture phase + stopImmediatePropagation so a
  // user-rebound combo that overlaps with a global keybinding (e.g.
  // command_palette's Cmd+K) is consumed here before bubbling to the
  // page-layout handler.
  const keybindingsMap = useAtomValue(keybindingsMapAtom);
  const clearTerminalBinding = keybindingsMap["clear_terminal"]?.binding ?? null;
  useEffect(() => {
    if (!isVisible || clearTerminalBinding == null) return;

    const listener = (e: KeyboardEvent): void => {
      if (!shouldClearActiveTerminal(e, clearTerminalBinding, terminalContainerRef.current)) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      xtermRef.current?.clear();
    };

    window.addEventListener("keydown", listener, { capture: true });
    return (): void => window.removeEventListener("keydown", listener, { capture: true });
  }, [isVisible, clearTerminalBinding]);

  // Register the palette-driven `Clear terminal` action only while this
  // terminal is the active tab — the command palette resolves a single
  // callback per action id, so gating on `isVisible` ensures the visible
  // tab owns the registration and other open tabs don't overwrite it.
  const setCommandActions = useSetAtom(commandActionsAtom);
  useEffect(() => {
    if (!isVisible) return;
    const clear = (): void => {
      xtermRef.current?.clear();
    };
    setCommandActions((prev) => ({ ...prev, "terminal.clearActive": clear }));
    return (): void => {
      setCommandActions((prev) => {
        if (prev["terminal.clearActive"] !== clear) return prev;
        const next = { ...prev };
        delete next["terminal.clearActive"];
        return next;
      });
    };
  }, [isVisible, setCommandActions]);

  return { terminalContainerRef };
};
