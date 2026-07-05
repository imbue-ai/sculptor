import { useAtomValue, useSetAtom, useStore } from "jotai";
import { useEffect, useRef } from "react";

import { sidebarCollapsedAtom } from "~/pages/workspace/layout/atoms/sidebar.ts";

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
import {
  areGlobalShortcutsDisabledAtom,
  newWorkspaceDialogAtom,
} from "../../components/newWorkspace/newWorkspaceAtoms.ts";
import { chatToolDensityAtom } from "../../pages/workspace/components/chat-alpha/atoms.ts";

export const useGlobalKeyboardShortcuts = (): void => {
  const store = useStore();
  const { toggleDevPanel } = useDevPanel();
  const {
    isOpen: isCommandPaletteOpen,
    close: closeCommandPalette,
    toggle: toggleCommandPalette,
    openTo: openCommandPaletteTo,
  } = useCommandPalette();
  const { toggleHelpDialog } = useHelpDialog();
  const { navigateToHome } = useImbueNavigate();
  const setChatSearchVisible = useSetAtom(chatSearchVisibleAtom);
  const setFocusRequest = useSetAtom(chatSearchFocusRequestAtom);
  const setNewWorkspaceDialog = useSetAtom(newWorkspaceDialogAtom);
  const openSettings = useOpenSettings();

  const resolvedTheme = useResolvedTheme();
  const setThemeSettings = useSetAtom(themeBuilderSettingsAtom);
  const setChatToolDensity = useSetAtom(chatToolDensityAtom);

  const isChatSearchVisible = useAtomValue(chatSearchVisibleAtom);
  const isChatSearchVisibleRef = useRef(isChatSearchVisible);
  useEffect(() => {
    isChatSearchVisibleRef.current = isChatSearchVisible;
  });

  // In the empty first-run state, global shortcuts are off. Read
  // through a ref so the keydown effect doesn't re-subscribe when the flag
  // flips (it reads the latest value at event time instead).
  const areGlobalShortcutsDisabled = useAtomValue(areGlobalShortcutsDisabledAtom);
  const areGlobalShortcutsDisabledRef = useRef(areGlobalShortcutsDisabled);
  useEffect(() => {
    areGlobalShortcutsDisabledRef.current = areGlobalShortcutsDisabled;
  });

  const keybindingsMap = useAtomValue(keybindingsMapAtom);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      // Empty first-run state — only Settings is reachable. Suppress
      // every other global shortcut (including Cmd+K) so the user can't escape
      // the inline form by keyboard. Settings still works so they can reach
      // preferences; it's the one allowed destination per the empty-state spec.
      if (areGlobalShortcutsDisabledRef.current) {
        const settingsBinding = keybindingsMap["settings"]?.binding;
        if (settingsBinding != null && shouldHandleKeybinding(e, settingsBinding)) {
          e.preventDefault();
          openSettings();
        }
        return;
      }

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

      // Cmd+W / Ctrl+W: when an overlay is open, close it instead of letting
      // Electron close the window. Scoped to the bare close_workspace chord
      // (no Shift/Alt): Cmd+Shift+W is delete_workspace and opens the
      // confirmation dialog, so treating it as a close-overlay gesture would
      // dismiss the dialog it just opened.
      if ((e.metaKey || e.ctrlKey) && !e.shiftKey && !e.altKey && e.key === "w" && isDismissibleOverlayOpen()) {
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
            // Open the global new-workspace dialog. Its host (NewWorkspaceDialog)
            // is mounted in AppShell alongside this hook, so wherever this
            // handler runs the dialog can actually render.
            setNewWorkspaceDialog({ open: true });
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
          // The sidebar rail is mounted by AppShell on every route (workspace,
          // Home, Settings), so its toggle lives here — the shell-level hook —
          // rather than in the workspace-only shortcut set. Reads the current
          // value through the store at press time so the listener does not
          // re-subscribe on every toggle.
          "toggle_sidebar",
          (): void => store.set(sidebarCollapsedAtom, !store.get(sidebarCollapsedAtom)),
        ],
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
    store,
    setChatSearchVisible,
    setFocusRequest,
    closeCommandPalette,
    isCommandPaletteOpen,
    toggleDevPanel,
    toggleCommandPalette,
    openCommandPaletteTo,
    setNewWorkspaceDialog,
    navigateToHome,
    openSettings,
    toggleHelpDialog,
    keybindingsMap,
    resolvedTheme,
    setThemeSettings,
    setChatToolDensity,
  ]);
};
