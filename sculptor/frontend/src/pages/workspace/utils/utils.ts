/**
 * Extract plain text content from an HTML string, stripping all tags and attributes.
 *
 * TipTap serializes Mention nodes as HTML `<span>` elements. This helper converts
 * such strings to the visible text the user would expect when copying a message.
 */
export const stripHtml = (html: string): string => {
  const doc = new DOMParser().parseFromString(html, "text/html");
  return doc.body.textContent ?? "";
};

export const DIFF_TOOLS = ["Edit", "MultiEdit", "Write"] as const;
type DiffTool = (typeof DIFF_TOOLS)[number];

export const isDiffTool = (toolName: string): toolName is DiffTool => {
  return DIFF_TOOLS.includes(toolName as DiffTool);
};

export const formatSubagentType = (subagentType: string | undefined): string => {
  if (!subagentType) return "Subagent";
  return subagentType.charAt(0).toUpperCase() + subagentType.slice(1) + " subagent";
};

export const isEnterPlanModeTool = (toolName: string): boolean => {
  return toolName === "EnterPlanMode";
};

/** Tools that should be hidden from the alpha chat UI (still visible in debug view). */
const HIDDEN_TOOL_NAMES = new Set(["TaskList", "TaskGet", "TaskOutput", "TaskStop"]);

export const isHiddenTool = (toolName: string): boolean => HIDDEN_TOOL_NAMES.has(toolName);
