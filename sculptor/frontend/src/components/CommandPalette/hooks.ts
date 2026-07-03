import { atom, useAtom, useAtomValue, useSetAtom } from "jotai";
import { posthog } from "posthog-js";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useSyncExternalStore } from "react";

import { useImbueLocation } from "~/common/NavigateUtils.ts";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { effectiveOpenTabIdsAtom, workspacesArrayAtom } from "~/common/state/atoms/workspaces.ts";
import { recentAgentTypeAtom } from "~/components/sections/addPanelCore.ts";
import { panelRegistryAtom } from "~/components/sections/registry/panelRegistry.ts";
import { workspaceLayoutAtom } from "~/components/sections/sectionAtoms.ts";
import { maximizedSectionAtom } from "~/components/sections/transientAtoms.ts";
import { chatPanelMountedAtom, terminalPanelMountedAtom } from "~/pages/workspace/atoms.ts";

import { areGlobalShortcutsDisabledAtom } from "../newWorkspace/newWorkspaceAtoms.ts";
import {
  commandPaletteInitialPageAtom,
  commandPaletteOpenAtom,
  commandPalettePagesAtom,
  commandPalettePendingAtom,
  commandPaletteSearchAtom,
} from "./atoms.ts";
import {
  addPanelTargetSubSectionAtom,
  agentActionsTargetAtom,
  workspaceActionsTargetAtom,
} from "./contextActions/atoms.ts";
import { isValidPageId, popPageStack, pushPageStack } from "./pages.ts";
import { useCommandRegistry } from "./registryContext.tsx";
import type { Command, DynamicProvider, PageId, PaletteContext } from "./types.ts";

/**
 * Hard cap for how long a command's `perform` can hold the palette in
 * `pending` state. After this, we release pending and let the user close
 * the palette; the underlying perform may still complete in the background.
 * Most commands finish in <100ms and async ones
 * (like `updateField` for experimental flags) typically finish in <2s.
 */
const COMMAND_TIMEOUT_MS = 30_000;

/**
 * Build the palette context. Re-runs whenever the React Router location
 * changes (`useImbueLocation` re-renders consumers on every navigation),
 * the section-maximize atom changes, the chat panel mounts/unmounts, or the page
 * stack changes. Each ctx field is keyed on a primitive so the returned
 * object is reference-stable across unrelated renders.
 */
export const usePaletteContext = (): PaletteContext => {
  const loc = useImbueLocation();
  // Reactive read: the panel components maintain these mount counters on
  // mount/unmount, so this updates without poking the DOM. `> 0` means at
  // least one such panel is currently mounted.
  const hasChatPanel = useAtomValue(chatPanelMountedAtom) > 0;
  const hasTerminalPanel = useAtomValue(terminalPanelMountedAtom) > 0;
  const isSectionMaximized = useAtomValue(maximizedSectionAtom) !== null;
  const pages = useAtomValue(commandPalettePagesAtom);
  const page = pages.length === 0 ? null : (pages[pages.length - 1] ?? null);

  // Route-derived ids (and workspace/agent flags) come from React Router via
  // `useImbueLocation`, not from regexing `window.location.hash`.
  const isWorkspace = loc.isWorkspaceRoute;
  const activeWorkspaceId = loc.workspaceId;
  const activeAgentId = loc.agentId;

  return useMemo(
    () => ({
      route: {
        isHome: loc.isHomeRoute,
        isWorkspace,
        isSettings: loc.isSettingsRoute,
        isAgent: loc.isAgentRoute,
      },
      activeWorkspaceId,
      activeAgentId,
      hasChatPanel,
      hasTerminalPanel,
      isSectionMaximized,
      page,
    }),
    [
      loc.isHomeRoute,
      loc.isSettingsRoute,
      loc.isAgentRoute,
      isWorkspace,
      activeWorkspaceId,
      activeAgentId,
      hasChatPanel,
      hasTerminalPanel,
      isSectionMaximized,
      page,
    ],
  );
};

