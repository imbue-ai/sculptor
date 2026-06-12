import type { Terminal as XTerm } from "@xterm/xterm";
import type { DetailedHTMLProps, HTMLAttributes } from "react";

import type { WsSwitchTimingRecord } from "./common/perf/workspaceSwitchProfiler.ts";
import type { SculptorElectronAPI } from "./shared/types.ts";

type WebviewHTMLAttributes = HTMLAttributes<HTMLElement> & {
  src?: string;
  partition?: string;
  allowpopups?: boolean;
  useragent?: string;
};

declare global {
  // eslint-disable-next-line @typescript-eslint/consistent-type-definitions
  interface Window {
    sculptor?: SculptorElectronAPI;
    /** Exposed by the active TerminalInstance for integration tests. */
    __xterm?: XTerm;
    /** Populated by the Browser panel after webview did-attach, for integration tests. */
    __BROWSER_PANEL_TEST__?: { webContentsId: number };
    /** Inlined by the backend's static-HTML serve path when --trace-to is set.
     * The renderer reads this synchronously at boot in common/tracing.ts. */
    __SCULPTOR_TRACING__?: { enabled: boolean };
    /** Set by test/capture harnesses (before app code runs) to force-enable
     * the workspace-switch profiler. See common/perf/workspaceSwitchProfiler.ts. */
    __WS_SWITCH_PROFILER__?: boolean;
    /** Completed workspace-switch timing records, newest last (capped).
     * Written by common/perf/workspaceSwitchProfiler.ts; read by tooling. */
    __WS_SWITCH_TIMINGS__?: Array<WsSwitchTimingRecord>;
  }

  declare const API_URL_BASE: string | undefined;

  namespace JSX {
    // eslint-disable-next-line @typescript-eslint/consistent-type-definitions
    interface IntrinsicElements {
      webview: DetailedHTMLProps<WebviewHTMLAttributes, HTMLElement>;
    }
  }
}
