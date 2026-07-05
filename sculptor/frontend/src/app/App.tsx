import { ErrorBoundary } from "@sentry/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { Provider as JotaiProvider } from "jotai/react";
import { posthog } from "posthog-js";
import { PostHogProvider } from "posthog-js/react";
import type { ReactElement } from "react";
import { useEffect, useRef, useState } from "react";

import { getTelemetryInfo } from "~/api";
import { queryClient } from "~/common/queryClient.ts";
import { applyTelemetryInfo } from "~/common/Telemetry.ts";

import { TanstackDevtoolsMount } from "../components/devPanel/TanstackDevtoolsMount.tsx";
import { ToastProvider } from "../components/Toast.tsx";
import { ErrorPage } from "../pages/error/ErrorPage.tsx";
import { BrowserViewHost } from "../pages/workspace/panels/browser/BrowserViewHost.tsx";
import { BackendStatusBoundary } from "./BackendStatusBoundary.tsx";
import { ConfigLoader } from "./ConfigLoader.tsx";
import { useAppZoom } from "./hooks/useAppZoom.ts";
import { RequireOnboarding } from "./RequireOnboarding.tsx";
import { Router } from "./Router.tsx";
import { ThemeProvider } from "./ThemeProvider.tsx";

const isDebugRoute = (): boolean => window.location.hash.startsWith("#/debug/");

export const App = (): ReactElement => {
  useAppZoom();
  const [isBackendAPIReady, setIsBackendAPIReady] = useState<boolean>(false);
  const isTelemetryInfoApplied = useRef<boolean>(false);

  // PostHog itself was initialized in `Main.tsx` so pre-handshake events (e.g.
  // loading screen, pageload) are captured. Once the BE responds with
  // `/api/v1/telemetry_info`, we wire up the rest: super properties, Sentry
  // user context, and identify if the user has already submitted their email.
  const fetchAndApplyTelemetryInfo = async (): Promise<void> => {
    const { data: telemetryInfo } = await getTelemetryInfo({ meta: { skipWsAck: true } });

    if (isTelemetryInfoApplied.current) return;
    if (telemetryInfo) {
      applyTelemetryInfo(telemetryInfo);
      isTelemetryInfoApplied.current = true;
    }
  };

  useEffect(() => {
    if (isTelemetryInfoApplied.current) return;
    if (!isBackendAPIReady) return;

    // NOTE: no retrying on failure here
    fetchAndApplyTelemetryInfo();
  }, [isBackendAPIReady]);

  // Debug routes bypass backend, onboarding, and config loading since they
  // are self-contained pages that don't need API access.
  if (isDebugRoute()) {
    return (
      <ErrorBoundary fallback={(props) => <ErrorPage error={props.error} />} showDialog>
        <QueryClientProvider client={queryClient}>
          <Router />
        </QueryClientProvider>
      </ErrorBoundary>
    );
  }

  return (
    <ErrorBoundary fallback={(props) => <ErrorPage error={props.error} />} showDialog>
      <QueryClientProvider client={queryClient}>
        <PostHogProvider client={posthog}>
          <JotaiProvider>
            <ThemeProvider>
              <ToastProvider>
                <BackendStatusBoundary setIsBackendAPIReady={setIsBackendAPIReady}>
                  <RequireOnboarding>
                    <ConfigLoader>
                      <Router />
                      <BrowserViewHost />
                    </ConfigLoader>
                  </RequireOnboarding>
                </BackendStatusBoundary>
              </ToastProvider>
            </ThemeProvider>
            <TanstackDevtoolsMount />
          </JotaiProvider>
        </PostHogProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
};
