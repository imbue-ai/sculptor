import type { LucideIcon } from "lucide-react";
import type { ComponentPropsWithRef, ReactElement, ReactNode } from "react";

import styles from "./IdentityPillButton.module.scss";

type IdentityPillButtonProps = Omit<ComponentPropsWithRef<"button">, "type" | "className"> & {
  icon: LucideIcon;
  /** The workspace's name for its checkout, in the mono font. */
  text: ReactNode;
  textClassName?: string;
};

/**
 * The button both identity pills are drawn as: an icon, the text, and any
 * trailing marks passed as children. Props a tooltip or hover-card trigger
 * passes down (handlers, ref, aria) land on the button.
 */
export const IdentityPillButton = ({
  icon: Icon,
  text,
  textClassName,
  children,
  ...buttonProps
}: IdentityPillButtonProps): ReactElement => (
  <button type="button" className={styles.pill} {...buttonProps}>
    <Icon size={12} className={styles.icon} />
    <span className={textClassName === undefined ? styles.text : `${styles.text} ${textClassName}`}>{text}</span>
    {children}
  </button>
);
