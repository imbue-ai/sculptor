// Frontend-side check for the structural rules `git check-ref-format`
// applies on top of character sanitization in BranchNameField. Returns
// a short user-facing message, or null when the name is acceptable.
// Empty input is treated as valid here — the parent decides whether
// emptiness is a hard error (worktree) or fine (clone).
export const validateBranchName = (value: string): string | null => {
  if (value === "") return null;
  if (value.startsWith("/") || value.startsWith(".")) return "Cannot start with / or .";
  if (value.endsWith("/") || value.endsWith(".") || value.endsWith(".lock")) return "Cannot end with /, ., or .lock";
  if (value.includes("..") || value.includes("//") || value.includes("@{")) return "Cannot contain .., //, or @{";
  if (value === "@") return "Cannot be @";
  return null;
};
