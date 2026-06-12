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
      style={isActive ? { color: "var(--button-primary-bg)", margin: 0 } : { margin: 0 }}
    >
      <Zap size={16} />
    </IconButton>
  </Tooltip>
);
