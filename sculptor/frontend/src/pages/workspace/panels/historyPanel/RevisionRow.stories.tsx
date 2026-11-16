import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";
import { useState } from "react";

import type { RevisionInfo } from "~/api";

import { RevisionRow } from "./RevisionRow";
import { makeStoryRevision } from "./revisionStoryData.ts";

/** Renders one row at the Revisions panel's list width, toggling its files on click. */
const Wrapper = (props: { revision: RevisionInfo; isInitiallyExpanded: boolean }): ReactElement => {
  const [isExpanded, setIsExpanded] = useState<boolean>(props.isInitiallyExpanded);
  return (
    <div style={{ background: "var(--color-panel-solid)", padding: "var(--space-2)", width: "320px" }}>
      <RevisionRow
        revision={props.revision}
        isFirst
        isExpanded={isExpanded}
        onToggle={() => setIsExpanded((previous) => !previous)}
        onFileClick={() => {}}
      />
    </div>
  );
};

const meta = {
  title: "Custom/RevisionRow",
  component: Wrapper,
} satisfies Meta<typeof Wrapper>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Described: Story = {
  args: {
    revision: makeStoryRevision({
      changeId: "kxqpmzvyrstuwlnokxqpmzvyrstuwlno",
      commitId: "0123456789abcdef0123456789abcdef01234567",
      description: "Add the login form",
      bookmarks: ["dev/login-form"],
    }),
    isInitiallyExpanded: false,
  },
};

export const Expanded: Story = {
  args: {
    revision: makeStoryRevision({
      changeId: "kxqpmzvyrstuwlnokxqpmzvyrstuwlno",
      commitId: "0123456789abcdef0123456789abcdef01234567",
      description: "Add the login form",
      files: [
        { path: "src/login/LoginForm.tsx", status: "A", oldPath: null, additions: 80, deletions: 0 },
        { path: "src/app.tsx", status: "M", oldPath: null, additions: 2, deletions: 1 },
      ],
    }),
    isInitiallyExpanded: true,
  },
};

// The working copy the agent is editing, with no description yet.
export const WorkingCopy: Story = {
  args: {
    revision: makeStoryRevision({
      changeId: "wnlrostkvpzmqxyuwnlrostkvpzmqxyu",
      commitId: "1111111111111111111111111111111111111111",
      isWorkingCopy: true,
    }),
    isInitiallyExpanded: false,
  },
};

// A fresh working copy after `jj new` holds nothing yet, so it is muted.
export const EmptyWorkingCopy: Story = {
  args: {
    revision: makeStoryRevision({
      changeId: "wnlrostkvpzmqxyuwnlrostkvpzmqxyu",
      commitId: "1111111111111111111111111111111111111111",
      isWorkingCopy: true,
      isEmpty: true,
      files: [],
    }),
    isInitiallyExpanded: false,
  },
};

export const ConflictedAndDivergent: Story = {
  args: {
    revision: makeStoryRevision({
      changeId: "kxqpmzvyrstuwlnokxqpmzvyrstuwlno",
      commitId: "0123456789abcdef0123456789abcdef01234567",
      changeIdPrefixLength: 4,
      description: "Rebase the login form onto the new API",
      bookmarks: ["dev/login-form", "dev/login-form-v2"],
      hasConflict: true,
      isDivergent: true,
    }),
    isInitiallyExpanded: false,
  },
};
