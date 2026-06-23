import type { CSSProperties } from "react";

/**
 * Pill styling for an inline `<Code>` chip in settings copy — a subtle gray
 * background so file paths and code tokens (e.g. `~/.sculptor/plugins`, `.env`)
 * stand out from the surrounding prose. Shared so every settings section renders
 * these the same way. Lives in its own (non-component) module so re-exporting it
 * doesn't trip the react-refresh "components only" rule.
 */
export const inlineCodeStyle: CSSProperties = {
  backgroundColor: "var(--gray-4)",
  borderRadius: "var(--radius-1)",
  padding: "0.2em 0.4em",
};
