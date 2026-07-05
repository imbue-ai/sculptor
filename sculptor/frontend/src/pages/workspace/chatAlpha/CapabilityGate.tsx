import { type ButtonProps, IconButton, Tooltip, type TooltipProps } from "@radix-ui/themes";
import type { ReactElement, ReactNode } from "react";

import { type ElementIds } from "../../../api";
import { useCapabilityGate } from "../../../common/hooks/useCapabilityGate.ts";
import { neutral } from "../../../common/Utils.ts";

type CapabilityGateProps = {
  /** The narrow capability value, e.g. `useTaskSupportsInterruption(taskId)`. */
  capabilityValue: boolean | undefined;
  /** Stable test hook for the disabled treatment. */
  elementId: ElementIds;
  /** The enabled affordance — rendered verbatim when the capability holds. */
  children: ReactNode;
  /** Icon for the disabled placeholder button; mirror the enabled icon. */
  disabledIcon: ReactElement;
  size?: ButtonProps["size"];
  variant?: ButtonProps["variant"];
  color?: ButtonProps["color"];
  className?: string;
  /** Applied to the disabled placeholder button, e.g. `{ margin: 0 }` to match
   *  the enabled control's spacing. */
  style?: React.CSSProperties;
  side?: TooltipProps["side"];
};

/**
 * Render an interactive affordance, replacing it with a disabled-with-tooltip
 * placeholder when the active task's harness lacks the underlying capability.
 *
 * The enabled branch renders `children` untouched. The disabled branch renders
 * a non-interactive `IconButton` wrapped in a `Tooltip` carrying the
 * standardized copy. Radix `Tooltip` does not fire on a `disabled` button (it
 * sets `pointer-events: none`), so the hover target and the `data-testid` live
 * on a wrapping span — the same handling `TooltipIconButton` uses.
 */
export const CapabilityGate = ({
  capabilityValue,
  elementId,
  children,
  disabledIcon,
  size,
  variant,
  color,
  className,
  style,
  side,
}: CapabilityGateProps): ReactElement => {
  const gate = useCapabilityGate(capabilityValue, elementId);
  if (gate.enabled) {
    return <>{children}</>;
  }
  return (
    <Tooltip content={gate.tooltip} side={side}>
      <span data-testid={gate.elementId} style={{ display: "inline-flex" }}>
        <IconButton
          disabled
          aria-disabled
          variant={variant ?? "ghost"}
          size={size ?? "1"}
          color={color ?? neutral}
          className={className}
          style={style}
        >
          {disabledIcon}
        </IconButton>
      </span>
    </Tooltip>
  );
};
