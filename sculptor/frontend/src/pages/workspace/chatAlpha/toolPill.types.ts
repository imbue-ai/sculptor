import type { ToolResultBlock, ToolUseBlock } from "~/api";

export type PillState = "initializing" | "completed" | "error";

export type PillData = {
  /** Stable React key — the `id` of the ToolUseBlock (or toolUseId of a result-only block). */
  id: string;
  /** Display label: e.g. "Bash", "Read", "Grep". */
  label: string;
  state: PillState;
  /** All tool_use blocks represented by this pill. */
  blocks: ReadonlyArray<ToolUseBlock>;
  /** Corresponding results (may be empty if executing). */
  results: ReadonlyArray<ToolResultBlock>;
};
