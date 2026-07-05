export { CommandPalette } from "./CommandPalette.tsx";
export { useCommandPalette, useRegisterCommands, useRegisterDynamicCommands } from "./hooks/useCommandPalette.ts";
export { CommandRegistryProvider, useCommandRegistry } from "./registryContext.tsx";
export type {
  Command,
  CommandGroupId,
  CommandIcon,
  CommandId,
  DynamicProvider,
  PageId,
  PaletteContext,
} from "./types/commandPalette.ts";
export { CommandRegistry, commandRegistry } from "./utils/registry.ts";
