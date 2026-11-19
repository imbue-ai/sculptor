import { Badge, Code, Flex, Skeleton, Text } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement, ReactNode } from "react";

import type { WorkspaceJjStateInfo } from "~/api";
import { ElementIds } from "~/api";
import { workspaceJjStateAtomFamily } from "~/common/state/atoms/workspaceJjState.ts";
import { useWorkspace } from "~/common/state/hooks/useWorkspace.ts";
import { useWorkspaceIdentityLabel } from "~/common/state/hooks/useWorkspaceIdentity.ts";
import { shortChangeId } from "~/common/utils/jjChangeId.ts";
import { HoverCard } from "~/components/HoverCard.tsx";

import { useCopyFeedback } from "./hooks/useCopyFeedback.ts";
import { IdentityPillButton } from "./IdentityPillButton.tsx";
import styles from "./JjIdentityPill.module.scss";

const pluralize = (count: number, noun: string): string => `${count} ${noun}${count === 1 ? "" : "s"}`;

const flagsOf = (jjState: WorkspaceJjStateInfo): Array<string> =>
  [
    { flag: "empty", isSet: jjState.isWorkingCopyEmpty },
    { flag: "conflict", isSet: jjState.hasConflict },
    { flag: "divergent", isSet: jjState.isDivergent },
    { flag: "stale", isSet: jjState.isWorkingCopyStale },
  ]
    .filter(({ isSet }) => isSet)
    .map(({ flag }) => flag);

const CardRow = ({ label, children }: { label: string; children: ReactNode }): ReactElement => (
  <Flex gap="3" align="baseline">
    <Text size="1" color="gray" className={styles.cardLabel}>
      {label}
    </Text>
    <Text size="1" as="div" className={styles.cardValue}>
      {children}
    </Text>
  </Flex>
);

// Described revisions above the primary bookmark; only a workspace with a bookmark has any.
type RevisionsAhead = { count: number; bookmark: string };

const JjIdentityCard = ({
  jjState,
  ahead,
  requestedBookmark,
  target,
  copyHint,
}: {
  jjState: WorkspaceJjStateInfo | null;
  ahead: RevisionsAhead | null;
  requestedBookmark: string | null;
  target: string | null;
  copyHint: string;
}): ReactElement => {
  const bookmarks = jjState?.bookmarks ?? [];
  const primaryBookmark = jjState?.primaryBookmark ?? null;
  const flags = jjState === null ? [] : flagsOf(jjState);
  return (
    <Flex direction="column" gap="2" className={styles.card} data-testid={ElementIds.JJ_IDENTITY_CARD}>
      <CardRow label="Bookmarks">
        {bookmarks.length > 0 ? (
          <Flex wrap="wrap" gap="1">
            {bookmarks.map((bookmark) => (
              <Code key={bookmark} size="1" color="gray" variant={bookmark === primaryBookmark ? "soft" : "outline"}>
                {bookmark}
              </Code>
            ))}
          </Flex>
        ) : requestedBookmark !== null ? (
          <>
            None yet. Sculptor sets{" "}
            <Code size="1" color="gray">
              {requestedBookmark}
            </Code>{" "}
            on the newest described revision.
          </>
        ) : (
          "None"
        )}
      </CardRow>
      {ahead !== null && (
        <CardRow label="Ahead">
          {pluralize(ahead.count, "described revision")} above{" "}
          <Code size="1" color="gray">
            {ahead.bookmark}
          </Code>
        </CardRow>
      )}
      {jjState !== null && (
        <>
          <CardRow label="Change">
            <span className={styles.mono}>
              <strong>{jjState.workingCopyChangeId.slice(0, jjState.workingCopyChangeIdPrefixLength)}</strong>
              <span className={styles.changeIdRest}>
                {jjState.workingCopyChangeId.slice(jjState.workingCopyChangeIdPrefixLength)}
              </span>
            </span>
          </CardRow>
          <CardRow label="Description">
            {jjState.workingCopyDescription || <span className={styles.muted}>(no description set)</span>}
          </CardRow>
          {flags.length > 0 && (
            <CardRow label="Flags">
              <Flex wrap="wrap" gap="1">
                {flags.map((flag) => (
                  <Badge key={flag} size="1" color={flag === "conflict" ? "red" : "gray"} variant="soft">
                    {flag}
                  </Badge>
                ))}
              </Flex>
            </CardRow>
          )}
        </>
      )}
      <CardRow label="Target">{target ?? <span className={styles.muted}>No target bookmark</span>}</CardRow>
      <Text size="1" color="gray">
        {copyHint}
      </Text>
    </Flex>
  );
};

