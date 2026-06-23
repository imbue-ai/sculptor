import { Badge, Text } from "@radix-ui/themes";
import { openExternal } from "@sculptor/plugin-sdk";
import type { ReactElement } from "react";

import type { LinearState } from "../linear/client.ts";
import { StateDot } from "./StateDot.tsx";

/**
 * A clickable badge linking to another Linear ticket — the panel's shape for a
 * "reference back to a ticket" (sub-issues today; parent/related/mentions
 * later). It shows the identifier and title, with a status dot when the ticket's
 * workflow state is known. `state` is optional precisely so the same badge can
 * front references we have the status for inline and ones whose status would be
 * fetched separately.
 */
export const TicketBadge = ({
  identifier,
  title,
  url,
  state,
}: {
  identifier: string;
  title: string;
  url: string;
  state: LinearState | null;
}): ReactElement => (
  <Badge
    size="2"
    variant="soft"
    color="gray"
    onClick={() => openExternal(url)}
    title={state ? `${identifier} · ${state.name}` : identifier}
    style={{ cursor: "pointer", maxWidth: "100%" }}
  >
    {state && <StateDot color={state.color} />}
    <Text style={{ fontFamily: "var(--code-font-family)", flexShrink: 0 }}>{identifier}</Text>
    <Text truncate>{title}</Text>
  </Badge>
);
