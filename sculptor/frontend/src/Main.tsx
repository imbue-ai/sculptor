import "@radix-ui/themes/styles.css";
import "./index.css";
import "./styles/mobile-sand.css";

import React from "react";
import ReactDOM from "react-dom/client";

import { baseUrl, configureClient } from "./apiClient.ts";
import { App } from "./App.tsx";
import { initializeSessionToken } from "./common/Auth.ts";
import { initializeKeyboardLayoutMap } from "./common/ShortcutUtils.ts";
import { initializeTelemetry } from "./common/Telemetry.ts";
import { initializeTracing } from "./common/tracing.ts";
import { initializeSentry } from "./instrument.ts";

(async (): Promise<void> => {
  try {
    initializeSentry();
    initializeTelemetry();
    // Cache the active keyboard layout so shortcut matching follows the
    // characters the user's layout produces.
    initializeKeyboardLayoutMap();
    await configureClient();
    initializeTracing(baseUrl);
    await initializeSessionToken();
  } catch (e) {
    console.log("Initialization failed", e);
  }

  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
})();
