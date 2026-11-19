import { Skeleton, Tooltip } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";
import { useWorkspaceIdentityLabel } from "~/common/state/hooks/useWorkspaceIdentity.ts";

import { useCopyFeedback } from "./hooks/useCopyFeedback.ts";
import { IdentityPillButton } from "./IdentityPillButton.tsx";

/**
 * A git workspace's branch in the header. The visible label is the branch name,
 * so the aria-label spells out what pressing it does.
 */
export const GitIdentityPill = ({ workspaceId }: { workspaceId: string }): ReactElement | null => {
  const identityLabel = useWorkspaceIdentityLabel({ workspaceId });
  const { isCopied, copy } = useCopyFeedback();

  if (identityLabel.status === "LOADING") {
    return <Skeleton width="160px" height="16px" />;
  }

  if (identityLabel.status === "UNAVAILABLE") {
    return null;
  }

  return (
    <Tooltip
      content={isCopied ? "Copied!" : "Workspace branch — click to copy"}
      open={isCopied || undefined}
      side="bottom"
    >
      <IdentityPillButton
        icon={identityLabel.icon}
        text={identityLabel.text}
        onClick={() => copy(identityLabel.copyText)}
        aria-label={`Copy branch name ${identityLabel.text}`}
        data-testid={ElementIds.BRANCH_NAME}
      />
    </Tooltip>
  );
};
