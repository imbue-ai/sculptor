import { Flex, Select, Text } from "@radix-ui/themes";
import { Brain } from "lucide-react";
import { memo, type ReactElement } from "react";

import { EffortLevel, ElementIds } from "~/api";

import { EFFORT_DISPLAY_NAMES, EFFORT_OPTIONS } from "./effortConstants.ts";
import styles from "./EffortSelector.module.scss";

const EFFORT_FILL_PERCENT: Record<EffortLevel, number> = {
  [EffortLevel.LOW]: 20,
  [EffortLevel.MEDIUM]: 40,
  [EffortLevel.HIGH]: 60,
  [EffortLevel.XHIGH]: 80,
  [EffortLevel.MAX]: 100,
};

type EffortSelectorProps = {
  effort: EffortLevel;
  onEffortChange: (effort: EffortLevel) => void;
};

// Memoized so it bails out of ChatInput's re-renders (effort is atom-backed
// and onEffortChange is a stable useCallback).
export const EffortSelector = memo(
  ({ effort, onEffortChange }: EffortSelectorProps): ReactElement => (
    <Select.Root size="1" value={effort} onValueChange={onEffortChange}>
      <Select.Trigger
        className={styles.trigger}
        variant="ghost"
        data-testid={ElementIds.EFFORT_SELECTOR}
        data-value={effort}
      >
        <Flex align="center" gap="1">
          <Brain size={14} />
          <span className={styles.fillBar}>
            <span className={styles.fillBarInner} style={{ height: `${EFFORT_FILL_PERCENT[effort]}%` }} />
          </span>
        </Flex>
      </Select.Trigger>
      <Select.Content position="popper" sideOffset={5}>
        <Select.Group>
          <Select.Label>Effort level</Select.Label>
          {EFFORT_OPTIONS.map((level) => (
            <Select.Item key={level} value={level} data-testid={ElementIds.EFFORT_SELECTOR_OPTION}>
              <Text size="1">{EFFORT_DISPLAY_NAMES[level]}</Text>
            </Select.Item>
          ))}
        </Select.Group>
      </Select.Content>
    </Select.Root>
  ),
);
