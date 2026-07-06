import { Box, Flex, Progress, Text } from "@radix-ui/themes";
import { useAtom, useSetAtom } from "jotai";
import type { PropsWithChildren, ReactElement } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ElementIds, getHealthCheck } from "~/api";
import { useInterval } from "~/common/useInterval.ts";

import SculptorLogoAndTitle from "../assets/logos/sculptor_logo_and_title.svg";
import {
  backendStatusAtom,
  hasBackendStartedSuccessfullyAtom,
  healthCheckDataAtom,
} from "../common/state/atoms/backend.ts";
import { ErrorPage } from "../pages/error/ErrorPage.tsx";
import type { AnyBackendStatus, BackendStatus } from "../shared/types.ts";
import styles from "./BackendStatusBoundary.module.scss";
import { TitleBar } from "./TitleBar.tsx";

// Once the renderer enters ``shutting_down``, the boundary locks the state
// (see ``maybeSetBackendStatus``). If the Electron main process never
// transitions out — e.g. ``autoUpdater.quitAndInstall()`` failed and the
// app silently stays alive — the user is left on an indefinite progress
// bar. After this stall timeout elapses we swap the spinner for a
// recovery message so the user knows to relaunch the app manually.
const SHUTDOWN_STALL_TIMEOUT_MS = 30_000;

// How often we poll the backend health check endpoint while the app is up.
const HEALTH_CHECK_INTERVAL_MS = 3_000;

const getShutdownStallTimeoutMs = (): number => {
  // Integration tests inject a shorter timeout via localStorage so they
  // don't have to wait the full production duration.
  try {
    const override = window.localStorage?.getItem("__sculptor_shutdown_stall_timeout_ms");
    if (override !== null && override !== undefined) {
      const parsed = parseInt(override, 10);
      if (Number.isFinite(parsed) && parsed > 0) return parsed;
    }
  } catch {
    // localStorage may be unavailable in some sandboxes; fall through to default.
  }
  return SHUTDOWN_STALL_TIMEOUT_MS;
};

const isBackendStatusExited = (state: AnyBackendStatus): state is BackendStatus<"exited"> => {
  return state.status === "exited";
};

const isBackendStatusError = (state: AnyBackendStatus): state is BackendStatus<"error"> => {
  return state.status === "error";
};

type BackendStatusBoundaryProps = {
  setIsBackendAPIReady?: (isReady: boolean) => void;
};

