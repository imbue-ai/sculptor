import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { ChatMarkdownBlock } from "~/pages/workspace/chat/ChatMarkdownBlock.tsx";

const meta = {
  title: "Chat/Content/MarkdownBlock",
  component: ChatMarkdownBlock,
  decorators: [
    (Story): ReactElement => (
      <MemoryRouter initialEntries={["/ws/storybook-ws/agent/storybook-agent"]}>
        <Routes>
          <Route
            path="/ws/:workspaceID/agent/:id"
            element={
              <div style={{ padding: "16px", maxWidth: "700px" }}>
                <Story />
              </div>
            }
          />
        </Routes>
      </MemoryRouter>
    ),
  ],
} satisfies Meta<typeof ChatMarkdownBlock>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Headings: Story = {
  args: {
    content: [
      "# Heading 1",
      "",
      "## Heading 2",
      "",
      "### Heading 3",
      "",
      "#### Heading 4",
      "",
      "##### Heading 5",
      "",
      "###### Heading 6",
    ].join("\n"),
  },
};

export const InlineFormatting: Story = {
  args: {
    content: [
      "This has **bold text** and *italic text* and ***bold italic*** together.",
      "",
      "You can also use __underscores for bold__ and _underscores for italic_.",
      "",
      "Here is ~~strikethrough text~~ via GFM.",
      "",
      "Inline `code snippets` appear with a background highlight.",
      "",
      "Multiple `inline` code `snippets` in one `line` should each be styled.",
    ].join("\n"),
  },
};

export const Links: Story = {
  args: {
    content: [
      "Here is a [basic link](https://example.com) in a sentence.",
      "",
      "An autolinked URL: https://github.com/example/repo",
      "",
      "A [link with a long label that might wrap on narrow screens](https://example.com/very/long/path/to/something)",
      "",
      "Multiple links: [one](https://a.com), [two](https://b.com), and [three](https://c.com).",
    ].join("\n"),
  },
};

export const UnorderedLists: Story = {
  args: {
    content: [
      "- First item",
      "- Second item",
      "- Third item",
      "",
      "Nested list:",
      "",
      "- Top level A",
      "  - Nested A.1",
      "  - Nested A.2",
      "    - Deeply nested A.2.1",
      "- Top level B",
      "  - Nested B.1",
    ].join("\n"),
  },
};

export const OrderedLists: Story = {
  args: {
    content: [
      "1. First step",
      "2. Second step",
      "3. Third step",
      "",
      "Nested ordered list:",
      "",
      "1. Install dependencies",
      "   1. Run `npm install`",
      "   2. Run `npm run build`",
      "2. Configure the app",
      "   1. Copy `.env.example` to `.env`",
      "   2. Fill in the values",
      "3. Start the server",
    ].join("\n"),
  },
};

export const MixedLists: Story = {
  args: {
    content: [
      "- Unordered parent",
      "  1. Ordered child one",
      "  2. Ordered child two",
      "- Another unordered parent",
      "  - Unordered child",
      "    1. Deep ordered child",
    ].join("\n"),
  },
};

export const TaskLists: Story = {
  args: {
    content: [
      "A flat task list:",
      "",
      "- [x] Write the spec",
      "- [ ] Implement the feature",
      "- [ ] Add tests",
      "",
      "A task list with nested sub-tasks:",
      "",
      "- [x] Top level task that is done",
      "  - [x] Nested sub-task A.1",
      "  - [ ] Nested sub-task A.2",
      "    - [ ] Deeply nested A.2.1",
      "- [ ] Another top level task",
      "  - [ ] Nested sub-task B.1",
      "",
      "A task item with text long enough to wrap onto a second line so we can",
      "confirm the wrapped text aligns under the first line and not under the",
      "checkbox:",
      "",
      "- [ ] This is a task with a fairly long description that should wrap across multiple lines when the container is narrow enough to force wrapping",
      "",
      "A loose task list (blank lines between items, so each item's text is",
      "wrapped in a paragraph) — the checkbox must stay on the same line as its",
      "text:",
      "",
      "- [x] First loose item",
      "",
      "- [ ] Second loose item",
      "",
      "- [ ] Third loose item",
    ].join("\n"),
  },
};

export const Blockquotes: Story = {
  args: {
    content: [
      "> A simple blockquote with a single paragraph.",
      "",
      "> A blockquote with **bold** and *italic* and `code` inside.",
      "",
      "> A multi-paragraph blockquote.",
      ">",
      "> Second paragraph in the same quote.",
      "",
      "> Nested blockquotes:",
      ">",
      "> > This is a nested quote.",
      "> >",
      "> > It can have multiple lines.",
    ].join("\n"),
  },
};

export const Tables: Story = {
  args: {
    content: [
      "| Name | Type | Default | Description |",
      "|------|------|---------|-------------|",
      "| `content` | `string` | — | The markdown string to render |",
      "| `language` | `string` | `undefined` | Language for syntax highlighting |",
      "| `className` | `string` | `undefined` | Additional CSS class |",
      "",
      "Right-aligned and centered columns:",
      "",
      "| Left | Center | Right |",
      "|:-----|:------:|------:|",
      "| a | b | 100 |",
      "| cc | dd | 2,500 |",
      "| eee | fff | 38,000 |",
    ].join("\n"),
  },
};