/** UI controls for the palette. Stable identities. */
export const useCommandPalette = (): {
  isOpen: boolean;
  open: () => void;
  /**
   * Open the palette and land directly on a sub-page (e.g.
   * `openTo("workspaces.switch")` from the Cmd+P keybinding). The
   * sub-page is delivered via `commandPaletteInitialPageAtom` so the
   * open-side of the reset effect doesn't clobber the page stack.
   */
  openTo: (pageId: PageId) => void;
  close: () => void;
  toggle: () => void;
  pushPage: (pageId: PageId) => void;
  popPage: () => void;
} => {
  const [isOpen, setIsOpen] = useAtom(commandPaletteOpenAtom);
  const setSearch = useSetAtom(commandPaletteSearchAtom);
  const setPages = useSetAtom(commandPalettePagesAtom);
  const setInitialPage = useSetAtom(commandPaletteInitialPageAtom);
  // The palette is unreachable in the empty first-run state. Gate the
  // open paths here (rather than only at the keyboard hook) so every entry —
  // the sidebar Search button, deep links, commands that re-open it — is
  // covered by one rule. `close`/`toggle` never get stuck open because opening
  // is blocked in the first place.
  const areGlobalShortcutsDisabled = useAtomValue(areGlobalShortcutsDisabledAtom);

  // open/close just flip `isOpen`. The reset of search / page stack /
  // context-action targets is owned exclusively by `useResetOnOpenChange`
  // (mounted inside `<CommandPalette>`), which fires on both the rising
  // and falling edges. That keeps a single writer to those atoms and
  // ensures raw `setIsOpen(...)` callers (tests, deep links) get the
  // same reset behavior.
  const open = useCallback(() => {
    if (areGlobalShortcutsDisabled) return;
    setIsOpen(true);
  }, [areGlobalShortcutsDisabled, setIsOpen]);

  const openTo = useCallback(
    (pageId: PageId) => {
      if (areGlobalShortcutsDisabled) return;
      if (!isValidPageId(pageId)) {
        console.error(`[command-palette] openTo: unknown page id "${pageId}" — opening at root`);
        setIsOpen(true);
        return;
      }
      // Stash the initial page BEFORE flipping isOpen so the reset
      // effect can read it on the same commit.
      setInitialPage(pageId);
      setIsOpen(true);
    },
    [areGlobalShortcutsDisabled, setInitialPage, setIsOpen],
  );

  const close = useCallback(() => {
    setIsOpen(false);
  }, [setIsOpen]);

  const toggle = useCallback(() => {
    if (areGlobalShortcutsDisabled) return;
    setIsOpen((prev) => !prev);
  }, [areGlobalShortcutsDisabled, setIsOpen]);

  const pushPage = useCallback(
    (pageId: PageId) => {
      setSearch("");
      setPages((prev) => pushPageStack(prev, pageId));
    },
    [setPages, setSearch],
  );

  const popPage = useCallback(() => {
    setSearch("");
    setPages((prev) => popPageStack(prev));
  }, [setPages, setSearch]);

  return { isOpen, open, openTo, close, toggle, pushPage, popPage };
};

/**
 * Register an array of commands for the lifetime of the calling component.
 * The effect re-runs whenever the `commands` array identity changes —
 * callers should memoize the array (or build it from `useMemo`) so we
 * don't churn the registry on every render.
 */
export const useRegisterCommands = (commands: ReadonlyArray<Command>): void => {
  const registry = useCommandRegistry();
  useEffect(() => {
    return registry.registerMany(commands);
  }, [registry, commands]);
};

export const useRegisterDynamicCommands = (provider: DynamicProvider): void => {
  const registry = useCommandRegistry();
  useEffect(() => {
    const unregister = registry.registerProvider(provider);
    return unregister;
  }, [registry, provider]);
};

/**
 * Subscribe to registry mutations so the palette re-renders when dynamic
 * registrations land mid-session. Returns the registry size (a stand-in
 * snapshot) — what we actually care about is that the value changes when
 * the registry mutates, so that downstream `useMemo` recomputes.
 */
const useRegistrySize = (): number => {
  const registry = useCommandRegistry();
  return useSyncExternalStore(
    (cb) => registry.subscribe(cb),
    () => registry.size(),
    () => registry.size(),
  );
};

/**
 * The atoms that dynamic providers (and their action runtimes) read
 * imperatively via `runtime.store.get(atom)` inside `produce()`, bundled into
 * one derived value and gated on the palette being open.
 *
 * Two jobs:
 *  - While OPEN, the bundle's identity changes whenever any input changes,
 *    which forces the visible-set memo to recompute and re-invoke every
 *    provider's `produce`. Without these subscriptions, providers would see
 *    stale data after the user edits state outside the palette (e.g. closing
 *    a tab while the palette is open would leave "Close others" stale until
 *    the palette reopens).
 *  - While CLOSED, the read function returns before touching any input, so
 *    the only tracked dependency is `commandPaletteOpenAtom`. The palette
 *    host stays mounted for the whole session and several inputs churn
 *    constantly (every task streaming tick rebuilds `tasksArrayAtom`, every
 *    layout write bumps `workspaceLayoutAtom`) — the gate keeps that churn
 *    from re-rendering the host. First-open contents stay correct because
 *    the open transition itself recomputes this atom from current state.
 *
 * INVARIANT: any atom a dynamic provider or its action runtime reads through
 * `runtime.store.get(...)` MUST appear here. The static builtin commands
 * don't need this — their `when` predicates already re-evaluate on every
 * `ctx` change inside `registry.list()`.
 */
