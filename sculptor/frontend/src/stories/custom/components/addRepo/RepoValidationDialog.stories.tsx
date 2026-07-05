import type { Meta, StoryObj } from "@storybook/react-vite";

import { RepoValidationDialog } from "~/components/addRepo/RepoValidationDialog.tsx";

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

export const NotGitRepo: Story = {
  args: {
    phase: { type: "not-git-repo", repoPath: "/Users/dev/my-project" },
  },
};

export const EmptyRepo: Story = {
  args: {
    phase: { type: "empty-repo", repoPath: "/Users/dev/my-project" },
  },
};

export const Initializing: Story = {
  args: {
    phase: { type: "initializing", repoPath: "/Users/dev/my-project" },
  },
};

export const Error: Story = {
  args: {
    phase: { type: "error", repoPath: "/Users/dev/my-project", errorMessage: "Directory does not exist" },
  },
};

export const ExistingFolder: Story = {
  args: {
    phase: {
      type: "clone-failed",
      repoPath: "/Users/dev/my-project",
      errorMessage: "This folder already exists. Add it as a local folder instead?",
      localPathSuggestion: "~/.sculptor/repos/github/my-project",
    },
    onOpenLocal: noop,
  },
};
