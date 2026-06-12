import type { ChatMessage } from "~/api";

/**
 * Extract plain text from a message's content blocks.
 * Joins all text blocks into a single string.
 */
export const getPlainText = (message: ChatMessage): string =>
  message.content
    .filter((block) => block.type === "text")
    .map((block) => ("text" in block ? block.text : ""))
    .join("");

/**
 * Summarize tool_use blocks as "ToolName(id: tool_id)" strings.
 */
export const getToolUseSummary = (message: ChatMessage): ReadonlyArray<string> =>
  message.content
    .filter((block) => block.type === "tool_use")
    .map((block) => {
      const name = "name" in block ? block.name : "unknown";
      const id = "id" in block ? block.id : "?";
      return `${name}(id: ${id})`;
    });

/**
 * Summarize tool_result blocks as "ToolName (toolUseId: id)" strings.
 */
export const getToolResultSummary = (message: ChatMessage): ReadonlyArray<string> =>
  message.content
    .filter((block) => block.type === "tool_result")
    .map((block) => {
      const toolUseId = "toolUseId" in block ? block.toolUseId : "?";
      const toolName = "toolName" in block ? block.toolName : "unknown";
      return `${toolName} (toolUseId: ${toolUseId})`;
    });