const dynamicProviderInputsAtom = atom((get) => {
  if (!get(commandPaletteOpenAtom)) {
    return null;
  }
  return {
    workspaces: get(workspacesArrayAtom),
    tasks: get(tasksArrayAtom),
    openTabIds: get(effectiveOpenTabIdsAtom),
    panelRegistry: get(panelRegistryAtom),
    // The panel-toggle provider reads the layout's placement to list only
    // actively-placed panels; the add-panel location page reads it via
    // listAvailableLocations.
    workspaceLayout: get(workspaceLayoutAtom),
    // The add-panel provider reads this to build the panel page for the
    // chosen section; without it, picking a section wouldn't recompute the
    // list and the panel page would show "No commands here".
    addPanelTarget: get(addPanelTargetSubSectionAtom),
    // The add-panel provider builds the "New {recent} agent" row title from the
    // normalized last-used agent type; tracking it keeps that title in sync when a
    // userConfig frame or the pi flag lands while the palette is open.
    recentAgentType: get(recentAgentTypeAtom),
  };
});

/**
 * The list of visible commands for the current ctx, with `when` and
 * `onPage` already applied. Sorting + grouping is done in the component.
 *
 * While the palette is closed, the dynamic-provider inputs are not
 * subscribed at all (see `dynamicProviderInputsAtom`) and the memo
 * short-circuits, so the always-mounted host neither re-renders on
 * unrelated state churn nor pays the `commandRegistry.list()` cost.
 */
export const useVisibleCommands = (ctx: PaletteContext): Array<Command> => {
  const registry = useCommandRegistry();
  const isOpen = useAtomValue(commandPaletteOpenAtom);
  const search = useAtomValue(commandPaletteSearchAtom);
  const size = useRegistrySize();
  const dynamicInputs = useAtomValue(dynamicProviderInputsAtom);
  const hasQuery = search.trim().length > 0;
  return useMemo(() => {
    if (!isOpen) return [];
    // Tripwire reads — referenced so React tracks them as deps without
    // ESLint flagging them as unused. The actual data is consumed by
    // dynamic providers via `runtime.store.get(...)`.
    void size;
    void dynamicInputs;
    // While the user is typing at the root, surface page-scoped commands
    // too so fuzzy search can land them on sub-page items directly.
    return registry.list(ctx, { includeAllPages: hasQuery });
  }, [registry, isOpen, ctx, hasQuery, size, dynamicInputs]);
};

/**
 * Run a command:
 *  - mark pending while async
 *  - close palette unless keepOpen / Cmd+Enter requested
 *  - on error, log and keep palette open
 */
export const useRunCommand = (): ((cmd: Command, opts?: { keepOpen?: boolean }) => Promise<void>) => {
  const ctx = usePaletteContext();
  const { close, pushPage } = useCommandPalette();
  const setPending = useSetAtom(commandPalettePendingAtom);

  return useCallback(
    async (cmd: Command, opts?: { keepOpen?: boolean }) => {
      const start = performance.now();
      const shouldKeepOpen = opts?.keepOpen ?? cmd.keepOpen ?? false;
      const isPageOpener = cmd.pageId != null;

      // Multiple commands in flight can race on `commandPalettePendingAtom`.
      // Only set pending if no other command is in flight, and only clear
      // pending if the in-flight command is OURS (so a faster sibling's
      // finally doesn't clear our spinner).
      setPending((prev) => prev ?? cmd.id);
      let didThrow = false;
      let didTimeOut = false;
      // Hoisted so a synchronous throw before the Promise.race still
      // clears the timer in `finally` — otherwise the timeout fires
      // 30s later on a settled race (no-op visible behavior, but a
      // stray timer holds a reference until then).
      let timeoutHandle: ReturnType<typeof setTimeout> | null = null;
      try {
        if (cmd.pageId) {
          pushPage(cmd.pageId);
        }
        const performPromise = Promise.resolve(cmd.perform({ ctx, keepOpen: shouldKeepOpen, pushPage }));
        let timeoutResolve: (value: "timeout") => void;
        const timeoutPromise = new Promise<"timeout">((resolve) => {
          timeoutResolve = resolve;
        });
        timeoutHandle = setTimeout(() => timeoutResolve("timeout"), COMMAND_TIMEOUT_MS);
        const result = await Promise.race([performPromise.then(() => "ok" as const), timeoutPromise]);
        if (result === "timeout") {
          didTimeOut = true;
          console.warn(
            `[command-palette] "${cmd.id}" did not complete within ${COMMAND_TIMEOUT_MS}ms; releasing pending state. The command may still complete in the background.`,
          );
          // Surface as console.warn until a global toast hook lands; the
          // timeout is non-fatal — the perform may still complete in the
          // background.
        }
      } catch (err) {
        didThrow = true;
        console.error(`[command-palette] "${cmd.id}" threw`, err);
      } finally {
        if (timeoutHandle != null) clearTimeout(timeoutHandle);
        setPending((prev) => (prev === cmd.id ? null : prev));
      }
      const elapsed = performance.now() - start;
      console.debug(`[command-palette] ran "${cmd.id}" in ${elapsed.toFixed(1)}ms`);

      // Telemetry: emit a product-analytics event for actual command runs.
      // Page-opener commands (those that just push a sub-page) are excluded
      // because they're navigation, not "the user ran a command" — emitting
      // for every breadcrumb push would flood downstream dashboards with
      // low-signal events. The `console.debug` above is developer-facing
      // and intentionally separate from this telemetry call.
      //
      // Property names use snake_case to match PostHog conventions and the
      // existing register() shape in `~/common/Telemetry.ts`. Only the
      // command id, group, page, elapsed, and boolean flags are emitted —
      // no PII (no titles, no search query, no workspace/agent ids).
      if (!isPageOpener) {
        posthog.capture("command_palette.command_run", {
          command_id: cmd.id,
          group: cmd.group,
          page: ctx.page,
          keep_open: shouldKeepOpen,
          elapsed_ms: Math.round(elapsed),
          timed_out: didTimeOut,
          threw: didThrow,
        });
      }

      if (!shouldKeepOpen && !isPageOpener) {
        close();
      }
      // keepOpen path: focus restoration is owned by `CommandPalette.tsx`,
      // which watches `commandPalettePendingAtom` and pulls focus back to
      // its own input ref after the perform settles. Keeping the focus
      // logic next to the input ref (rather than querying the DOM here)
      // avoids a `document.querySelector` lookup in this hook.
    },
    [ctx, close, pushPage, setPending],
  );
};

