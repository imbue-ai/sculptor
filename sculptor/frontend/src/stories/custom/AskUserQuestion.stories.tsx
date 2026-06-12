import type { Meta, StoryObj } from "@storybook/react-vite";
import { Provider as JotaiProvider } from "jotai";
import type { ReactElement } from "react";

import type { AskUserQuestionData } from "~/api";
import { AskUserQuestion } from "~/pages/workspace/components/AskUserQuestion";

const SINGLE_QUESTION_DATA: AskUserQuestionData = {
  questions: [
    {
      question:
        "Where should the workspace panel live in the layout? From the screenshot it appears to be a left sidebar. Should it be a new panel zone in the DockingLayout, or a fixed sidebar separate from the panel system?",
      header: "PANEL ZONE",
      options: [
        {
          label: "New DockingLayout panel",
          description:
            'Add it as a panel in the existing docking system (e.g., a "left" or "top-left" zone), making it draggable/closeable like other panels',
        },
        {
          label: "Fixed left sidebar",
          description:
            "A dedicated section outside the DockingLayout, always visible when the workspace page is open (similar to how VS Code has a fixed sidebar)",
        },
        {
          label: "Toggleable sidebar",
          description:
            "A fixed sidebar that can be toggled on/off via a button, but not part of the draggable panel system",
        },
      ],
      multiSelect: false,
    },
  ],
  toolUseId: "story-tool-use-1",
};

const MULTI_SELECT_DATA: AskUserQuestionData = {
  questions: [
    {
      question: "Which features do you want to enable for the new dashboard?",
      header: "FEATURES",
      options: [
        {
          label: "Real-time updates",
          description: "Enable WebSocket-based live data streaming",
        },
        {
          label: "Dark mode",
          description: "Support both light and dark theme variants",
        },
        {
          label: "Export to CSV",
          description: "Allow users to download dashboard data as CSV files",
        },
        {
          label: "Keyboard shortcuts",
          description: "Add keyboard navigation and shortcut support",
        },
      ],
      multiSelect: true,
    },
  ],
  toolUseId: "story-tool-use-2",
};

const MULTIPLE_QUESTIONS_DATA: AskUserQuestionData = {
  questions: [
    {
      question: "Which database should we use for storing user data?",
      header: "DATABASE",
      options: [
        {
          label: "PostgreSQL",
          description: "Relational database with strong ACID compliance",
        },
        {
          label: "MongoDB",
          description: "Document-oriented NoSQL database",
        },
        {
          label: "SQLite",
          description: "Lightweight embedded database",
        },
      ],
      multiSelect: false,
    },
    {
      question: "What authentication method should we implement?",
      header: "AUTH",
      options: [
        {
          label: "OAuth 2.0",
          description: "Industry-standard authorization framework",
        },
        {
          label: "JWT tokens",
          description: "Stateless token-based authentication",
        },
        {
          label: "Session-based",
          description: "Traditional server-side session management",
        },
      ],
      multiSelect: false,
    },
    {
      question: "Which CI/CD platform should we integrate with?",
      header: "CI/CD",
      options: [
        {
          label: "GitHub Actions",
          description: "Native GitHub integration",
        },
        {
          label: "GitLab CI",
          description: "Built-in GitLab pipeline system",
        },
      ],
      multiSelect: false,
    },
  ],
  toolUseId: "story-tool-use-3",
};

const MARKDOWN_QUESTION_DATA: AskUserQuestionData = {
  questions: [
    {
      question:
        'I\'ve analyzed the release commands. Here are the issues I see: 1. **`bump-version`**: Currently bumps `0.10.0.dev0` → `0.11.0` (clean). Should bump to `0.11.0.dev0` to keep main on dev0. 2. **`cut-release`**: Uses `pyproject_version()` (`0.10.0.dev0`) as "target_release_version" and creates RC from it. `next_version(\'0.10.0.dev0\', PRE_RELEASE)` → `0.10.0rc1` which is correct, but: - The log says "Beginning a release branch for 0.10.0.dev0" — should say "0.10.0" - The target_release_version should strip `.dev0` first - Per the architecture doc, after cutting release, main should be bumped to the next version (0.11.0.dev0) — this isn\'t currently done 3. **`cut-release` should also ensure it\'s run from a `.dev0` version** (not an arbitrary version on main) Does this match your expectations? Any other issues you want addressed?',
      header: "SCOPE",
      options: [
        {
          label: "Yes, fix all three",
          description: "Fix **bump-version**, **cut-release** logging/validation, and add post-cut main bump",
        },
        {
          label: "Fix 1 and 2 only",
          description: "Fix bump-version and cut-release, but don't add automatic main bump after `cut-release`",
        },
        {
          label: "Let me clarify",
          description: "I have different expectations for how these should work",
        },
      ],
      multiSelect: false,
    },
  ],
  toolUseId: "story-tool-use-markdown",
};

const MINIMAL_OPTIONS_DATA: AskUserQuestionData = {
  questions: [
    {
      question: "Should we proceed with the refactoring?",
      header: "CONFIRM",
      options: [
        {
          label: "Yes, proceed",
          description: "Start the refactoring process now",
        },
        {
          label: "No, cancel",
          description: "Abort and keep the current implementation",
        },
      ],
      multiSelect: false,
    },
  ],
  toolUseId: "story-tool-use-4",
};

const handleSubmit = (answers: Record<string, string>): void => {
  console.log("Submitted answers:", answers);
};

const handleDismiss = (): void => {
  console.log("Dismissed");
};

const Wrapper = ({
  questionData,
  onDismiss,
}: {
  questionData: AskUserQuestionData;
  onDismiss?: boolean;
}): ReactElement => (
  <JotaiProvider>
    <div style={{ width: "600px" }}>
      <AskUserQuestion
        taskId="storybook-demo"
        questionData={questionData}
        onSubmit={handleSubmit}
        onDismiss={onDismiss ? handleDismiss : undefined}
      />
    </div>
  </JotaiProvider>
);

const meta = {
  title: "Custom/AskUserQuestion",
  component: Wrapper,
  args: {
    onDismiss: true,
  },
} satisfies Meta<typeof Wrapper>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const SingleQuestion: Story = {
  args: {
    questionData: SINGLE_QUESTION_DATA,
  },
};

export const MultiSelect: Story = {
  args: {
    questionData: MULTI_SELECT_DATA,
  },
};

export const MultipleQuestions: Story = {
  args: {
    questionData: MULTIPLE_QUESTIONS_DATA,
  },
};

export const Minimal: Story = {
  args: {
    questionData: MINIMAL_OPTIONS_DATA,
  },
};

export const NoDismiss: Story = {
  args: {
    questionData: SINGLE_QUESTION_DATA,
    onDismiss: false,
  },
};

export const MarkdownContent: Story = {
  args: {
    questionData: MARKDOWN_QUESTION_DATA,
  },
};
