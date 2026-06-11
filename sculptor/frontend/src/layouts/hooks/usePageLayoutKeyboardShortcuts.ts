import { useAtomValue, useSetAtom } from "jotai";
import { useEffect, useRef } from "react";

import { ElementIds } from "../../api";
import { CHAT_INPUT_ELEMENT_ID } from "../../common/Constants.ts";
import { keybindingsMapAtom } from "../../common/keybindings/atoms.ts";
import type { KeybindingId } from "../../common/keybindings/types.ts";
import { useImbueNavigate } from "../../common/NavigateUtils.ts";
import { isDismissibleOverlayOpen } from "../../common/overlayUtils.ts";
import { shouldHandleKeybinding } from "../../common/ShortcutUtils.ts";
import { chatSearchFocusRequestAtom, chatSearchVisibleAtom } from "../../common/state/atoms/chatSearch.ts";
import { themeBuilderSettingsAtom } from "../../common/state/atoms/themeBuilder.ts";
import { useDevPanel } from "../../common/state/hooks/useDevPanel.ts";
import { useHelpDialog } from "../../common/state/hooks/useHelpDialog.ts";
import { useOpenSettings } from "../../common/state/hooks/useOpenSettings.ts";
import { useResolvedTheme } from "../../common/Utils.ts";
import { useCommandPalette } from "../../components/CommandPalette";
import { focusedZoneAtom } from "../../components/panels/atoms.ts";
import { useFocusMode, useMaximizePanel, useSideToggle, useZenMode } from "../../components/panels/hooks.ts";
import { isAnySuggestionPopoverActive } from "../../components/SuggestionUtils.ts";
import { chatToolDensityAtom } from "../../pages/workspace/components/chat-alpha/atoms.ts";

