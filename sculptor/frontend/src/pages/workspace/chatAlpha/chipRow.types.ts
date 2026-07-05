import type { ToolResultBlock, ToolUseBlock } from "~/api";

export type ChipState = "executing" | "completed" | "error";

export type ChipData = {
  /** Stable React key — the `id` of the first ToolUseBlock in the group. */
  id: string;
  /** Full file path. */
  filePath: string;
  /** Disambiguated filename for display. */
  displayName: string;
  state: ChipState;
  /** Line-change stats, null when executing or error. */
  stats: { added: number; removed: number } | null;
  /** True when the tool is Write (for "new file" badge). */
  isNewFile: boolean;
  /** The tool_use blocks in this chip. */
  blocks: ReadonlyArray<ToolUseBlock>;
  /** Corresponding results (may be empty if executing). */
  results: ReadonlyArray<ToolResultBlock>;
  /** Parsed error text for error state. */
  errorDetail: string | null;
  /** Whether the error originated from a diff tool or a generic text tool. */
  errorContentType: "diff" | "text" | null;
};

export type Segment =
  | { kind: "chip"; blocks: ReadonlyArray<ToolUseBlock> }
  | { kind: "tools"; blocks: ReadonlyArray<ToolUseBlock | ToolResultBlock> };
