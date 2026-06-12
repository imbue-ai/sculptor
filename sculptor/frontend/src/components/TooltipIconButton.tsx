import { type ButtonProps, IconButton, Tooltip, type TooltipProps } from "@radix-ui/themes";
import type { PropsWithChildren, ReactElement, ReactNode } from "react";
import { forwardRef } from "react";

import type { PropsWithClassName } from "../common/Types.ts";
import { neutral } from "../common/Utils.ts";

type TooltipIconProps = {
  icon?: ReactElement;
  tooltipText: ReactNode;
  // defined in PopperContentProps
  side?: TooltipProps["side"];
  align?: TooltipProps["align"];
  /** Forwarded to Radix `Tooltip`. Use to delay the open of frequently-
   * hovered icons whose label isn't critical (e.g. mention shortcuts). */
  delayDuration?: TooltipProps["delayDuration"];
} & PropsWithChildren;

type TooltipIconButtonProps = TooltipIconProps &
  PropsWithClassName & {
    onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
    color?: ButtonProps["color"];
    variant?: ButtonProps["variant"];
    disabled?: ButtonProps["disabled"];
    loading?: ButtonProps["loading"];
    size?: ButtonProps["size"];
    style?: React.CSSProperties;
  };

export const TooltipIconButton = forwardRef<HTMLButtonElement, TooltipIconButtonProps>((props, ref): ReactElement => {
  const {
    className,
    tooltipText,
    icon,
    onClick,
    children,
    color,
    variant,
    // eslint-disable-next-line @typescript-eslint/naming-convention
    disabled,
    // eslint-disable-next-line @typescript-eslint/naming-convention
    loading,
    size,
    side,
    align,
    style,
    delayDuration,
    ...rest
  } = props;

  return (
    <Tooltip content={tooltipText} side={side} align={align} delayDuration={delayDuration}>
      <IconButton
        ref={ref}
        variant={variant ?? "ghost"}
        disabled={disabled ?? false}
        loading={loading ?? false}
        size={size ?? "1"}
        onClick={onClick}
        color={color ?? neutral}
        className={className}
        style={style}
        {...rest}
      >
        {icon ?? children}
      </IconButton>
    </Tooltip>
  );
});