export const WideTable: Story = {
  args: {
    content: [
      "| Col 1 | Col 2 | Col 3 | Col 4 | Col 5 | Col 6 | Col 7 | Col 8 | Col 9 | Col 10 |",
      "|-------|-------|-------|-------|-------|-------|-------|-------|-------|--------|",
      "| data | data | data | data | data | data | data | data | data | data |",
      "| more data | more data | more data | more data | more data | more data | more data | more data | more data | more data |",
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

export const CodeBlocks: Story = {
  args: {
    content: [
      "A Python code block:",
      "",
      "```python",
      "def fibonacci(n: int) -> int:",
      '    """Return the nth Fibonacci number."""',
      "    if n <= 1:",
      "        return n",
      "    return fibonacci(n - 1) + fibonacci(n - 2)",
      "",
      "",
      "for i in range(10):",
      '    print(f"fib({i}) = {fibonacci(i)}")',
      "```",
      "",
      "A TypeScript code block:",
      "",
      "```typescript",
      "type Props = {",
      "  content: string;",
      "  language?: string;",
      "};",
      "",
      "export const CodeBlock = ({ content, language }: Props): ReactElement => {",
      "  return (",
      "    <pre data-language={language}>",
      "      <code>{content}</code>",
      "    </pre>",
      "  );",
      "};",
      "```",
      "",
      "A block with no language specified:",
      "",
      "```",
      "Just some plain preformatted text.",
      "No syntax highlighting here.",
      "```",
    ].join("\n"),
  },
};

export const LongCodeLines: Story = {
  args: {
    content: [
      "```",
      "const veryLongVariableName = someFunction(argumentOne, argumentTwo, argumentThree, argumentFour, argumentFive, argumentSix, argumentSeven, argumentEight, argumentNine, argumentTen);",
      "```",
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

export const InlineCode: Story = {
  args: {
    content: [
      "Use `npm install` to install dependencies.",
      "",
      "The function `calculateTotal(items: ReadonlyArray<Item>)` returns a `number`.",
      "",
      "Set the environment variable `DATABASE_URL=postgres://localhost:5432/mydb` before starting.",
      "",
      "Run `git log --oneline --graph --all` to see the full branch history.",
    ].join("\n"),
  },
};

export const HorizontalRules: Story = {
  args: {
    content: [
      "Section one content.",
      "",
      "---",
      "",
      "Section two content.",
      "",
      "---",
      "",
      "Section three content.",
    ].join("\n"),
  },
};

export const Emoji: Story = {
  args: {
    content: [
      "Emoji shortcodes via remark-emoji:",
      "",
      "- :rocket: Rocket",
      "- :white_check_mark: Check mark",
      "- :warning: Warning",
      "- :bug: Bug",
      "- :sparkles: Sparkles",
      "- :memo: Memo",
      "",
      "Inline: This feature is :fire: and ready to ship :ship:",
    ].join("\n"),
  },
};

export const KitchenSink: Story = {
  args: {
    content: [
      "# Full Markdown Kitchen Sink",
      "",
      "This story combines **every** supported markdown element for a complete visual check.",
      "",
      "## Text Formatting",
      "",
      "Regular text, **bold**, *italic*, ***bold italic***, ~~strikethrough~~, and `inline code`.",
      "",
      "## Lists",
      "",
      "Unordered:",
      "",
      "- Item A",
      "  - Nested A.1",
      "  - Nested A.2",
      "- Item B",
      "",
      "Ordered:",
      "",
      "1. Step one",
      "2. Step two",
      "   1. Sub-step",
      "3. Step three",
      "",
      "## Links",
      "",
      "Visit [Example](https://example.com) or https://github.com for more.",
      "",
      "## Blockquote",
      "",
      "> This is a blockquote with **bold** and `code`.",
      ">",
      "> > Nested quote inside.",
      "",
      "## Table",
      "",
      "| Feature | Status | Notes |",
      "|---------|--------|-------|",
      "| Headings | :white_check_mark: | Native h1–h6 |",
      "| Lists | :white_check_mark: | Nested supported |",
      "| Tables | :white_check_mark: | Scrollable wrapper |",
      "| Code | :white_check_mark: | Horizontal scroll |",
      "",
      "## Code Block",
      "",
      "```python",
      "def greet(name: str) -> str:",
      '    return f"Hello, {name}!"',
      "```",
      "",
      "---",
      "",
      "### End :sparkles:",
      "",
      "That covers all supported markdown elements.",
    ].join("\n"),
  },
};

export const NarrowWidth: Story = {
  args: {
    content: [
      "# Narrow Width Test",
      "",
      "Testing all elements at 400px to catch overflow.",
      "",
      "A long URL: https://github.com/owner/repository/pulls?q=is%3Apr+is%3Aopen+label%3Abug",
      "",
      "- List item with `inline code` and **bold**",
      "- Another item with a [link](https://example.com/long/path/to/resource)",
      "",
      "| Column A | Column B | Column C |",
      "|----------|----------|----------|",
      "| data | more data | even more data |",
      "",
      "```",
      "a_very_long_variable_name = some_function(arg1, arg2, arg3, arg4, arg5)",
      "```",
      "",
      "> A blockquote that contains enough text to wrap across multiple lines at narrow widths.",
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
