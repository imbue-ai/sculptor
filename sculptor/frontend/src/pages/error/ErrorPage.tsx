import { Box, Button, Flex, Text } from "@radix-ui/themes";
import * as Sentry from "@sentry/react";
import type { ReactElement } from "react";
import { useEffect } from "react";

import { ElementIds } from "../../api";
import SculptorLogo from "../../assets/logos/envy.svg";
import { TitleBar } from "../../components/TitleBar.tsx";
import styles from "./ErrorPage.module.scss";

type ErrorPageProps = {
  error?: unknown;
  headerText?: string | ReactElement;
  errorMessage?: string;
  isCapturingErrorWithSentry?: boolean;
  onClearCustomBackend?: () => void;
  isCustomBackendCleared?: boolean;
};

export const ErrorPage = (props: ErrorPageProps): ReactElement => {
  let errorText: string | undefined;

  // running in an effect to prevent multiple captures
  useEffect(() => {
    if (props.isCapturingErrorWithSentry) {
      // TODO (PROD-2166): Verify that this works
      Sentry.captureException(props.error);
    }
  }, [props.error, props.isCapturingErrorWithSentry]);

  if (props.error instanceof Error) {
    errorText = props.error.stack;
  } else if (props.error) {
    errorText = JSON.stringify(props.error, null, 2);
  } else {
    errorText = props.errorMessage;
  }

  const handleCopyError = (): void => {
    if (!errorText) return;
    navigator.clipboard.writeText(errorText);
  };

  return (
    <Flex
      justify="center"
      width="100vw"
      height="var(--app-height)"
      className={styles.container}
      data-testid={ElementIds.BACKEND_ERROR_PAGE}
    >
      <Flex
        direction="column"
        height="var(--app-height)"
        width="80%"
        minHeight="0"
        align="center"
        justify="center"
        gap="4"
      >
        <Flex justify="center" align="center" mt="5">
          <TitleBar />
          <img src={SculptorLogo} className={styles.logo} alt="Sculptor Logo" />
        </Flex>
        <Text className={styles.text}>
          {props.headerText
            ? props.headerText
            : "Oops! That is embarrassing. An unexpected error has occurred. Try restarting the app or contacting us if the problem persists."}
        </Text>
        {!!errorText && errorText.trim() && (
          <>
            <Flex gap="2" mx="auto">
              <Button variant="soft" onClick={handleCopyError}>
                Copy Error to Clipboard
              </Button>
              {props.onClearCustomBackend && (
                <Button
                  variant="soft"
                  color="red"
                  onClick={props.onClearCustomBackend}
                  disabled={props.isCustomBackendCleared}
                >
                  {props.isCustomBackendCleared
                    ? "Custom backend command cleared — restart the app to use the built-in backend"
                    : "Clear Custom Backend Command"}
                </Button>
              )}
            </Flex>
            <Box minHeight="0" mt="2" mb="5" className={styles.errorBox}>
              <div className={styles.errorScroll}>
                <Box px="4" py="1">
                  <pre className={styles.errorText}>{errorText}</pre>
                </Box>
              </div>
            </Box>
          </>
        )}
      </Flex>
    </Flex>
  );
};
