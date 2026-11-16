import type { Meta, StoryObj } from "@storybook/react-vite";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createStore, Provider as JotaiProvider } from "jotai";
import type { ReactElement } from "react";

import type { Workspace, WorkspaceJjStateInfo } from "~/api";
import { WorkspaceInitializationStrategy } from "~/api";
import { workspaceJjStateAtomFamily } from "~/common/state/atoms/workspaceJjState.ts";
import { workspaceAtomFamily } from "~/common/state/atoms/workspaces.ts";

import { JjIdentityPill } from "./JjIdentityPill";

const WORKSPACE_ID = "ws-story";

const baseJjState: WorkspaceJjStateInfo = {
  workspaceId: WORKSPACE_ID,
  workingCopyChangeId: "kxqpmzvyrstuwlnokxqpmzvyrstuwlno",
  workingCopyChangeIdPrefixLength: 2,
  workingCopyDescription: "",
  isWorkingCopyEmpty: false,
  bookmarks: [],
  primaryBookmark: null,
  unbookmarkedRevisionCount: 0,
  hasConflict: false,
  isDivergent: false,
  isWorkingCopyStale: false,
};

// The hover card reads the working copy's commit id from the revisions route,
// which a story has no backend for, so the card's commit row reads "Unknown".
const storyQueryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

/** Renders the pill the way the workspace header does, from hand-made streamed state. */
const Wrapper = (props: {
  requestedBookmark: string | null;
  jjState: Partial<WorkspaceJjStateInfo> | null;
}): ReactElement => {
  const store = createStore();
  const workspace: Workspace = {
    objectId: WORKSPACE_ID,
    projectId: "proj-story",
    organizationReference: "org-story",
    description: "Login form",
    initializationStrategy: WorkspaceInitializationStrategy.JJ_WORKSPACE,
    sourceBranch: "main@origin",
    targetBranch: "main@origin",
    requestedBranchName: props.requestedBookmark,
  };
  store.set(workspaceAtomFamily(WORKSPACE_ID), workspace);
  if (props.jjState !== null) {
    store.set(workspaceJjStateAtomFamily(WORKSPACE_ID), { ...baseJjState, ...props.jjState });
  }
  return (
    <QueryClientProvider client={storyQueryClient}>
      <JotaiProvider store={store}>
        <div style={{ background: "var(--gray-2)", display: "flex", padding: "var(--space-4)", width: "520px" }}>
          <JjIdentityPill workspaceId={WORKSPACE_ID} />
        </div>
      </JotaiProvider>
    </QueryClientProvider>
  );
};

const meta = {
  title: "Custom/JjIdentityPill",
  component: Wrapper,
} satisfies Meta<typeof Wrapper>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const PrimaryBookmark: Story = {
  args: {
    requestedBookmark: "dev/login-form",
    jjState: { bookmarks: ["dev/login-form"], primaryBookmark: "dev/login-form" },
  },
};

export const MoreBookmarks: Story = {
  args: {
    requestedBookmark: "dev/login-form",
    jjState: {
      bookmarks: ["dev/login-form-tests", "dev/login-form", "dev/login-form-api"],
      primaryBookmark: "dev/login-form",
    },
  },
};

// Described revisions sit above the bookmark, so the bookmark lags the work.
export const RevisionsAboveBookmark: Story = {
  args: {
    requestedBookmark: "dev/login-form",
    jjState: { bookmarks: ["dev/login-form"], primaryBookmark: "dev/login-form", unbookmarkedRevisionCount: 2 },
  },
};

// The first turn has not described anything yet, so the requested bookmark does not exist.
export const RequestedBookmarkGhosted: Story = {
  args: {
    requestedBookmark: "dev/login-form",
    jjState: { isWorkingCopyEmpty: true },
  },
};

export const ChangeIdAndDescription: Story = {
  args: {
    requestedBookmark: null,
    jjState: { workingCopyDescription: "Add the login form" },
  },
};

export const Conflict: Story = {
  args: {
    requestedBookmark: "dev/login-form",
    jjState: {
      bookmarks: ["dev/login-form"],
      primaryBookmark: "dev/login-form",
      hasConflict: true,
      unbookmarkedRevisionCount: 1,
    },
  },
};

// The jj state has not streamed in; past the grace window the requested name stands in.
export const NoJjStateYet: Story = {
  args: {
    requestedBookmark: "dev/login-form",
    jjState: null,
  },
};