export const BackendStatusBoundary = (props: PropsWithChildren<BackendStatusBoundaryProps>): ReactElement => {
  const [backendStatus, setBackendStatus] = useAtom(backendStatusAtom);
  const [hasStartedSuccessfully, setHasStartedSuccessfully] = useAtom(hasBackendStartedSuccessfullyAtom);
  const setHealthCheckData = useSetAtom(healthCheckDataAtom);
  const abortControllerRef = useRef<AbortController | null>(null);

  const [isCustomCommandMode, setIsCustomCommandMode] = useState<boolean>(false);
  const [isShutdownStalled, setIsShutdownStalled] = useState<boolean>(false);

  useEffect(() => {
    window.sculptor
      ?.isCustomCommandMode?.()
      .then(setIsCustomCommandMode)
      .catch((error) => {
        console.warn("Failed to read custom-command-mode flag; assuming default.", error);
      });
  }, []);

  const [isCustomBackendCleared, setIsCustomBackendCleared] = useState<boolean>(false);

  const handleClearCustomBackend = useCallback(async () => {
    await window.sculptor?.setCustomBackendSettings?.({ customBackendCommand: "" });
    setIsCustomBackendCleared(true);
  }, []);

  const { setIsBackendAPIReady } = props;
  const maybeSetBackendStatus = useCallback(
    (newStatus: AnyBackendStatus): void => {
      let isSet = false;
      // We use the functional form of setState to avoid circular dependencies.
      setBackendStatus((prevStatus) => {
        if (prevStatus.status === "shutting_down") {
          // Once shutting down, always stay shutting down. Ignore any other updates.
          return prevStatus;
        }
        isSet = true;
        return newStatus;
      });

      if (isSet) {
        if (newStatus.status === "running") {
          setHasStartedSuccessfully(true);
        }

        const isBackendAPIReady = newStatus.status === "running" || newStatus.status === "warning";
        setIsBackendAPIReady?.(isBackendAPIReady);
      }
    },
    [setBackendStatus, setHasStartedSuccessfully, setIsBackendAPIReady],
  );

  useEffect(() => {
    if (!window.sculptor) return;

    const loadInitialState = async (): Promise<void> => {
      if (!window.sculptor) return;

      try {
        const initialState = await window.sculptor.getCurrentBackendStatus();
        maybeSetBackendStatus(initialState);
      } catch (error) {
        console.error("Failed to load initial backend state:", error);
      }
    };

    loadInitialState();

    const handleStateChange = (state: AnyBackendStatus): void => {
      maybeSetBackendStatus(state);
    };

    window.sculptor.onBackendStatusChange(handleStateChange);

    return (): void => {
      window.sculptor?.removeBackendStatusListener?.();
    };
  }, [maybeSetBackendStatus]);

  const performHealthCheck = useCallback(async (): Promise<void> => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();
    const { signal } = abortControllerRef.current;

    try {
      const { data: healthData } = await getHealthCheck({
        meta: { skipWsAck: true, signal },
      });

      if (signal.aborted) return;

      // mark a successful start if we haven't yet
      if (!hasStartedSuccessfully) {
        setHasStartedSuccessfully(true);
      }

      setHealthCheckData(healthData);

      if (healthData && healthData.freeDiskGb < healthData.minFreeDiskGb) {
        maybeSetBackendStatus({
          status: "warning",
          payload: {
            message:
              "Insufficient free space (" +
              Number(healthData.freeDiskGb).toFixed(2) +
              " GB free, " +
              healthData.minFreeDiskGb +
              " GB required) You must free up additional space before creating new agents or messages",
          },
        });
      } else if (healthData && healthData.freeDiskGb < healthData.freeDiskGbWarnLimit) {
        maybeSetBackendStatus({
          status: "warning",
          payload: {
            message:
              "Low disk space warning (only " +
              Number((healthData.freeDiskGbWarnLimit - healthData.freeDiskGb).toFixed(2)) +
              " GB free) Please free up some space (no new agents or messages will be allowed when free space <= " +
              healthData.minFreeDiskGb +
              " GB).",
          },
        });
      } else {
        maybeSetBackendStatus({
          status: "running",
          payload: { message: "Received health check response from backend." },
        });
      }
    } catch {
      // Silently ignore aborted requests — they don't indicate backend issues.
      if (signal.aborted) return;

      // if we've never started, exit and stay in the loading state
      if (!hasStartedSuccessfully) return;

      maybeSetBackendStatus({
        status: "unresponsive",
        payload: {
          message: "The backend process is down or unresponsive. Please restart the application.",
        },
      });
    }
  }, [maybeSetBackendStatus, hasStartedSuccessfully, setHasStartedSuccessfully, setHealthCheckData]);

  useEffect(() => {
    if (backendStatus.status === "shutting_down") {
      return;
    }

    performHealthCheck();

    return (): void => {
      abortControllerRef.current?.abort();
    };
  }, [backendStatus.status, performHealthCheck]);

  useInterval(() => {
    if (backendStatus.status !== "shutting_down") {
      performHealthCheck();
    }
  }, HEALTH_CHECK_INTERVAL_MS);

  // Clear the stalled flag as soon as we leave ``shutting_down``. Adjusting
  // state during render (with a previous-value guard) keeps the reset on the
  // same render that observes the status change, instead of the extra render
  // an effect would add.
  const [prevBackendStatusForStall, setPrevBackendStatusForStall] = useState(backendStatus.status);
  if (prevBackendStatusForStall !== backendStatus.status) {
    setPrevBackendStatusForStall(backendStatus.status);
    if (backendStatus.status !== "shutting_down" && isShutdownStalled) {
      setIsShutdownStalled(false);
    }
  }

  // SCU-403: ``autoUpdater.quitAndInstall()`` can fail silently (e.g. when
  // Squirrel's cached download has been purged). The boundary locks into
  // ``shutting_down`` once entered, so without this safety net the user
  // sees an indefinite progress bar. After the stall timeout we surface a
  // recovery message instead.
  useEffect(() => {
    if (backendStatus.status !== "shutting_down") {
      return;
    }
    const timeoutId = setTimeout(() => {
      setIsShutdownStalled(true);
    }, getShutdownStallTimeoutMs());
    return (): void => {
      clearTimeout(timeoutId);
    };
  }, [backendStatus.status]);

  if (backendStatus.status === "loading") {
    return (
      <Flex height="100vh" width="100vw" className={styles.background}>
        <TitleBar />
        <Flex m="auto" gap="4" align="center" direction="column">
          <Flex align="center" gap="1">
            <img src={SculptorLogoAndTitle} alt="Sculptor Logo and Title" />
            <Box className={styles.betaLabel}>beta</Box>
          </Flex>
          <Box width="178px">
            <Progress duration="10s" />
          </Box>
          {backendStatus.payload.message &&
            backendStatus.payload.message !== "Initializing..." &&
            backendStatus.payload.message !== "Waiting for backend..." && (
              <Text size="2" weight="medium" className={styles.statusLabel}>
                {backendStatus.payload.message}
              </Text>
            )}
        </Flex>
      </Flex>
    );
  }

  if (backendStatus.status === "shutting_down") {
    if (isShutdownStalled) {
      return (
        <Flex
          height="100vh"
          width="100vw"
          className={styles.background}
          data-testid={ElementIds.BACKEND_SHUTDOWN_STALLED}
        >
          <TitleBar />
          <Flex m="auto" gap="4" align="center" direction="column">
            <Flex align="center" gap="1">
              <img src={SculptorLogoAndTitle} alt="Sculptor Logo and Title" />
              <Box className={styles.betaLabel}>beta</Box>
            </Flex>
            <Flex direction="column" gap="2" align="center" maxWidth="420px">
              <Text size="3" weight="medium" className={styles.shutdownLabel}>
                Sculptor&apos;s shutdown is taking longer than expected.
              </Text>
              <Text size="2" className={styles.shutdownLabel} align="center">
                Please quit Sculptor (⌘Q on macOS, Alt+F4 on Windows/Linux) and relaunch the app.
              </Text>
            </Flex>
          </Flex>
        </Flex>
      );
    }
    return (
      <Flex
        height="100vh"
        width="100vw"
        className={styles.background}
        data-testid={ElementIds.BACKEND_SHUTDOWN_SPINNER}
      >
        <TitleBar />
        <Flex m="auto" gap="4" align="center" direction="column">
          <Flex align="center" gap="1">
            <img src={SculptorLogoAndTitle} alt="Sculptor Logo and Title" />
            <Box className={styles.betaLabel}>beta</Box>
          </Flex>
          <Box width="178px">
            {/*
                We expect shutdown to be generally fast.
                When that's not the case, the Progress component automatically switches to an indeterminate state after its duration elapses.
                We should gradually remove all cases where shutdown takes a long time.
            */}
            <Progress duration="3s" />
          </Box>
          <Text size="3" weight="medium" className={styles.shutdownLabel}>
            {backendStatus.payload.message}
          </Text>
        </Flex>
      </Flex>
    );
  }

  // Fatal error state - show error page if we never got running
  if ((isBackendStatusExited(backendStatus) && !hasStartedSuccessfully) || isBackendStatusError(backendStatus)) {
    const errorMessage =
      backendStatus.status === "exited" ? backendStatus.payload.stderr : backendStatus.payload.message;

    return (
      <ErrorPage
        isCapturingErrorWithSentry={false}
        headerText="Oops! That is embarrassing. An unexpected error has occurred. Try restarting the app or contacting us if the problem persists."
        errorMessage={errorMessage}
        onClearCustomBackend={isCustomCommandMode ? handleClearCustomBackend : undefined}
        isCustomBackendCleared={isCustomBackendCleared}
      />
    );
  }

  return <>{props.children}</>;
};
