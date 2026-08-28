import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

import { AlphaCodeBlock } from "~/pages/workspace/chatAlpha/AlphaCodeBlock.tsx";

const meta = {
  title: "Chat Alpha/Content/CodeBlock",
  component: AlphaCodeBlock,
  decorators: [
    (Story): ReactElement => (
      <div style={{ padding: "16px", maxWidth: "700px" }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof AlphaCodeBlock>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Python: Story = {
  args: {
    language: "python",
    content: [
      "from typing import Optional",
      "",
      "",
      "def fibonacci(n: int, memo: Optional[dict] = None) -> int:",
      '    """Return the nth Fibonacci number using memoization."""',
      "    if memo is None:",
      "        memo = {}",
      "    if n in memo:",
      "        return memo[n]",
      "    if n <= 1:",
      "        return n",
      "    memo[n] = fibonacci(n - 1, memo) + fibonacci(n - 2, memo)",
      "    return memo[n]",
      "",
    ].join("\n"),
  },
};

export const TypeScript: Story = {
  args: {
    language: "typescript",
    content: [
      "type AlphaCodeBlockProps = {",
      "  content: string;",
      "  language?: string;",
      "};",
      "",
      "export const AlphaCodeBlock = memo(",
      "  ({ content, language }: AlphaCodeBlockProps): ReactElement => {",
      "    return (",
      "      <pre className={styles.codeBlock} data-language={language}>",
      "        <code>{content}</code>",
      "      </pre>",
      "    );",
      "  },",
      ");",
      "",
    ].join("\n"),
  },
};

export const JSON: Story = {
  args: {
    language: "json",
    content: [
      "{",
      '  "name": "sculptor",',
      '  "version": "0.0.0",',
      '  "dependencies": {',
      '    "react": "^19.0.0",',
      '    "react-markdown": "^9.0.0",',
      '    "remark-gfm": "^4.0.0"',
      "  }",
      "}",
      "",
    ].join("\n"),
  },
};

export const Bash: Story = {
  args: {
    language: "bash",
    content: [
      "#!/bin/bash",
      "set -euo pipefail",
      "",
      "# Install dependencies and run tests",
      "npm install",
      "npm run build",
      "npm test -- --coverage",
      "",
      'echo "All tests passed!"',
      "",
    ].join("\n"),
  },
};

export const NoLanguage: Story = {
  args: {
    content: [
      "Plain preformatted text without a language.",
      "No syntax highlighting should be applied.",
      "",
      "  Indented lines should preserve their whitespace.",
      "    Even deeper indentation.",
      "",
    ].join("\n"),
  },
};

export const LongLines: Story = {
  args: {
    language: "typescript",
    content: [
      "// This line is intentionally very long to test horizontal scrolling behavior within the code block container",
      "const result = someFunction(argumentOne, argumentTwo, argumentThree, argumentFour, argumentFive, argumentSix, argumentSeven, argumentEight);",
      "",
    ].join("\n"),
  },
  decorators: [
    (Story): ReactElement => (
      <div style={{ padding: "16px", maxWidth: "400px" }}>
        <Story />
      </div>
    ),
  ],
};

export const SingleLine: Story = {
  args: {
    language: "bash",
    content: "npm install --save-dev @types/react @types/react-dom typescript\n",
  },
};

export const Empty: Story = {
  args: {
    content: "\n",
  },
};
