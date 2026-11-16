import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";
import { useState } from "react";

import type { RevisionHistoryResponse } from "~/api";

import { RevisionList } from "./RevisionList";
import { makeStoryRevision } from "./revisionStoryData.ts";

const FORK_POINT = "9876543210fedcba9876543210fedcba98765432";

/** Renders the list at the Revisions panel's width, expanding revisions on click. */
const Wrapper = (props: {
  history: RevisionHistoryResponse | null | undefined;
  isPending: boolean;
  target: string | null;
}): ReactElement => {
  const [expandedChangeIds, setExpandedChangeIds] = useState<ReadonlySet<string>>(new Set<string>());
  const handleToggleRevision = (changeId: string): void => {
    setExpandedChangeIds((previous) => {
      const next = new Set(previous);
      if (next.has(changeId)) {
        next.delete(changeId);
      } else {
        next.add(changeId);
      }
      return next;
    });
  };
  return (
    <div
      style={{
        background: "var(--color-panel-solid)",
        display: "flex",
        flexDirection: "column",
        height: "420px",
        width: "320px",
      }}
    >
      <RevisionList
        history={props.history}
        isPending={props.isPending}
        target={props.target}
        expandedChangeIds={expandedChangeIds}
        onToggleRevision={handleToggleRevision}
        onSelectFile={() => {}}
      />
    </div>
  );
};

const meta = {
  title: "Custom/RevisionList",
  component: Wrapper,
} satisfies Meta<typeof Wrapper>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

// After a described change and `jj new`: the empty working copy above the described revision.
export const DescribedThenNew: Story = {
  args: {
    history: {
      revisions: [
        makeStoryRevision({
          changeId: "wnlrostkvpzmqxyuwnlrostkvpzmqxyu",
          commitId: "1111111111111111111111111111111111111111",
          isWorkingCopy: true,
          isEmpty: true,
          files: [],
        }),
        makeStoryRevision({
          changeId: "kxqpmzvyrstuwlnokxqpmzvyrstuwlno",
          commitId: "2222222222222222222222222222222222222222",
          description: "Add the login form",
          bookmarks: ["dev/login-form"],
        }),
      ],
      forkPoint: FORK_POINT,
    },
    isPending: false,
    target: "main@origin",
  },
};

export const Stack: Story = {
  args: {
    history: {
      revisions: [
        makeStoryRevision({
          changeId: "wnlrostkvpzmqxyuwnlrostkvpzmqxyu",
          commitId: "1111111111111111111111111111111111111111",
          isWorkingCopy: true,
        }),
        makeStoryRevision({
          changeId: "kxqpmzvyrstuwlnokxqpmzvyrstuwlno",
          commitId: "2222222222222222222222222222222222222222",
          description: "Validate the login form",
          bookmarks: ["dev/login-form"],
        }),
        makeStoryRevision({
          changeId: "zyxwvutsrqponmlkzyxwvutsrqponmlk",
          commitId: "3333333333333333333333333333333333333333",
          description: "Add the login form",
        }),
      ],
      forkPoint: FORK_POINT,
    },
    isPending: false,
    target: "main@origin",
  },
};

export const Loading: Story = {
  args: { history: undefined, isPending: true, target: "main@origin" },
};

export const NoRevisions: Story = {
  args: { history: null, isPending: false, target: "main@origin" },
};
