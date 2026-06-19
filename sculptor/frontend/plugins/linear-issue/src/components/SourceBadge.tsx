import { Badge } from "@radix-ui/themes";
import { GitBranch, GitPullRequest, type LucideIcon, Pin } from "lucide-react";
import type { ReactElement } from "react";

import type { TicketSource } from "../linear/sources.ts";

const SOURCE_CONFIG: Record<TicketSource, { label: string; Icon: LucideIcon }> = {
  branch: { label: "Branch", Icon: GitBranch },
  pr: { label: "PR", Icon: GitPullRequest },
  pinned: { label: "Pinned", Icon: Pin },
};

/** A chip explaining where a ticket came from; accented for the primary one. */
export const SourceBadge = ({ source, primary = false }: { source: TicketSource; primary?: boolean }): ReactElement => {
  const { label, Icon } = SOURCE_CONFIG[source];
  return (
    <Badge size="1" variant={primary ? "solid" : "soft"} color={primary ? "iris" : "gray"}>
      <Icon size={11} />
      {label}
    </Badge>
  );
};
