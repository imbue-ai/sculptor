import type { LinearIssue } from "./client.ts";

/**
 * User-templatable seeds for the new-workspace dialog. Templates use `{name}`
 * tokens (see `applyIssueTemplate`); the extension settings UI stores one template
 * per field and blank means "use the default".
 *
 * The default title leads with the identifier because the host derives the
 * branch name from the title — so the generated branch carries the ticket id,
 * which is also how the board associates branches back to tickets.
 */
export const DEFAULT_TITLE_TEMPLATE = "{identifier}: {title}";

/**
 * The default prompt is a short self-contained brief: the assignment, the
 * issue URL, and the description. For a ticket without a description the
 * `{description}` block substitutes to nothing and the trailing trim in
 * `applyIssueTemplate` drops the blank line before it.
 */
export const DEFAULT_PROMPT_TEMPLATE = "Work on Linear issue {identifier}: {title}\n{url}\n\n{description}";

// Branch names get unwieldy past this; the cut happens at a hyphen boundary so
// the slug never ends mid-word.
const SLUG_MAX_LENGTH = 48;

/**
 * Kebab-case a ticket title for use in branch names: lowercase, runs of
 * non-alphanumerics collapsed to single hyphens, hyphens trimmed from both
 * ends, capped at `SLUG_MAX_LENGTH` characters.
 */
const slugForTitle = (title: string): string => {
  const slug = title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  if (slug.length <= SLUG_MAX_LENGTH) return slug;
  const head = slug.slice(0, SLUG_MAX_LENGTH);
  // A hyphen right after the cut means the head already ends on a whole word.
  if (slug[SLUG_MAX_LENGTH] === "-") return head;
  const lastHyphen = head.lastIndexOf("-");
  return lastHyphen > 0 ? head.slice(0, lastHyphen) : head;
};

/**
 * Substitute a template's `{name}` tokens with values from the ticket, then
 * trim trailing whitespace (so templates whose tail substitutes to nothing —
 * like the default prompt on a description-less ticket — end cleanly).
 * Unknown tokens are left literal so a typo shows up in the seeded text
 * instead of vanishing silently.
 */
export const applyIssueTemplate = (template: string, issue: LinearIssue): string => {
  const variables = new Map<string, string>([
    ["identifier", issue.identifier],
    ["identifierLower", issue.identifier.toLowerCase()],
    ["title", issue.title],
    ["titleSlug", slugForTitle(issue.title)],
    ["url", issue.url],
    ["description", issue.description ?? ""],
  ]);
  return template.replace(/\{(\w+)\}/g, (token, name: string) => variables.get(name) ?? token).trimEnd();
};

/** Pre-fill values for the host's new-workspace modal, derived from a ticket. */
export type WorkspaceSeed = {
  title: string;
  prompt: string;
  /** `undefined` when no branch template is set: the host derives the branch from the title. */
  branchName: string | undefined;
};

/** The user-configured templates, one per seeded field; blank means default. */
export type WorkspaceSeedTemplates = {
  title: string;
  branch: string;
  prompt: string;
};

/**
 * Build the new-workspace seeds for a ticket from the configured templates.
 * A blank (empty or whitespace-only) title or prompt template falls back to
 * its default; branch has no default template — blank yields an `undefined`
 * branch name, deferring to the host's title-derived branch.
 */
export const workspaceSeedForIssue = (issue: LinearIssue, templates: WorkspaceSeedTemplates): WorkspaceSeed => {
  const titleTemplate = templates.title.trim() ? templates.title : DEFAULT_TITLE_TEMPLATE;
  const promptTemplate = templates.prompt.trim() ? templates.prompt : DEFAULT_PROMPT_TEMPLATE;
  return {
    title: applyIssueTemplate(titleTemplate, issue),
    prompt: applyIssueTemplate(promptTemplate, issue),
    branchName: templates.branch.trim() ? applyIssueTemplate(templates.branch, issue) : undefined,
  };
};
