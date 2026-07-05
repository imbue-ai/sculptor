// Predicates over a tool's wire name that the chat UI and file browser share to
// decide how (or whether) to surface a tool call.

const DIFF_TOOLS = ["Edit", "MultiEdit", "Write"] as const;
type DiffTool = (typeof DIFF_TOOLS)[number];

/** True for the file-editing tools whose result carries a diff worth rendering. */
export const isDiffTool = (toolName: string): toolName is DiffTool => {
  return DIFF_TOOLS.includes(toolName as DiffTool);
};

export const isEnterPlanModeTool = (toolName: string): boolean => {
  return toolName === "EnterPlanMode";
};

/** Tools that should be hidden from the alpha chat UI (still visible in debug view). */
const HIDDEN_TOOL_NAMES = new Set(["TaskList", "TaskGet", "TaskOutput", "TaskStop"]);

export const isHiddenTool = (toolName: string): boolean => HIDDEN_TOOL_NAMES.has(toolName);
