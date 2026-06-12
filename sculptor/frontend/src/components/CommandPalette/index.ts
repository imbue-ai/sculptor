export { CommandPalette } from "./CommandPalette.tsx";
export { useCommandPalette, useRegisterCommands, useRegisterDynamicCommands } from "./hooks.ts";
export { CommandRegistry, commandRegistry } from "./registry.ts";
export { CommandRegistryProvider, useCommandRegistry } from "./registryContext.tsx";
export type {
  Command,
  CommandGroupId,
  CommandIcon,
  CommandId,
  DynamicProvider,
  PageId,
  PaletteContext,
} from "./types.ts";
