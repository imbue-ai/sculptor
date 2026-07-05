import { atomWithStorage } from "jotai/utils";

export type ChatToolDensity = "default" | "expanded";

/**
 * Controls how tool calls render inside chat. "default" keeps the
 * comma-separated horizontal pill row; "expanded" lays one row per call,
 * with the same content the popover header would show inlined on the row.
 * Persists to localStorage so the choice survives reload.
 */
export const chatToolDensityAtom = atomWithStorage<ChatToolDensity>("chat.toolDensity", "default");

/**
 * Remembers whether the agent-tasks popover should open with the dependency
 * graph already toggled on. Persists across popover open/close cycles, agent
 * switches, and reloads.
 */
export const agentTasksGraphOpenAtom = atomWithStorage<boolean>("chat.agentTasksGraphOpen", false);