/**
 * A jj workspace's identity in the header: its primary bookmark, a count of its
 * other bookmarks, and how many described revisions sit above the bookmark. With
 * no bookmark it shows the requested name ghosted, or else the working copy's
 * change id and description. Clicking copies the bookmark, or the change id when
 * there is none; the hover card lists the rest.
 */
export const JjIdentityPill = ({ workspaceId }: { workspaceId: string }): ReactElement | null => {
  const jjState = useAtomValue(workspaceJjStateAtomFamily(workspaceId));
  const workspace = useWorkspace(workspaceId);
  const identityLabel = useWorkspaceIdentityLabel({ workspaceId });
  const { isCopied, copy } = useCopyFeedback();

  if (identityLabel.status === "LOADING") {
    return <Skeleton width="160px" height="16px" />;
  }

  if (identityLabel.status === "UNAVAILABLE") {
    return null;
  }

  const primaryBookmark = jjState?.primaryBookmark ?? null;
  const otherBookmarkCount = (jjState?.bookmarks.length ?? 0) - (primaryBookmark === null ? 0 : 1);
  const ahead: RevisionsAhead | null =
    primaryBookmark !== null && jjState !== null && jjState.unbookmarkedRevisionCount > 0
      ? { count: jjState.unbookmarkedRevisionCount, bookmark: primaryBookmark }
      : null;
  const changeId =
    jjState === null
      ? null
      : shortChangeId({
          changeId: jjState.workingCopyChangeId,
          uniquePrefixLength: jjState.workingCopyChangeIdPrefixLength,
        });
  // What a click copies, named for the aria-label and the card's hint.
  const copiedThing =
    primaryBookmark !== null
      ? { noun: "bookmark", name: primaryBookmark }
      : changeId !== null
        ? { noun: "change id", name: `${changeId.uniquePrefix}${changeId.rest}` }
        : { noun: "bookmark name", name: identityLabel.text };

  // Without a bookmark or a requested name, the change id names the workspace.
  const shownChangeId = identityLabel.isTentative || primaryBookmark !== null ? null : changeId;
  const text =
    shownChangeId === null ? (
      identityLabel.text
    ) : (
      <>
        <strong>{shownChangeId.uniquePrefix}</strong>
        <span className={styles.changeIdRest}>{shownChangeId.rest}</span>
      </>
    );

  return (
    <HoverCard
      side="bottom"
      align="start"
      trigger={
        <IdentityPillButton
          icon={identityLabel.icon}
          text={text}
          textClassName={identityLabel.isTentative ? styles.tentative : undefined}
          onClick={() => copy(identityLabel.copyText)}
          aria-label={`Copy ${copiedThing.noun} ${copiedThing.name}`}
          data-testid={ElementIds.JJ_IDENTITY_PILL}
        >
          {shownChangeId !== null && jjState?.workingCopyDescription && (
            <span className={styles.description}>{jjState.workingCopyDescription}</span>
          )}
          {otherBookmarkCount > 0 && (
            <span className={styles.moreBookmarks} data-testid={ElementIds.JJ_IDENTITY_MORE_BOOKMARKS}>
              +{otherBookmarkCount}
            </span>
          )}
          {ahead !== null && (
            <span className={styles.unbookmarked} data-testid={ElementIds.JJ_UNBOOKMARKED_MARKER}>
              ↑{ahead.count}
            </span>
          )}
          {jjState?.hasConflict && (
            <Badge size="1" color="red" variant="soft">
              conflict
            </Badge>
          )}
        </IdentityPillButton>
      }
      content={
        <JjIdentityCard
          jjState={jjState}
          ahead={ahead}
          requestedBookmark={workspace?.requestedBranchName ?? null}
          target={workspace?.targetBranch ?? null}
          copyHint={isCopied ? "Copied!" : `Click to copy the ${copiedThing.noun}`}
        />
      }
    />
  );
};
