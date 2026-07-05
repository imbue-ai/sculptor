import type { Command, CommandId, DynamicProvider, PaletteContext } from "../types/commandPalette.ts";
import { pagesOf } from "../types/commandPalette.ts";
import { PAGE_DEFINITIONS } from "./pages.ts";

type Listener = () => void;

/**
 * Keeps commands as plain data — no React, no JSX — so the palette can render
 * at any time without retaining stale closures. Commands are added via
 * `register` (with an unregister return value) or `registerMany`. Dynamic
 * providers produce commands at open-time only and never persist between
 * sessions.
 *
 * One instance is exported as the default `commandRegistry` for production;
 * tests instantiate `new CommandRegistry()` directly to get isolated state.
 * Components should read the registry via the `useCommandRegistry()` hook
 * (see `registryContext.tsx`) rather than importing the singleton.
 */
export class CommandRegistry {
  private commands = new Map<CommandId, Command>();
  private providers = new Map<string, DynamicProvider>();
  private listeners = new Set<Listener>();
  private erroredWhenIds = new Set<CommandId>();
  private warnedCollisionIds = new Set<CommandId>();
  /**
   * Shortcut ids we have already emitted a collision warning for, so each
   * clashing keybinding hint warns at most once. Populated lazily during
   * `list()` because that's where dynamic-provider commands appear.
   */
  private warnedShortcutIds = new Set<string>();

  register(command: Command): () => void {
    if (this.commands.has(command.id)) {
      console.warn(`[command-palette] duplicate registration for "${command.id}"`);
    }
    this.commands.set(command.id, command);
    this.notify();
    return (): void => this.unregister(command.id);
  }

  registerMany(commands: ReadonlyArray<Command>): () => void {
    const ids: Array<CommandId> = [];
    for (const cmd of commands) {
      if (this.commands.has(cmd.id)) {
        console.warn(`[command-palette] duplicate registration for "${cmd.id}"`);
      }
      this.commands.set(cmd.id, cmd);
      ids.push(cmd.id);
    }
    this.notify();
    return (): void => {
      for (const id of ids) {
        this.commands.delete(id);
        this.erroredWhenIds.delete(id);
      }
      this.notify();
    };
  }

  unregister(id: CommandId): void {
    if (this.commands.delete(id)) {
      this.erroredWhenIds.delete(id);
      this.notify();
    }
  }

  registerProvider(provider: DynamicProvider): () => void {
    if (this.providers.has(provider.id)) {
      console.warn(`[command-palette] duplicate provider "${provider.id}"`);
    }
    this.providers.set(provider.id, provider);
    this.notify();
    return (): void => {
      if (this.providers.delete(provider.id)) {
        this.notify();
      }
    };
  }

  byId(id: CommandId): Command | undefined {
    return this.commands.get(id);
  }

  /**
   * Returns the visible commands for the given context, with `when` and
   * `onPage` predicates applied. Commands from dynamic providers are
   * appended; later registrations win on id collisions.
   *
   * When `includeAllPages` is set (used for fuzzy search at the root),
   * commands scoped to a sub-page are also included so users can land on
   * sub-page items by typing from the root. Pages whose
   * `hideFromRootSearch` flag is set in `PAGE_DEFINITIONS` are still
   * excluded — they are intermediate steps whose contents duplicate
   * other pages.
   */
  list(ctx: PaletteContext, opts?: { includeAllPages?: boolean }): Array<Command> {
    const merged = new Map<CommandId, Command>(this.commands);

    for (const provider of this.providers.values()) {
      let produced: Array<Command> = [];
      try {
        produced = provider.produce(ctx);
      } catch (err) {
        console.error(`[command-palette] provider "${provider.id}" threw`, err);
        continue;
      }

      for (const cmd of produced) {
        if (this.commands.has(cmd.id) && !this.warnedCollisionIds.has(cmd.id)) {
          this.warnedCollisionIds.add(cmd.id);
          console.warn(`[command-palette] provider "${provider.id}" shadows static command "${cmd.id}"`);
        }
        merged.set(cmd.id, cmd);
      }
    }

    const isIncludingAllPagesAtRoot = opts?.includeAllPages === true && ctx.page == null;

    // Shortcut collision detection — done here so both static and dynamic
    // commands are covered. Warns once per shortcut, and only in dev (the
    // user-visible behavior is undefined: the first match wins in the
    // window keydown listener).
    if (process.env.NODE_ENV !== "production") {
      const shortcutOwners = new Map<string, CommandId>();
      for (const cmd of merged.values()) {
        if (!cmd.shortcut) continue;
        const owner = shortcutOwners.get(cmd.shortcut);
        if (owner != null && owner !== cmd.id && !this.warnedShortcutIds.has(cmd.shortcut)) {
          this.warnedShortcutIds.add(cmd.shortcut);
          console.warn(
            `[command-palette] shortcut "${cmd.shortcut}" claimed by both "${owner}" and "${cmd.id}" — first match wins`,
          );
        }
        shortcutOwners.set(cmd.shortcut, cmd.id);
      }
    }

    const out: Array<Command> = [];
    for (const cmd of merged.values()) {
      const pagesArr = pagesOf(cmd);
      const doesMatchPage = pagesArr === null ? ctx.page === null : ctx.page != null && pagesArr.includes(ctx.page);
      const isRevealedAtRoot =
        isIncludingAllPagesAtRoot &&
        pagesArr !== null &&
        pagesArr.some((p) => PAGE_DEFINITIONS[p]?.hideFromRootSearch !== true);
      if (!doesMatchPage && !isRevealedAtRoot) continue;
      if (cmd.when) {
        try {
          if (!cmd.when(ctx)) continue;
        } catch (err) {
          if (!this.erroredWhenIds.has(cmd.id)) {
            this.erroredWhenIds.add(cmd.id);
            console.error(`[command-palette] when() threw for "${cmd.id}"`, err);
          }
          continue;
        }
      }
      out.push(cmd);
    }
    return out;
  }

  /** Visible for tests. */
  reset(): void {
    this.commands.clear();
    this.providers.clear();
    this.erroredWhenIds.clear();
    this.warnedCollisionIds.clear();
    this.warnedShortcutIds.clear();
    this.notify();
  }

  /** Visible for tests / debugging. */
  size(): number {
    return this.commands.size;
  }

  /** Subscribe to registry changes; primarily used by Jotai integration. */
  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return (): void => {
      this.listeners.delete(listener);
    };
  }

  private notify(): void {
    for (const l of this.listeners) {
      try {
        l();
      } catch (err) {
        console.error("[command-palette] listener threw", err);
      }
    }
  }
}

export const commandRegistry = new CommandRegistry();
