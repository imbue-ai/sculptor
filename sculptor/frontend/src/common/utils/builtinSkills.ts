/**
 * Built-in Claude Code slash commands that appear in autocomplete but are
 * forwarded to the backend (not handled client-side like pseudo-skills).
 */
export const BUILTIN_SKILLS = [
  { name: "batch", description: "Run a prompt or command across multiple files" },
  { name: "compact", description: "Free up context by summarizing the conversation so far" },
  { name: "context", description: "Visualize current context usage" },
  { name: "loop", description: "Run a prompt or slash command on a recurring interval" },
  { name: "simplify", description: "Review changed code for reuse, quality, and efficiency" },
] as const satisfies ReadonlyArray<{
  name: string;
  description: string;
}>;
