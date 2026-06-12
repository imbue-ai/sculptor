import { Flex, Link, Text } from "@radix-ui/themes";
import { TriangleAlertIcon } from "lucide-react";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";

import styles from "./WarningStatusBanner.module.scss";

type StatusBannerProps = {
  message: string;
  linkText?: string;
  onLinkClick?: () => void;
};

export const WarningStatusBanner = (props: StatusBannerProps): ReactElement => {
  return (
    <Flex
      direction="row"
      className={styles.banner}
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
              style={{ cursor: "pointer", textDecoration: "underline" }}
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
