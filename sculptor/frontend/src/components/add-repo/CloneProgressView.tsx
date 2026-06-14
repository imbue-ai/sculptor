import { Box, Dialog, Flex, Link, Progress, Text } from "@radix-ui/themes";
import type { ReactElement, ReactNode } from "react";

import { ElementIds } from "~/api";

import styles from "./CloneProgressView.module.scss";

type CloneTitleContentProps = {
  displayName: string;
  webUrl?: string;
};

/**
 * Inline "Cloning {name}…" content (the link + ellipsis). Returned without a
 * surrounding heading so the parent can wrap in `Dialog.Title` (inside a
 * Dialog) or a plain heading element (e.g. the onboarding wizard) without
 * Radix throwing about Dialog.Title used outside Dialog.Root.
 */
export const CloneTitleContent = ({ displayName, webUrl }: CloneTitleContentProps): ReactElement => {
  // Always-underlined at rest, color steps up on hover. Color is driven by
  // the CSS module rather than Radix Link's gray/highContrast props because
  // Sculptor's accent palette is gray — without a manual two-step the hover
  // is invisible. Falls back to plain text when we couldn't derive a
  // navigable URL from the clone source.
  const nameNode: ReactNode = webUrl ? (
    <Link
      href={webUrl}
      target="_blank"
      rel="noreferrer"
      underline="always"
      className={styles.repoLink}
      data-testid={ElementIds.ADD_REPO_CLONE_PROGRESS_LINK}
    >
      {displayName}
    </Link>
  ) : (
    displayName
  );

  return <>Cloning {nameNode}…</>;
};

/** Progress bar + helper text — the title-less body of the clone view. */
export const CloneProgressBody = (): ReactElement => {
  return (
    <>
      <Box>
        {/* `duration` fills the bar smoothly to ~100% over the expected clone
            time and then sits at full, mirroring the initial-load pattern in
            BackendStatusBoundary. Tuned to a typical 30s clone; longer clones
            still show a filled bar while the request stays in flight. */}
        <Progress duration="30s" size="2" />
      </Box>

      <Text size="2" color="gray">
        Usually takes about 30 seconds. Larger repos can take a few minutes.
      </Text>
    </>
  );
};

type CloneProgressViewProps = {
  /** "owner/repo" — rendered as a link when `webUrl` is set, plain text otherwise. */
  displayName: string;
  /** Public web URL for the repo (e.g. https://github.com/owner/repo). */
  webUrl?: string;
};

export const CloneProgressView = ({ displayName, webUrl }: CloneProgressViewProps): ReactElement => {
  return (
    <Flex direction="column" gap="4">
      <Dialog.Title mb="0">
        <CloneTitleContent displayName={displayName} webUrl={webUrl} />
      </Dialog.Title>

      <CloneProgressBody />
    </Flex>
  );
};
