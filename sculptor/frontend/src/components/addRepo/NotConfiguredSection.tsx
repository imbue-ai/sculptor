import { Code, Flex, Link, Text } from "@radix-ui/themes";
import type { ReactElement, ReactNode } from "react";

import { ElementIds } from "~/api";

import styles from "./NotConfiguredSection.module.scss";
import type { RemoteProvider } from "./SourceRadioCards.tsx";
import { PROVIDER_META } from "./utils/providerMeta.ts";

type NotConfiguredSectionProps = {
  provider: RemoteProvider;
  footer?: ReactNode;
};

export const NotConfiguredSection = ({ provider, footer }: NotConfiguredSectionProps): ReactElement => {
  const meta = PROVIDER_META[provider];

  return (
    <Flex direction="column" gap="3" data-testid={ElementIds.ADD_REPO_NOT_CONFIGURED}>
      <Text size="3" weight="bold">
        {meta.cliLabel} not configured
      </Text>
      <Text size="2" color="gray">
        Sculptor uses{" "}
        <Link href={meta.installUrl} target="_blank" rel="noreferrer">
          {meta.cliLabel}
        </Link>{" "}
        to list and clone your repos.
      </Text>
      <Code size="2" className={styles.snippet}>
        {meta.authCommand}
      </Code>
      {footer && <Flex align="start">{footer}</Flex>}
    </Flex>
  );
};
