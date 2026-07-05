import { Flex } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { getTitleBarLeftPadding } from "../electron/platform.ts";
import styles from "./TitleBar.module.scss";

type TitleBarProps = {
  className?: string;
};

export const TitleBar = ({ className }: TitleBarProps): ReactElement => {
  return (
    <Flex
      position="absolute"
      top="0"
      left="0"
      width="100%"
      pl={getTitleBarLeftPadding(false)}
      height="var(--titlebar-height)"
      align="center"
      justify="end"
      pr="10px"
      className={`${styles.draggable}${className ? ` ${className}` : ""}`}
    />
  );
};
