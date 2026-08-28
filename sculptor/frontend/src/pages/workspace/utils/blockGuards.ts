import type {
  ContextClearedBlock,
  ContextSummaryBlock,
  DiffToolContent,
  ErrorBlock,
  FileBlock,
  GenericToolContent,
  GetWorkspaceAgentArtifactResponse,
  ResumeResponseBlock,
  TaskListArtifact,
  TextBlock,
  ToolResultBlock,
  ToolUseBlock,
  WarningBlock,
} from "~/api";

// Artifact type guards
export const isTaskListArtifact = (response: GetWorkspaceAgentArtifactResponse): response is TaskListArtifact => {
  return response.objectType === "TaskListArtifact";
};

export type BlockUnion =
  | TextBlock
  | ToolUseBlock
  | ToolResultBlock
  | ErrorBlock
  | WarningBlock
  | ContextSummaryBlock
  | ContextClearedBlock
  | ResumeResponseBlock
  | FileBlock;

// Content block type guards
export const isTextBlock = (content: BlockUnion): content is TextBlock => {
  return content.type === "text";
};

export const isToolUseBlock = (content: BlockUnion): content is ToolUseBlock => {
  return content.type === "tool_use";
};

export const isToolResultBlock = (content: BlockUnion): content is ToolResultBlock => {
  return content.type === "tool_result";
};

export const isErrorBlock = (content: BlockUnion): content is ErrorBlock => {
  return content.type === "error";
};

export const isWarningBlock = (content: BlockUnion): content is WarningBlock => {
  return content.type === "warning";
};

export const isContextSummaryBlock = (content: BlockUnion): content is ContextSummaryBlock => {
  return content.type === "context_summary";
};

export const isContextClearedBlock = (content: BlockUnion): content is ContextClearedBlock => {
  return content.type === "context_cleared";
};

export const isResumeResponseBlock = (content: BlockUnion): content is ResumeResponseBlock => {
  return content.type === "resume_response";
};

export const isFileBlock = (content: BlockUnion): content is FileBlock => {
  return content.type === "file";
};

// Tool result content type guards

export const isGenericToolContent = (content: GenericToolContent | DiffToolContent): content is GenericToolContent => {
  return content.contentType === "generic";
};

export const isDiffToolContent = (content: GenericToolContent | DiffToolContent): content is DiffToolContent => {
  return content.contentType === "diff";
};
