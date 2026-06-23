import type { HTMLProps, PropsWithChildren, ReactElement } from "react";

import { mergeClasses, optional } from "../common/Utils.ts";
import styles from "./Code.module.scss";

export const Code = (
  props: PropsWithChildren & {
    isUnderlined?: boolean;
    isClickable?: boolean;
    size?: "1" | "2" | "3" | "4" | "5" | "6";
  } & Omit<HTMLProps<HTMLDivElement>, "size">,
): ReactElement => {
  const { className, children, isUnderlined, isClickable, size: maybeSize, style, ...rest } = props;
  const combinedClassName = mergeClasses(
    className,
    styles.code,
    optional(!!isUnderlined, styles.underlined),
    optional(!!isClickable, styles.clickable),
  );
  const size = maybeSize ?? "2";

  return (
    <span className={combinedClassName} style={{ ...style, fontSize: `var(--font-size-${size})` }} {...rest}>
      {children}
    </span>
  );
};
