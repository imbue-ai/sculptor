import { Box, Button, Flex } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";

import { useTerminal } from "../../workspace/panels/useTerminal";

type PiLoginTerminalProps = {
  loginId: string;
  onDone: () => void;
};

/**
 * The interactive pi /login (or /logout) session, embedded inline in the Providers
 * detail pane. Reuses the workspace terminal hook pointed at the login PTY's
 * WebSocket; Done tears the session down (see PiProvidersArea).
 */
export const PiLoginTerminal = ({ loginId, onDone }: PiLoginTerminalProps): ReactElement => {
  const { terminalContainerRef } = useTerminal({
    terminalPath: `/api/v1/pi/login/${loginId}/ws`,
    isVisible: true,
    fontSize: 13,
    lineHeight: 1.1,
  });

  return (
    <Flex direction="column" gap="2" data-testid={ElementIds.PI_LOGIN_TERMINAL}>
      <Box
        ref={terminalContainerRef}
        style={{
          height: "320px",
          minHeight: 0,
          overflow: "hidden",
          backgroundColor: "var(--gray-2)",
          borderRadius: "var(--radius-2)",
          padding: "var(--space-2)",
        }}
      />
      <Flex justify="end">
        <Button variant="soft" onClick={onDone} data-testid={ElementIds.PI_LOGIN_DONE_BUTTON}>
          Done
        </Button>
      </Flex>
    </Flex>
  );
};
