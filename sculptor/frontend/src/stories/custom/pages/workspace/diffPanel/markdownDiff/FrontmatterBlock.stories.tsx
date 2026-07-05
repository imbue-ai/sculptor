import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

import { FrontmatterBlock } from "~/pages/workspace/diffPanel/markdownDiff/FrontmatterBlock.tsx";
import { parseFrontmatter } from "~/pages/workspace/diffPanel/markdownDiff/utils/frontmatter.ts";

// Render the block exactly as it appears in the file preview: inside a padded
// `markdownBody` surface, above the rendered document body.
const Wrapper = ({ source }: { source: string }): ReactElement => {
  const { frontmatter, body } = parseFrontmatter(source);
  return (
    <div
      data-markdown-body
      style={{
        background: "light-dark(var(--color-panel-solid), var(--color-background))",
        maxWidth: 720,
        padding: "var(--space-4)",
      }}
    >
      {frontmatter && <FrontmatterBlock frontmatter={frontmatter} />}
      {/* A stand-in for the rendered markdown body that follows the block. */}
      <h1 style={{ marginTop: 0 }}>{body.split("\n")[0]?.replace(/^#\s*/, "") || "Document"}</h1>
      <p style={{ color: "var(--gray-11)" }}>Body content renders here, below the metadata.</p>
    </div>
  );
};

const meta = {
  title: "Custom/FrontmatterBlock",
  component: Wrapper,
} satisfies Meta<typeof Wrapper>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const TypicalDoc: Story = {
  args: {
    source: [
      "---",
      "title: Design Notes",
      "author: Example Author",
      "date: 2026-01-01",
      "draft: false",
      "---",
      "",
      "# Design Notes",
      "",
    ].join("\n"),
  },
};

export const SkillFile: Story = {
  args: {
    source: [
      "---",
      "name: code-review-checklist",
      "description: |",
      "  Review a set of code changes against the review categories and",
      "  produce a markdown findings table. Use when reviewing code.",
      "---",
      "",
      "# code-review-checklist",
      "",
    ].join("\n"),
  },
};

export const NestedAndList: Story = {
  args: {
    source: [
      "---",
      "name: linear-issue",
      "tags:",
      "  - docs",
      "  - internal",
      "  - plugin",
      "metadata:",
      "  type: reference",
      "  version: 3",
      "---",
      "",
      "# Plugin",
      "",
    ].join("\n"),
  },
};

export const TomlRawFallback: Story = {
  args: {
    source: ["+++", 'title = "Hugo Page"', "draft = false", 'tags = ["a", "b"]', "+++", "", "# Hugo Page", ""].join(
      "\n",
    ),
  },
};

export const MalformedRawFallback: Story = {
  args: {
    source: ["---", "title: Broken", "  : nope", "key: : :", "---", "", "# Broken", ""].join("\n"),
  },
};
