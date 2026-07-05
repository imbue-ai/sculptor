import { createContext, type ReactElement, type ReactNode, useContext } from "react";

import type { CommandRegistry } from "./utils/registry.ts";
import { commandRegistry as defaultCommandRegistry } from "./utils/registry.ts";

/**
 * React Context for the command registry. The default value is the
 * module-level `commandRegistry` singleton, so production code that
 * doesn't wrap in a provider keeps working. Tests opt-in to an isolated
 * registry by wrapping the tree in `<CommandRegistryProvider value={...} />`.
 */
const CommandRegistryContext = createContext<CommandRegistry>(defaultCommandRegistry);

export const CommandRegistryProvider = ({
  value,
  children,
}: {
  value: CommandRegistry;
  children: ReactNode;
}): ReactElement => <CommandRegistryContext.Provider value={value}>{children}</CommandRegistryContext.Provider>;

/**
 * Read the active registry. Components should use this rather than
 * importing `commandRegistry` directly so a wrapping provider can swap
 * the registry — primarily for tests, but the seam also keeps the door
 * open to per-route registries in the future.
 */
// eslint-disable-next-line react-refresh/only-export-components -- hook must live alongside its context
export const useCommandRegistry = (): CommandRegistry => useContext(CommandRegistryContext);
