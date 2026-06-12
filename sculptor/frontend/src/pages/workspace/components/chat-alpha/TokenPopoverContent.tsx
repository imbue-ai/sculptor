import { Flex, Text } from "@radix-ui/themes";
import type { ReactElement } from "react";

import type { TurnMetrics } from "~/api";
import { ElementIds } from "~/api";

import styles from "./TokenPopoverContent.module.scss";

type TokenPopoverContentProps = {
  turnMetrics?: TurnMetrics | null;
  /** When set, the popover shows a single "Context" row instead of per-turn token breakdown. */
  turnContextTokens?: number | null;
  autoCompactThreshold?: number | null;
};

export const TokenPopoverContent = ({
  turnMetrics,
  turnContextTokens,
  autoCompactThreshold,
}: TokenPopoverContentProps): ReactElement => {
  const rows: Array<{ label: string; value: string }> = [];
  if (turnMetrics != null) {
    rows.push({ label: "Input", value: (turnMetrics.inputTokens ?? 0).toLocaleString() });
    rows.push({ label: "Output", value: (turnMetrics.outputTokens ?? 0).toLocaleString() });
    if (turnMetrics.reasoningTokens != null && turnMetrics.reasoningTokens > 0) {
      rows.push({ label: "Reasoning", value: turnMetrics.reasoningTokens.toLocaleString() });
    }
  }

  // CAPABILITY-GAP: supportsCompaction — the "Context" row displays the auto-compact threshold; harnesses without compaction (pi) never produce a threshold so the row already collapses, but the surrounding chrome should treat compaction as a per-harness capability rather than relying on null thresholds.
  if (turnContextTokens != null && turnContextTokens > 0 && autoCompactThreshold != null && autoCompactThreshold > 0) {
    rows.push({
      label: "Context",
      value: `${turnContextTokens.toLocaleString()} / ${autoCompactThreshold.toLocaleString()}`,
    });
  }

  return (
    <div data-testid={ElementIds.TOKEN_POPOVER}>
      {rows.map((row, i) => (
        <Flex
          key={row.label}
          align="center"
          justify="between"
          gap="4"
          className={styles.row}
          style={{
            borderBottom: i < rows.length - 1 ? "1px solid var(--gray-3)" : "none",
          }}
        >
          <Text size="1" style={{ color: "var(--gray-9)" }}>
            {row.label}
          </Text>
          <Text size="1" weight="medium">
            {row.value}
          </Text>
        </Flex>
      ))}
    </div>
  );
};
