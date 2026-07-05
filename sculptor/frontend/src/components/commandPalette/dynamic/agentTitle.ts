// Cap palette rows at a fixed width; longer titles are truncated with an
// ellipsis so the ellipsis budget stays inside the cap.
const MAX_TITLE_LENGTH = 80;
const ELLIPSIS = "...";

/**
 * Shared display-title derivation for agent rows in the command palette.
 * Used by both the agent navigation and agent-actions providers so the
 * truncation rule (and its cap) stays in one place.
 */
export const taskDisplayTitle = (task: { title?: string | null; initialPrompt: string }): string => {
  const display = task.title?.trim() || task.initialPrompt.trim() || "Untitled agent";
  return display.length > MAX_TITLE_LENGTH
    ? `${display.slice(0, MAX_TITLE_LENGTH - ELLIPSIS.length)}${ELLIPSIS}`
    : display;
};