/**
 * Single source of truth for resetting palette state on open/close.
 * Fires on BOTH edges of `commandPaletteOpenAtom`:
 *  - rising edge (false -> true): wipe search, page stack, and context
 *    action targets so the palette opens to a clean state. Catches
 *    `open()`, `toggle()`, and any raw `setIsOpen(true)` (tests, future
 *    deep-link flows).
 *  - falling edge (true -> false): same reset, so the next open also
 *    starts clean even if some other code path closes the palette by
 *    flipping the atom directly.
 *
 * Uses a ref to detect actual transitions so we don't run the reset on
 * every render of the host component.
 *
 * This is the ONLY writer to these atoms for open/close lifecycle. The
 * `open()`/`close()` callbacks on `useCommandPalette` are intentionally
 * just `setIsOpen(true|false)`; the reset rides along via this effect.
 */
export const useResetOnOpenChange = (): void => {
  const isOpen = useAtomValue(commandPaletteOpenAtom);
  const initialPage = useAtomValue(commandPaletteInitialPageAtom);
  const setSearch = useSetAtom(commandPaletteSearchAtom);
  const setPages = useSetAtom(commandPalettePagesAtom);
  const setInitialPage = useSetAtom(commandPaletteInitialPageAtom);
  const setWorkspaceActionsTarget = useSetAtom(workspaceActionsTargetAtom);
  const setAgentActionsTarget = useSetAtom(agentActionsTargetAtom);
  const setAddPanelTarget = useSetAtom(addPanelTargetSubSectionAtom);
  const prevOpenRef = useRef(false);
  // Layout effect (not plain effect) so the reset commits BEFORE paint.
  // A caller that batches `setSearch("x"); setIsOpen(true)` would
  // otherwise flash the stale search text for one frame before this
  // effect cleared it.
  useLayoutEffect(() => {
    const didChange = isOpen !== prevOpenRef.current;
    prevOpenRef.current = isOpen;
    if (didChange) {
      setSearch("");
      // On the rising edge: if a caller stashed an initial page (via
      // `openTo`), seed the page stack with it instead of resetting
      // to []. Always clear the atom so the next open starts fresh.
      // Re-validate on consume (defense-in-depth: `openTo` already
      // checks, but a future direct `setInitialPage(...)` writer must
      // not be able to push an invalid PageId into the stack).
      if (isOpen && initialPage != null) {
        if (isValidPageId(initialPage)) {
          setPages([initialPage]);
        } else {
          console.error(
            `[command-palette] commandPaletteInitialPageAtom holds invalid page id "${initialPage}" — opening at root`,
          );
          setPages([]);
        }
        setInitialPage(null);
      } else {
        setPages([]);
      }
      setWorkspaceActionsTarget(null);
      setAgentActionsTarget(null);
      setAddPanelTarget(null);
    }
  }, [
    isOpen,
    initialPage,
    setSearch,
    setPages,
    setInitialPage,
    setWorkspaceActionsTarget,
    setAgentActionsTarget,
    setAddPanelTarget,
  ]);
};