export const usePageLayoutKeyboardShortcuts = (): void => {
  const { toggleDevPanel } = useDevPanel();
  const {
    isOpen: isCommandPaletteOpen,
    close: closeCommandPalette,
    toggle: toggleCommandPalette,
    openTo: openCommandPaletteTo,
  } = useCommandPalette();
  const { toggleHelpDialog } = useHelpDialog();
  const { navigateToAddWorkspace, navigateToHome } = useImbueNavigate();
  const setChatSearchVisible = useSetAtom(chatSearchVisibleAtom);
  const setFocusRequest = useSetAtom(chatSearchFocusRequestAtom);
  const openSettings = useOpenSettings();

  const { toggleFocusMode } = useFocusMode();
  const { toggleZenMode } = useZenMode();
  const { toggleMaximizeFocused, restore: restoreMaximizedPanel, maximizedZone } = useMaximizePanel();
  const { toggle: toggleLeftPanel } = useSideToggle("left");
  const { toggle: toggleBottomPanel } = useSideToggle("bottom");
  const { toggle: toggleRightPanel } = useSideToggle("right");
  const resolvedTheme = useResolvedTheme();
  const setThemeSettings = useSetAtom(themeBuilderSettingsAtom);
  const setChatToolDensity = useSetAtom(chatToolDensityAtom);

  const isChatSearchVisible = useAtomValue(chatSearchVisibleAtom);
  const isChatSearchVisibleRef = useRef(isChatSearchVisible);
  isChatSearchVisibleRef.current = isChatSearchVisible;

  // Read the maximized-zone flag from a ref so the Escape handler stays current
  // without re-subscribing the keydown listener on every maximize/restore.
  const maximizedZoneRef = useRef(maximizedZone);
  maximizedZoneRef.current = maximizedZone;

  // Same ref pattern for the focused-pane indicator, read by the two-stage
  // Escape handler below.
  const setFocusedZone = useSetAtom(focusedZoneAtom);
  const focusedZone = useAtomValue(focusedZoneAtom);
  const focusedZoneRef = useRef(focusedZone);
  focusedZoneRef.current = focusedZone;

  // Whether a mention/skill popover was open at the START of the current Escape
  // keydown. Captured in the capture phase (below) because the editor's own
  // Escape handler closes the popover and synchronously decrements the active
  // count before the bubble-phase handler runs — so reading the count there
  // would always see zero. The two-stage pane-Escape uses this to yield to a
  // popover dismissal instead of also blurring the editor.
  const popoverOpenAtEscapeRef = useRef(false);
  useEffect(() => {
    const captureEscape = (e: KeyboardEvent): void => {
      if (e.key === "Escape") popoverOpenAtEscapeRef.current = isAnySuggestionPopoverActive();
    };
    window.addEventListener("keydown", captureEscape, { capture: true });
    return (): void => window.removeEventListener("keydown", captureEscape, { capture: true });
  }, []);

  const keybindingsMap = useAtomValue(keybindingsMapAtom);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      // Ctrl+Alt+/ — toggle the dev panel (not a registry keybinding)
      if (e.ctrlKey && e.altKey && e.key === "/") {
        e.preventDefault();
        toggleDevPanel();
        return;
      }

      // Escape closes chat search (not a registry keybinding)
      if (e.key === "Escape" && isChatSearchVisibleRef.current) {
        if (isDismissibleOverlayOpen()) {
          return;
        }
        e.preventDefault();
        setChatSearchVisible(false);
        return;
      }

      // Escape restores a maximized panel (not a registry keybinding). Runs
      // after chat search so an open search bar inside a maximized panel is
      // dismissed first.
      if (e.key === "Escape" && maximizedZoneRef.current !== null) {
        if (isDismissibleOverlayOpen()) {
          return;
        }
        e.preventDefault();
        restoreMaximizedPanel();
        return;
      }

      // Escape clears the active-pane ring (and steps focus out of any widget
      // inside that pane), in a single press. Only acts while the ring is showing.
      //
      // Yielding: normally we defer to any widget that already handled Escape
      // (`defaultPrevented`) so component-level Escape (path autocomplete, a
      // terminal sending ESC to its shell, an inline rename cancel) wins. The
      // chat editor is the exception — TipTap swallows Escape with a no-op
      // `preventDefault` even when it has nothing to dismiss, so for the chat
      // input we bypass that guard (but still defer while a mention/skill popover
      // is open, whose own Escape closes it). Terminals are excluded outright.
      if (e.key === "Escape" && !isDismissibleOverlayOpen() && focusedZoneRef.current !== null) {
        const active = document.activeElement as HTMLElement | null;
        const isInChatInput = active?.closest(`#${CHAT_INPUT_ELEMENT_ID}`) != null && !popoverOpenAtEscapeRef.current;
        const isHandledByWidget = e.defaultPrevented && !isInChatInput;
        if (!isHandledByWidget && active?.closest(".xterm") == null) {
          e.preventDefault();
          // Defocus a widget inside the pane (e.g. the chat input), then clear
          // the ring.
          const zoneEl = active?.closest<HTMLElement>("[data-zone-id]") ?? null;
          if (active && zoneEl && active !== zoneEl) active.blur();
          setFocusedZone(null);
          return;
        }
      }

      // Cmd+W / Ctrl+W: when an overlay is open, close it instead of
      // letting Electron close the window.
      if ((e.metaKey || e.ctrlKey) && e.key === "w" && isDismissibleOverlayOpen()) {
        e.preventDefault();
        document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
        return;
      }

      // The command palette toggle is the one keybinding that's allowed to
      // fire WHILE the palette overlay is open — it's the canonical "close
      // the thing I just opened" gesture. We special-case it here before
      // the general overlay-suppression rule below.
      //
      // INVARIANT: no Cmd+K command in the registry may claim
      // `shortcut: "command_palette"`. The in-palette window listener
      // (capture phase) intercepts shortcut matches against visible
      // commands, so if any command ever claimed it, Cmd+K would fire
      // that command instead of closing the palette and this branch
      // would never run. Guarded by a unit test in
      // `__tests__/builtinCommands.test.ts` ("no builtin command claims
      // the `command_palette` keybinding as its own shortcut").
      const commandPaletteBinding = keybindingsMap["command_palette"]?.binding;
      const isCommandPaletteShortcut =
        commandPaletteBinding != null && shouldHandleKeybinding(e, commandPaletteBinding);
      if (isCommandPaletteShortcut && isCommandPaletteOpen) {
        e.preventDefault();
        closeCommandPalette();
        return;
      }

      // All keybindings are suppressed when a dismissible overlay is open.
      // We still preventDefault for combos that match a registered keybinding
      // so the browser/Electron does not apply its own default handling
      // (e.g. Cmd+T opening a new tab) which can interfere with overlay
      // event handling (such as Escape to dismiss).
      if (isDismissibleOverlayOpen()) {
        for (const id of Object.keys(keybindingsMap) as Array<KeybindingId>) {
          const binding = keybindingsMap[id].binding;
          if (binding != null && shouldHandleKeybinding(e, binding)) {
            e.preventDefault();
            break;
          }
        }
        return;
      }

      // Workspace-only keybindings (zen/focus mode, panel toggles) should
      // not fire on non-workspace pages like Settings or Home.
      const isOnWorkspacePage = /^#\/ws\/(?!new\b)/.test(window.location.hash);

      const handlers: Array<[KeybindingId, () => void]> = [
        ["command_palette", (): void => toggleCommandPalette()],
        ["help", (): void => toggleHelpDialog()],
        [
          "chat_search",
          (): void => {
            // Only activate when a chat panel is on screen
            const hasChatPanel = document.querySelector(`[data-testid="${ElementIds.CHAT_PANEL}"]`) !== null;
            if (!hasChatPanel) return;
            setChatSearchVisible(true);
            setFocusRequest((n: number): number => n + 1);
          },
        ],
        [
          "focus_input",
          (): void => {
            // Try workspace name input first (Add Workspace page)
            const nameInput = document.querySelector<HTMLElement>(`[data-testid="${ElementIds.WORKSPACE_NAME_INPUT}"]`);
            if (nameInput) {
              nameInput.focus();
              return;
            }
            // Fall back to the chat input (workspace pages)
            const chatInput = document.getElementById(CHAT_INPUT_ELEMENT_ID);
            const editable = chatInput?.querySelector<HTMLElement>("[contenteditable='true']");
            if (editable) {
              editable.focus();
            }
          },
        ],
        [
          "new_workspace",
          (): void => {
            if (isCommandPaletteOpen) {
              closeCommandPalette();
            }
            navigateToAddWorkspace();
          },
        ],
        [
          // Cmd+P: jump straight into the workspace switcher. Opens the
          // palette and lands on the `workspaces.switch` sub-page in one
          // gesture so the user can start typing the workspace name
          // immediately. When the palette is already open the in-palette
          // keybinding interceptor (capture phase) handles it via the
          // same shortcut on the workspaces.switch command and we never
          // get here.
          "open_workspace",
          (): void => openCommandPaletteTo("workspaces.switch"),
        ],
        ["home", (): void => navigateToHome()],
        ["settings", (): void => openSettings()],
        [
          "toggle_theme",
          (): void => {
            const newTheme = resolvedTheme === "dark" ? "light" : "dark";
            setThemeSettings((prev) => ({ ...prev, appearance: newTheme }));
          },
        ],
        [
          "toggle_tool_density",
          (): void => {
            // Same chat-panel gate as `chat_search` — the density toggle
            // only makes sense where tool calls render.
            const hasChatPanel = document.querySelector(`[data-testid="${ElementIds.CHAT_PANEL}"]`) !== null;
            if (!hasChatPanel) return;
            setChatToolDensity((prev) => (prev === "expanded" ? "default" : "expanded"));
          },
        ],
        ...(isOnWorkspacePage
          ? ([
              ["zen_mode", (): void => toggleZenMode()],
              ["focus_mode", (): void => toggleFocusMode()],
              ["maximize_panel", (): void => toggleMaximizeFocused()],
              ["toggle_left_panel", (): void => toggleLeftPanel()],
              ["toggle_bottom_panel", (): void => toggleBottomPanel()],
              ["toggle_right_panel", (): void => toggleRightPanel()],
            ] as Array<[KeybindingId, () => void]>)
          : []),
      ];

      for (const [id, handler] of handlers) {
        const binding = keybindingsMap[id].binding;
        if (binding == null) continue;
        if (shouldHandleKeybinding(e, binding)) {
          e.preventDefault();
          handler();
          return;
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return (): void => window.removeEventListener("keydown", handleKeyDown);
  }, [
    setChatSearchVisible,
    setFocusRequest,
    closeCommandPalette,
    isCommandPaletteOpen,
    toggleDevPanel,
    toggleCommandPalette,
    openCommandPaletteTo,
    navigateToAddWorkspace,
    navigateToHome,
    openSettings,
    toggleHelpDialog,
    keybindingsMap,
    resolvedTheme,
    setThemeSettings,
    setChatToolDensity,
    toggleFocusMode,
    toggleZenMode,
    toggleMaximizeFocused,
    restoreMaximizedPanel,
    toggleLeftPanel,
    toggleBottomPanel,
    toggleRightPanel,
    setFocusedZone,
  ]);
};
