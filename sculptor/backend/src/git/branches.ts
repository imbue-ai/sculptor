import type { WorkspaceInitializationStrategy } from "~/db/schema";
import { runProcessToCompletion } from "~/environment/process";

const MAX_SLUG_LENGTH = 20;

// Slugify a workspace name into a kebab-case slug, mirroring
// branch_naming.slugify_workspace_name (python-slugify with max_length=20,
// word_boundary). ASCII-focused: non-alphanumeric runs collapse to "-", and the
// result is truncated on a word boundary to avoid a trailing partial token.
export function slugifyWorkspaceName(name: string): string {
  if (name.trim() === "") {
    return "";
  }
  const base = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  if (base.length <= MAX_SLUG_LENGTH) {
    return base;
  }
  const truncated = base.slice(0, MAX_SLUG_LENGTH);
  const lastDash = truncated.lastIndexOf("-");
  const onBoundary = lastDash > 0 ? truncated.slice(0, lastDash) : truncated;
  return onBoundary.replace(/-+$/g, "");
}

const RANDOM_ADJECTIVES = [
  "brave", "calm", "clever", "eager", "gentle", "happy", "keen", "lively", "merry", "swift",
];
const RANDOM_NOUNS = [
  "otter", "falcon", "maple", "river", "ember", "harbor", "willow", "comet", "meadow", "cedar",
];

function pick(words: string[]): string {
  return words[Math.floor(Math.random() * words.length)]!;
}

// A random `<adjective>-<noun>` slug (UX-quality randomness), mirroring the
// coolname-based generate_random_slug.
export function generateRandomSlug(): string {
  return `${pick(RANDOM_ADJECTIVES)}-${pick(RANDOM_NOUNS)}`;
}

// Substitute <user> and <slug> placeholders, collapsing empty substitutions:
// consecutive `/` reduce to one and a leading `/` is stripped. Mirrors
// branch_naming.resolve_pattern.
export function resolvePattern(pattern: string, userSlug: string, nameSlug: string): string {
  let resolved = pattern.replaceAll("<user>", userSlug).replaceAll("<slug>", nameSlug);
  while (resolved.includes("//")) {
    resolved = resolved.replaceAll("//", "/");
  }
  if (resolved.startsWith("/")) {
    resolved = resolved.slice(1);
  }
  return resolved;
}

const DEFAULT_NAMING_PATTERN = "<user>/<slug>";

export interface PreviewBranchNameParams {
  strategy: WorkspaceInitializationStrategy;
  repoHostPath: string;
  workspaceName: string;
  // Per-project override; falls back to the user-global default pattern.
  namingPattern?: string | null;
  defaultPattern?: string;
}

// Resolves the auto-filled branch-name preview, mirroring web/app.py's
// preview_branch_name: in-place returns "", otherwise the pattern is resolved
// against a name slug (random if empty) and a user slug derived from the repo's
// `git config user.name`.
export async function previewBranchName(params: PreviewBranchNameParams): Promise<string> {
  if (params.strategy === "IN_PLACE") {
    return "";
  }

  const pattern =
    params.namingPattern !== undefined && params.namingPattern !== null && params.namingPattern.trim() !== ""
      ? params.namingPattern
      : (params.defaultPattern ?? DEFAULT_NAMING_PATTERN);

  const nameSlug = slugifyWorkspaceName(params.workspaceName) || generateRandomSlug();

  let userSlug = "";
  const result = await runProcessToCompletion(["git", "config", "user.name"], { cwd: params.repoHostPath });
  if (result.exitCode === 0) {
    const firstToken = result.stdout.trim().split(/\s+/)[0] ?? "";
    userSlug = firstToken !== "" ? slugifyWorkspaceName(firstToken) : "";
  }

  return resolvePattern(pattern, userSlug, nameSlug);
}
