import { IconButton, Tooltip } from "@radix-ui/themes";
import { Zap } from "lucide-react";
import type { ReactElement } from "react";

import { ElementIds } from "../api";

type FastModeToggleProps = {
  isActive: boolean;
  onToggle: () => void;
  /**
   * Why fast mode is unavailable, when it is. The toggle then renders inactive
   * and disabled instead of reflecting the stored preference, so it never
   * promises a speed the turn will not launch with. The preference itself is
   * left untouched and applies again once the reason clears.
   */
  suppressedReason?: string | null;
};

export const FastModeToggle = ({ isActive, onToggle, suppressedReason }: FastModeToggleProps): ReactElement => {
  const isSuppressed = suppressedReason != null;
  const isShownActive = isActive && !isSuppressed;

  const button = (
    <IconButton
      variant="ghost"
      size="3"
      onClick={onToggle}
      disabled={isSuppressed}
      aria-disabled={isSuppressed || undefined}
      aria-label="Toggle fast mode"
      data-testid={ElementIds.FAST_MODE_TOGGLE}
      data-active={isShownActive}
      data-suppressed={isSuppressed}
      style={{ margin: 0, color: isShownActive ? "var(--button-primary-bg)" : undefined }}
    >
      <Zap size={16} />
    </IconButton>
  );

  return (
    <Tooltip content={suppressedReason ?? (isActive ? "Disable fast mode" : "Enable fast mode")}>
      {/* Radix Tooltip does not fire on a disabled button (it sets
          pointer-events: none), so the suppressed branch hangs the hover
          target on a wrapping span — the same handling CapabilityGate uses. */}
      {isSuppressed ? <span style={{ display: "inline-flex" }}>{button}</span> : button}
    </Tooltip>
  );
};
