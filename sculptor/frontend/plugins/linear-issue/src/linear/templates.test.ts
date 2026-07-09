import { describe, expect, it } from "vitest";

import type { LinearIssue } from "./client.ts";
import {
  applyIssueTemplate,
  DEFAULT_PROMPT_TEMPLATE,
  DEFAULT_TITLE_TEMPLATE,
  workspaceSeedForIssue,
  type WorkspaceSeedTemplates,
} from "./templates.ts";

const issue = (overrides: Partial<LinearIssue> = {}): LinearIssue => ({
  identifier: "SCU-42",
  title: "Wire up the thing",
  url: "https://linear.app/x/SCU-42",
  description: null,
  priorityLabel: null,
  state: null,
  assignee: null,
  attachments: [],
  children: [],
  ...overrides,
});

/** All-blank templates: every field falls back to its default behavior. */
const BLANK_TEMPLATES: WorkspaceSeedTemplates = { title: "", branch: "", prompt: "" };

describe("applyIssueTemplate", () => {
  it("substitutes every supported variable", () => {
    const result = applyIssueTemplate(
      "{identifier}|{identifierLower}|{title}|{titleSlug}|{url}|{description}",
      issue({ description: "Some details." }),
    );
    expect(result).toBe("SCU-42|scu-42|Wire up the thing|wire-up-the-thing|https://linear.app/x/SCU-42|Some details.");
  });

  it("substitutes a missing description as an empty string", () => {
    expect(applyIssueTemplate("[{description}]", issue())).toBe("[]");
  });

  it("leaves unknown tokens literal so typos stay visible", () => {
    expect(applyIssueTemplate("{identifer} and {nope}", issue())).toBe("{identifer} and {nope}");
  });

  it("does not resolve tokens through the object prototype", () => {
    expect(applyIssueTemplate("{toString}", issue())).toBe("{toString}");
  });

  it("trims trailing whitespace after substitution", () => {
    expect(applyIssueTemplate("{identifier}\n\n{description}", issue())).toBe("SCU-42");
  });

  describe("{titleSlug}", () => {
    const slugOf = (title: string): string => applyIssueTemplate("{titleSlug}", issue({ title }));

    it("kebab-cases the title", () => {
      expect(slugOf("Wire up the thing")).toBe("wire-up-the-thing");
    });

    it("collapses runs of edge characters to single hyphens and trims the ends", () => {
      expect(slugOf("  Fix: (weird)   chars!! ")).toBe("fix-weird-chars");
    });

    it("caps long titles at a hyphen boundary without a trailing fragment", () => {
      // 5 chars per "word-" unit: the 48-char cap lands mid-word, so the slug
      // backs off to the previous hyphen boundary.
      const slug = slugOf(Array.from({ length: 20 }, (_, i) => `word${i % 10}`).join(" "));
      expect(slug.length).toBeLessThanOrEqual(48);
      expect(slug).toBe("word0-word1-word2-word3-word4-word5-word6-word7");
      expect(slug.endsWith("-")).toBe(false);
    });

    it("keeps a whole word that ends exactly at the cap", () => {
      // "aaaa...(48)" followed by more words: position 48 is a hyphen, so the
      // full 48-char word survives.
      expect(slugOf(`${"a".repeat(48)} tail words`)).toBe("a".repeat(48));
    });

    it("hard-cuts a single word longer than the cap", () => {
      expect(slugOf("b".repeat(60))).toBe("b".repeat(48));
    });
  });
});

describe("workspaceSeedForIssue", () => {
  it("leads the default title with the identifier so the derived branch carries it", () => {
    expect(workspaceSeedForIssue(issue(), BLANK_TEMPLATES).title).toBe("SCU-42: Wire up the thing");
  });

  it("builds the default prompt as assignment line + URL when there is no description", () => {
    expect(workspaceSeedForIssue(issue(), BLANK_TEMPLATES).prompt).toBe(
      "Work on Linear issue SCU-42: Wire up the thing\nhttps://linear.app/x/SCU-42",
    );
  });

  it("appends the description after a blank line when present", () => {
    expect(workspaceSeedForIssue(issue({ description: "Details\nhere." }), BLANK_TEMPLATES).prompt).toBe(
      "Work on Linear issue SCU-42: Wire up the thing\nhttps://linear.app/x/SCU-42\n\nDetails\nhere.",
    );
  });

  it("treats an empty description like a missing one", () => {
    expect(workspaceSeedForIssue(issue({ description: "" }), BLANK_TEMPLATES).prompt).toBe(
      "Work on Linear issue SCU-42: Wire up the thing\nhttps://linear.app/x/SCU-42",
    );
  });

  it("matches the explicit default templates when they are passed verbatim", () => {
    const explicit = { title: DEFAULT_TITLE_TEMPLATE, branch: "", prompt: DEFAULT_PROMPT_TEMPLATE };
    for (const ticket of [issue(), issue({ description: "Some details." })]) {
      expect(workspaceSeedForIssue(ticket, explicit)).toEqual(workspaceSeedForIssue(ticket, BLANK_TEMPLATES));
    }
  });

  it("applies custom title and prompt templates", () => {
    const seed = workspaceSeedForIssue(issue(), {
      title: "[{identifier}] {title}",
      branch: "",
      prompt: "Fix {identifier} ({url})",
    });
    expect(seed.title).toBe("[SCU-42] Wire up the thing");
    expect(seed.prompt).toBe("Fix SCU-42 (https://linear.app/x/SCU-42)");
  });

  it("treats whitespace-only templates as blank and falls back to the defaults", () => {
    expect(workspaceSeedForIssue(issue(), { title: "  ", branch: " \n", prompt: "\t" })).toEqual(
      workspaceSeedForIssue(issue(), BLANK_TEMPLATES),
    );
  });

  it("leaves branchName undefined when the branch template is blank", () => {
    expect(workspaceSeedForIssue(issue(), BLANK_TEMPLATES).branchName).toBeUndefined();
  });

  it("applies the branch template when set", () => {
    const seed = workspaceSeedForIssue(issue(), { ...BLANK_TEMPLATES, branch: "linear/{identifierLower}-{titleSlug}" });
    expect(seed.branchName).toBe("linear/scu-42-wire-up-the-thing");
  });
});
