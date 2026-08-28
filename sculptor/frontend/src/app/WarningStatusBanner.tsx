import { Flex, Link, Text } from "@radix-ui/themes";
import { TriangleAlertIcon } from "lucide-react";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";

import styles from "./WarningStatusBanner.module.scss";

type WarningStatusBannerProps = {
  message: string;
  // "error" (default) is the red alert style for states needing user action;
  // "warning" is a softer amber style for degraded-but-recovering states.
  tone?: "error" | "warning";
  linkText?: string;
  onLinkClick?: () => void;
};

export const WarningStatusBanner = (props: WarningStatusBannerProps): ReactElement => {
  return (
    <Flex
      direction="row"
      className={`${styles.banner} ${props.tone === "warning" ? styles.warningTone : ""}`}
      justify="center"
      p="3"
      gapX="2"
      align="center"
      data-testid={ElementIds.WARNING_STATUS_BANNER}
    >
      <Flex className={styles.alert} p="1">
        <TriangleAlertIcon />
      </Flex>
      <Text>
        {props.message}
        {props.linkText && props.onLinkClick && (
          <>
            {" "}
            <Link
              onClick={(e) => {
                e.preventDefault();
                props.onLinkClick?.();
              }}
              underline="always"
              className={styles.link}
              data-testid={ElementIds.WARNING_STATUS_BANNER_LINK}
            >
              {props.linkText}
            </Link>
          </>
        )}
      </Text>
    </Flex>
  );
};
