import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

import { TurnFooter } from "~/pages/workspace/chat/TurnFooter.tsx";

const meta = {
  title: "Chat/Controls/TurnFooter",
  component: TurnFooter,
  decorators: [
    (Story): ReactElement => (
      <div style={{ padding: "16px", maxWidth: "600px" }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof TurnFooter>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    metrics: {
      durationSeconds: 5.9,
      inputTokens: 4,
      outputTokens: 298,
    },
  },
};

export const HighTokenCount: Story = {
  args: {
    metrics: {
      durationSeconds: 42.3,
      inputTokens: 12_450,
      outputTokens: 8_321,
      reasoningTokens: 3_200,
    },
  },
};

export const NoTokens: Story = {
  args: {
    metrics: {
      durationSeconds: 2.1,
      inputTokens: 100,
      outputTokens: 50,
    },
  },
};

export const LongDuration: Story = {
  args: {
    metrics: {
      durationSeconds: 187.4,
      inputTokens: 50_000,
      outputTokens: 25_000,
      reasoningTokens: 10_000,
    },
  },
};

export const WithFileChanges: Story = {
  name: "With File Changes (click for popover)",
  args: {
    metrics: {
      durationSeconds: 22.3,
      inputTokens: 800,
      outputTokens: 580,
    },
    files: [{ path: "sculptor/backend/utils/pagination.py", status: "modified" }],
  },
};

export const WithMultipleFiles: Story = {
  name: "With Multiple Files (click for popover)",
  args: {
    metrics: {
      durationSeconds: 18.2,
      inputTokens: 2_100,
      outputTokens: 1_280,
    },
    files: [
      { path: "sculptor/backend/models/user.py", status: "modified" },
      { path: "sculptor/backend/utils/validators.py", status: "modified" },
      { path: "sculptor/backend/tests/test_user.py", status: "modified" },
    ],
  },
};

export const WithManyFiles: Story = {
  name: "With Many Files (click for popover)",
  args: {
    metrics: {
      durationSeconds: 45.0,
      inputTokens: 8_000,
      outputTokens: 4_600,
      reasoningTokens: 2_000,
    },
    files: [
      { path: "sculptor/backend/db/queries/users.py", status: "modified" },
      { path: "sculptor/backend/db/queries/workspaces.py", status: "modified" },
      { path: "sculptor/backend/db/queries/sessions.py", status: "modified" },
      { path: "sculptor/backend/db/builder.py", status: "modified" },
      { path: "sculptor/backend/db/base.py", status: "modified" },
      { path: "sculptor/backend/tests/test_queries.py", status: "modified" },
      { path: "sculptor/backend/tests/test_builder.py", status: "modified" },
      { path: "sculptor/backend/db/legacy_orm.py", status: "modified" },
    ],
  },
};

export const WithManyModifiedFiles: Story = {
  name: "With Many Modified Files (click for popover)",
  args: {
    metrics: {
      durationSeconds: 24.0,
      inputTokens: 3_200,
      outputTokens: 1_600,
    },
    files: [
      { path: "sculptor/backend/utils/string_helpers.py", status: "modified" },
      { path: "sculptor/backend/utils/date_helpers.py", status: "modified" },
      { path: "sculptor/backend/utils/__init__.py", status: "modified" },
      { path: "sculptor/backend/utils/utils.py", status: "modified" },
    ],
  },
};
