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

export const getToolDisplayName = (name: string, contentText?: string): string => {
  if (name === "TaskOutput") return TASK_OUTPUT_DISPLAY[parseBackgroundTaskType(contentText)];
  if (name === "TaskStop") return TASK_STOP_DISPLAY[parseBackgroundTaskType(contentText)];

  const displayNames: Record<string, string> = {
    Read: "Read file",
    LS: "Listed files",
    Bash: "Ran command",
    Monitor: "Watched events",
    TaskCreate: "Added task",
    TaskUpdate: "Updated task",
    Grep: "Searched files",
    Glob: "Found files",
    Edit: "Edited file",
    MultiEdit: "Edited files",
    Write: "Created file",
    WebFetch: "Fetched web content",
    WebSearch: "Searched web",
    NotebookRead: "Read notebook",
    NotebookEdit: "Edited notebook",
    Task: "Ran subagent",
    Agent: "Ran subagent",
    Skill: "Ran skill",
    ExitPlanMode: "Plan review",
    EnterPlanMode: "Entered plan mode",
  };
  return displayNames[name] || name;
};

export const getToolDisplayNamePresent = (name: string): string => {
  const displayNames: Record<string, string> = {
    Read: "Reading file...",
    LS: "Listing files...",
    Bash: "Running command...",
    Monitor: "Watching for events...",
    TaskCreate: "Adding task...",
    TaskUpdate: "Updating task...",
    Grep: "Searching files...",
    Glob: "Finding files...",
    Edit: "Editing file...",
    MultiEdit: "Editing files...",
    Write: "Creating file...",
    WebFetch: "Fetching web content...",
    WebSearch: "Searching web...",
    NotebookRead: "Reading notebook...",
    NotebookEdit: "Editing notebook...",
    TaskOutput: "Reading task output...",
    TaskStop: "Stopping task...",
    Task: "Running subagent...",
    Agent: "Running subagent...",
    Skill: "Running skill...",
    ExitPlanMode: "Reviewing plan...",
    EnterPlanMode: "Entering plan mode...",
  };
  return displayNames[name] || `Running ${name}...`;
};

/** Known task types emitted by Claude Code in TaskOutput / TaskStop results. */
type BackgroundTaskType = "bash" | "agent" | "unknown";

/** Extract the background task type from a TaskOutput / TaskStop result's content text. */
export const parseBackgroundTaskType = (contentText?: string): BackgroundTaskType => {
  if (!contentText) return "unknown";
  if (contentText.includes("<task_type>local_bash</task_type>")) return "bash";
  if (contentText.includes("<task_type>local_agent</task_type>")) return "agent";
  return "unknown";
};

const TASK_OUTPUT_DISPLAY: Record<BackgroundTaskType, string> = {
  bash: "Read command output",
  agent: "Read subagent output",
  unknown: "Read task output",
};

const TASK_STOP_DISPLAY: Record<BackgroundTaskType, string> = {
  bash: "Stopped command",
  agent: "Stopped subagent",
  unknown: "Stopped task",
};
