import { Flex, Text } from "@radix-ui/themes";
import { AlertCircle } from "lucide-react";
import type { ReactElement, ReactNode } from "react";

/**
 * Centered message shown when there's nothing to render (no key, no ticket, an
 * error, or a miss). `action` is an optional control below the message — e.g. a
 * retry button.
 */
export const EmptyState = (props: { message: string; action?: ReactNode }): ReactElement => (
  <Flex direction="column" align="center" justify="center" gap="3" p="5" style={{ flexGrow: 1 }}>
    <AlertCircle size={20} color="var(--gray-8)" />
    <Text size="2" color="gray" align="center">
      {props.message}
    </Text>
    {props.action}
  </Flex>
);
