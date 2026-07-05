import type { Meta, StoryObj } from "@storybook/react-vite";
import { createStore, Provider as JotaiProvider } from "jotai";
import type { ReactElement } from "react";

import type { HealthCheckResponse } from "~/api";
import { healthCheckDataAtom } from "~/common/state/atoms/backend.ts";

import type { ReportProblemContentProps, ScreenshotState, SubmitState } from "./ReportProblemPopover.tsx";
import { ReportProblemContent } from "./ReportProblemPopover.tsx";

const SAMPLE_HEALTH_CHECK: HealthCheckResponse = {
  version: "0.42.1",
  gitSha: "abc1234def5678",
  pythonVersion: "3.12.3",
  platform: "darwin",
  platformVersion: "24.6.0",
  freeDiskGb: 128.3,
  minFreeDiskGb: 5,
  freeDiskGbWarnLimit: 10,
  uptimeSeconds: 3600,
  activeTaskCount: 2,
  dataDirectory: "/Users/dev/.sculptor_data",
  installMode: "source",
  installPath: "/Users/dev/sculptor",
  ciJobId: null,
  ciRef: null,
};

const SAMPLE_REPORT_ID = "20260320-180000_a1b2c3d4-e5f6-7890-abcd-ef1234567890";
const SAMPLE_SENTRY_ID = "f47ac10b58cc4372a5670e02b2c3d479";

const handleNoop = (): void => {
  console.log("action triggered");
};

const handleCopyReference = (): void => {
  console.log("copy reference");
};

const createHealthCheckStore = (): ReturnType<typeof createStore> => {
  const store = createStore();
  store.set(healthCheckDataAtom, SAMPLE_HEALTH_CHECK);
  return store;
};

type StoryProps = {
  submitState: SubmitState;
  description: string;
  shouldIncludeLogs: boolean;
  isDiagnosticsExpanded: boolean;
  screenshotState: ScreenshotState;
};

const Wrapper = ({
  submitState,
  description,
  shouldIncludeLogs,
  isDiagnosticsExpanded,
  screenshotState,
}: StoryProps): ReactElement => {
  const store = createHealthCheckStore();
  const isSubmitting = submitState.type === "collecting" || submitState.type === "reporting";

  const contentProps: ReportProblemContentProps = {
    submitState,
    description,
    shouldIncludeLogs,
    isDiagnosticsExpanded,
    isSubmitting,
    copiedField: null,
    onClose: null,
    onDescriptionChange: handleNoop,
    onIncludeLogsChange: handleNoop,
    onExpandDiagnostics: handleNoop,
    onCollapseDiagnostics: handleNoop,
    onSubmit: handleNoop,
    onNewReport: handleNoop,
    onCopyReference: handleCopyReference,
    showScreenshotButton: true,
    screenshotState,
    onCaptureScreenshot: handleNoop,
    onRemoveScreenshot: handleNoop,
  };

  return (
    <JotaiProvider store={store}>
      <div style={{ width: 420, padding: 20 }}>
        <div
          style={{
            background: "var(--color-panel-solid)",
            border: "1px solid var(--gray-a5)",
            borderRadius: "var(--radius-4)",
            padding: "var(--space-4)",
            overflow: "hidden",
          }}
        >
          <ReportProblemContent {...contentProps} />
        </div>
      </div>
    </JotaiProvider>
  );
};

const meta = {
  title: "Custom/ReportProblemPopover",
  component: Wrapper,
  args: {
    description: "",
    shouldIncludeLogs: true,
    isDiagnosticsExpanded: false,
    screenshotState: "idle",
  },
} satisfies Meta<typeof Wrapper>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    submitState: { type: "idle" },
  },
};

export const DiagnosticsExpanded: Story = {
  args: {
    submitState: { type: "idle" },
    isDiagnosticsExpanded: true,
  },
};

export const WithDescription: Story = {
  args: {
    submitState: { type: "idle" },
    description: "The agent stopped responding after I asked it to refactor the auth module.",
  },
};

export const LogsUnchecked: Story = {
  args: {
    submitState: { type: "idle" },
    shouldIncludeLogs: false,
  },
};

export const Collecting: Story = {
  args: {
    submitState: { type: "collecting" },
    description: "Something broke during code generation.",
  },
};

export const Reporting: Story = {
  args: {
    submitState: { type: "reporting" },
    description: "Something broke during code generation.",
  },
};

export const SuccessWithDiagnostics: Story = {
  args: {
    submitState: {
      type: "success",
      reportId: SAMPLE_REPORT_ID,
      sentryEventId: SAMPLE_SENTRY_ID,
      didDiagnosticsFail: false,
    },
  },
};

export const SuccessWithoutDiagnostics: Story = {
  args: {
    submitState: {
      type: "success",
      reportId: null,
      sentryEventId: SAMPLE_SENTRY_ID,
      didDiagnosticsFail: false,
    },
  },
};

export const SuccessDiagnosticsFailed: Story = {
  args: {
    submitState: {
      type: "success",
      reportId: null,
      sentryEventId: SAMPLE_SENTRY_ID,
      didDiagnosticsFail: true,
    },
  },
};

export const ScreenshotCapturing: Story = {
  args: {
    submitState: { type: "idle" },
    description: "Something broke.",
    screenshotState: "capturing",
  },
};

export const ScreenshotCaptured: Story = {
  args: {
    submitState: { type: "idle" },
    description: "Something broke.",
    screenshotState: "captured",
  },
};

export const ScreenshotFailed: Story = {
  args: {
    submitState: { type: "idle" },
    description: "Something broke.",
    screenshotState: "failed",
  },
};

export const Error: Story = {
  args: {
    submitState: {
      type: "error",
      message: "Network error: Failed to fetch",
    },
    description: "Something broke.",
  },
};
