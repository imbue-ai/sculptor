import * as ToastPrimitive from "@radix-ui/react-toast";
import { Flex } from "@radix-ui/themes";
import { AlertTriangle, X } from "lucide-react";
import type React from "react";
import type { PropsWithChildren, ReactNode } from "react";
import { memo } from "react";

import { ElementIds } from "../api";
import { ToastType } from "../common/state/atoms/toasts.ts";
import { mergeClasses } from "../common/utils/classNames.ts";
import styles from "./Toast.module.scss";

export type ToastProps = {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  duration?: number;
  type?: ToastType;
  title?: string;
  description?: ReactNode;
  action?: {
    label: string;
    handleClick: () => void;
  };
} & PropsWithChildren;

// Memoized so the many always-mounted, closed <Toast> instances (notification,
// auto-update, and error toasts mounted unconditionally in AppShell) don't
// re-render on every unrelated React commit. Toast is a pure presentational
// wrapper with no hooks/context, so memo bails out whenever its props are
// referentially stable — see the always-mounted call sites, which pass stable
// callbacks/objects for exactly this reason. (SCU-1455)
export const Toast = memo(function Toast({
  children,
  open,
  onOpenChange,
  duration = 3000,
  type = ToastType.DEFAULT,
  title,
  description,
  action,
}: ToastProps): React.ReactElement {
  return (
    <ToastPrimitive.Root
      className={mergeClasses(styles.root, styles[type])}
      open={open}
      onOpenChange={onOpenChange}
      duration={duration}
      onClick={(e) => e.stopPropagation()}
      data-testid={ElementIds.TOAST}
    >
      <Flex className={styles.content} align="center" gap="2" justify="start">
        {type === ToastType.ERROR_PROMINENT && <AlertTriangle size={18} className={styles.prominentIcon} />}
        {title && <ToastPrimitive.Title className={styles.title}>{title}</ToastPrimitive.Title>}
        {description && (
          <ToastPrimitive.Description className={styles.description}>{description}</ToastPrimitive.Description>
        )}
        {children}
        {action && (
          <ToastPrimitive.Action
            className={styles.action}
            altText={action.label}
            onClick={action.handleClick}
            data-testid={ElementIds.TOAST_ACTION_BUTTON}
          >
            {action.label}
          </ToastPrimitive.Action>
        )}
      </Flex>
      <ToastPrimitive.Close className={styles.close} data-testid={ElementIds.TOAST_CLOSE_BUTTON}>
        <X size={16} />
      </ToastPrimitive.Close>
    </ToastPrimitive.Root>
  );
});

export const ToastProvider = ({ children }: PropsWithChildren): React.ReactElement => {
  return (
    <ToastPrimitive.Provider swipeDirection="right">
      {children}
      <ToastPrimitive.Viewport className={styles.viewport} />
    </ToastPrimitive.Provider>
  );
};
