import { IconButton, Tooltip } from "@radix-ui/themes";
import { Zap } from "lucide-react";
import type { ReactElement } from "react";

import { ElementIds } from "../api";

type FastModeToggleProps = {
  isActive: boolean;
  onToggle: () => void;
};

export const FastModeToggle = ({ isActive, onToggle }: FastModeToggleProps): ReactElement => (
  <Tooltip content={isActive ? "Disable fast mode" : "Enable fast mode"}>
    <IconButton
      variant="ghost"
      size="3"
      onClick={onToggle}
      aria-label="Toggle fast mode"
      data-testid={ElementIds.FAST_MODE_TOGGLE}
      data-active={isActive}
      style={{ margin: 0, color: isActive ? "var(--button-primary-bg)" : undefined }}
    >
      <Zap size={16} />
    </IconButton>
  </Tooltip>
);
