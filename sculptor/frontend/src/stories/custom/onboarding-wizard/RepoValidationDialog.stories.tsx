import type { Meta, StoryObj } from "@storybook/react-vite";

import { RepoValidationDialog } from "~/components/add-repo/RepoValidationDialog.tsx";

const noop = (): void => {};

const meta = {
  title: "Custom/Onboarding/RepoValidationDialog",
  component: RepoValidationDialog,
  args: {
    isOpen: true,
    onInitializeGit: noop,
    onCreateInitialCommit: noop,
    onCancel: noop,
  },
} satisfies Meta<typeof RepoValidationDialog>;

// eslint-disable-next-line import/no-default-export
export default meta;
type Story = StoryObj<typeof meta>;

export const Checking: Story = {
  args: {
    state: { status: "checking", repoPath: "/Users/dev/my-project" },
  },
};

export const NotGitRepo: Story = {
  args: {
    state: { status: "not-git-repo", repoPath: "/Users/dev/my-project" },
  },
};

export const EmptyRepo: Story = {
  args: {
    state: { status: "empty-repo", repoPath: "/Users/dev/my-project" },
  },
};

export const Initializing: Story = {
  args: {
    state: { status: "initializing", repoPath: "/Users/dev/my-project" },
  },
};

export const Success: Story = {
  args: {
    state: { status: "success", repoPath: "/Users/dev/my-project" },
  },
};

export const Error: Story = {
  args: {
    state: { status: "error", repoPath: "/Users/dev/my-project", errorMessage: "Directory does not exist" },
  },
};
