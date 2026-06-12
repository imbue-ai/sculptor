import { Button, Checkbox, Flex, IconButton, Popover, Spinner, Text, TextArea } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { Bug, Camera, Check, CheckCircle, ChevronDown, ChevronUp, CopyIcon, Trash2, Undo2, X } from "lucide-react";
import { type ReactElement, useCallback, useRef, useState } from "react";

import { healthCheckDataAtom } from "~/common/state/atoms/backend.ts";
import type { DiagnosticEntry, ScreenshotState, SubmitState } from "~/common/state/atoms/reportProblem.ts";
import {
  formatDiagnosticsAsText,
  getDiagnosticEntries,
  reportProblemAtom,
  resetReportProblemFormAtom,
  submitReportAtom,
  updateReportProblemAtom,
} from "~/common/state/atoms/reportProblem.ts";
import { isTelemetryEnabledAtom } from "~/common/state/atoms/userConfig.ts";
import { isElectron } from "~/electron/utils.ts";

import { ElementIds } from "../api";
import styles from "./ReportProblemPopover.module.scss";

export type { ScreenshotState, SubmitState } from "~/common/state/atoms/reportProblem.ts";

type ReportProblemPopoverProps = {
  children: ReactElement;
};

const COLLAPSED_ENTRY_COUNT = 3;

const useDiagnosticEntries = (): ReadonlyArray<DiagnosticEntry> | null => {
  const healthCheckData = useAtomValue(healthCheckDataAtom);
  if (!healthCheckData) return null;
  return getDiagnosticEntries(healthCheckData);
};

type DiagnosticsSectionProps = {
  isExpanded: boolean;
  onExpand: () => void;
  onCollapse: () => void;
};

const DiagnosticsSection = ({ isExpanded, onExpand, onCollapse }: DiagnosticsSectionProps): ReactElement => {
  const entries = useDiagnosticEntries();
  const [isDiagnosticsCopied, setIsDiagnosticsCopied] = useState(false);

  const handleCopyDiagnostics = useCallback(async (): Promise<void> => {
    if (!entries) return;
    try {
      await navigator.clipboard.writeText(formatDiagnosticsAsText(entries));
      setIsDiagnosticsCopied(true);
      setTimeout(() => setIsDiagnosticsCopied(false), 2000);
    } catch {
      // Clipboard write failed silently
    }
  }, [entries]);

  if (!entries) {
    return <Text size="1">Loading diagnostics...</Text>;
  }

  const visibleEntries = isExpanded ? entries : entries.slice(0, COLLAPSED_ENTRY_COUNT);
  const isCollapsed = !isExpanded && entries.length > COLLAPSED_ENTRY_COUNT;

  return (
    <div className={styles.diagnosticsWrapper}>
      <div className={isExpanded ? styles.diagnosticsScrollArea : undefined}>
        <Flex direction="column" gap="1" className={styles.diagnosticsBox}>
          {visibleEntries.map(({ label, value }) => (
            <Flex key={label} justify="between" gap="4">
              <Text size="1" color="gray">
                {label}
              </Text>
              <Text size="1" className={styles.diagnosticValue}>
                {value ?? "\u2014"}
              </Text>
            </Flex>
          ))}
        </Flex>
      </div>
      {isExpanded && (
        <Flex className={styles.diagnosticsFooter} align="center" justify="between">
          <Button variant="ghost" size="1" onClick={onCollapse} className={styles.collapseButton}>
            <ChevronUp size={12} />
            Collapse
          </Button>
          <IconButton variant="ghost" size="1" onClick={handleCopyDiagnostics} className={styles.diagnosticsCopyButton}>
            {isDiagnosticsCopied ? <Check size={12} /> : <CopyIcon size={12} />}
          </IconButton>
        </Flex>
      )}
      {isCollapsed && (
        <Flex className={styles.diagnosticsFooter} align="center" justify="center">
          <Button variant="ghost" size="1" className={styles.expandButton} onClick={onExpand}>
            <ChevronDown size={12} />
            Show all ({entries.length - COLLAPSED_ENTRY_COUNT} more)
          </Button>
        </Flex>
      )}
    </div>
  );
};

const formatReferenceText = (state: Extract<SubmitState, { type: "success" }>): string => {
  const lines: Array<string> = [];
  if (state.reportId !== null) {
    lines.push(`Report ID: ${state.reportId}`);
  }
  lines.push(`Feedback ID: ${state.sentryEventId}`);
  return lines.join("\n");
};

const getSubmitButtonLabel = (submitState: SubmitState): string => {
  switch (submitState.type) {
    case "collecting":
      return "Collecting...";
    case "reporting":
      return "Reporting...";
    case "idle":
    case "success":
    case "error":
      return "Submit Report";
  }
};

type ScreenshotButtonProps = {
  state: ScreenshotState;
  onCapture: () => void;
  onRemove: () => void;
  isDisabled: boolean;
};

const ScreenshotButton = ({ state, onCapture, onRemove, isDisabled }: ScreenshotButtonProps): ReactElement => {
  const [isHovered, setIsHovered] = useState(false);

  const getButtonProps = (): {
    icon: ReactElement;
    label: string;
    variant: "soft";
    color?: "green" | "red" | "orange";
    isDisabled: boolean;
    onClick?: () => void;
  } => {
    switch (state) {
      case "capturing":
        return { icon: <Spinner size="1" />, label: "Capturing", variant: "soft", isDisabled: true };
      case "captured": {
        const isShowingRemove = isHovered && !isDisabled;
        return {
          icon: isShowingRemove ? <Trash2 size={14} /> : <Camera size={14} />,
          label: isShowingRemove ? "Remove" : "Captured",
          variant: "soft",
          color: isShowingRemove ? "red" : "green",
          isDisabled,
          onClick: onRemove,
        };
      }

      case "failed": {
        const isShowingRetry = isHovered;
        return {
          icon: <Camera size={14} />,
          label: isShowingRetry ? "Screenshot" : "Failed",
          variant: "soft",
          color: isShowingRetry ? undefined : "orange",
          isDisabled: false,
          onClick: onCapture,
        };
      }
      case "idle":
        return { icon: <Camera size={14} />, label: "Screenshot", variant: "soft", isDisabled, onClick: onCapture };
    }
  };

  const props = getButtonProps();

  return (
    <Button
      variant={props.variant}
      color={props.color}
      size="2"
      disabled={props.isDisabled}
      onClick={props.onClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      className={styles.screenshotButton}
    >
      {props.icon}
      {props.label}
    </Button>
  );
};

export type ReportProblemContentProps = {
  submitState: SubmitState;
  description: string;
  shouldIncludeLogs: boolean;
  isDiagnosticsExpanded: boolean;
  isSubmitting: boolean;
  copiedField: "reference" | null;
  onClose: (() => void) | null;
  onDescriptionChange: (value: string) => void;
  onIncludeLogsChange: (value: boolean) => void;
  onExpandDiagnostics: () => void;
  onCollapseDiagnostics: () => void;
  onSubmit: () => void;
  onNewReport: () => void;
  onCopyReference: () => void;
  showScreenshotButton: boolean;
  screenshotState: ScreenshotState;
  onCaptureScreenshot: () => void;
  onRemoveScreenshot: () => void;
};

export const ReportProblemContent = ({
  submitState,
  description,
  shouldIncludeLogs,
  isDiagnosticsExpanded,
  isSubmitting,
  copiedField,
  onClose,
  onDescriptionChange,
  onIncludeLogsChange,
  onExpandDiagnostics,
  onCollapseDiagnostics,
  onSubmit,
  onNewReport,
  onCopyReference,
  showScreenshotButton,
  screenshotState,
  onCaptureScreenshot,
  onRemoveScreenshot,
}: ReportProblemContentProps): ReactElement => {
  const isTelemetryEnabled = useAtomValue(isTelemetryEnabledAtom);

  return (
    <Flex direction="column" gap="3">
      <Flex justify="between" align="center">
        <Text size="2" weight="medium">
          Give Feedback
        </Text>
        {onClose !== null && (
          <IconButton variant="ghost" size="1" className={styles.closeButton} onClick={onClose}>
            <X size={14} />
          </IconButton>
        )}
      </Flex>

      {submitState.type === "success" ? (
        <Flex direction="column" gap="3">
          <Flex align="center" gap="2">
            <CheckCircle size={24} color="var(--green-11)" />
            <Text size="2" weight="medium">
              Thank you for your report!
            </Text>
          </Flex>

          {submitState.didDiagnosticsFail && (
            <Text size="1" color="orange">
              Diagnostics collection failed, but the report was still submitted.
            </Text>
          )}

          <Flex direction="column" gap="1">
            <Flex align="center" justify="between">
              <Text size="1" color="gray">
                Report Reference ID
              </Text>
              <IconButton variant="ghost" size="1" onClick={onCopyReference} className={styles.copyButton}>
                {copiedField === "reference" ? <Check size={12} /> : <CopyIcon size={12} />}
              </IconButton>
            </Flex>
            <Text size="1" className={styles.idValue}>
              {submitState.sentryEventId}
            </Text>
            {submitState.reportId !== null && (
              <Text size="1" className={styles.idValue}>
                {submitState.reportId}
              </Text>
            )}
          </Flex>

          <Button variant="soft" size="2" onClick={onNewReport}>
            <Undo2 size={14} />
            Submit New Report
          </Button>
        </Flex>
      ) : (
        <Flex direction="column" gap="3">
          <DiagnosticsSection
            isExpanded={isDiagnosticsExpanded}
            onExpand={onExpandDiagnostics}
            onCollapse={onCollapseDiagnostics}
          />

          <TextArea
            placeholder="Describe the problem you encountered..."
            value={description}
            onChange={(e) => onDescriptionChange(e.target.value)}
            rows={3}
            disabled={isSubmitting}
          />

          {submitState.type === "error" && (
            <Text size="1" color="red">
              {submitState.message}
            </Text>
          )}

          {!isTelemetryEnabled && (
            <Text size="1" color="gray">
              Telemetry is off — this report is still sent because you&rsquo;re choosing to send it.
            </Text>
          )}

          <Flex gap="2" justify="between" align="center">
            <Flex align="center" gap="2" asChild>
              <label>
                <Checkbox
                  size="1"
                  checked={shouldIncludeLogs}
                  onCheckedChange={(checked) => onIncludeLogsChange(checked === true)}
                  disabled={isSubmitting}
                />
                <Text size="1">Include logs</Text>
              </label>
            </Flex>
            <Flex gap="2" align="center">
              {showScreenshotButton && (
                <ScreenshotButton
                  state={screenshotState}
                  onCapture={onCaptureScreenshot}
                  onRemove={onRemoveScreenshot}
                  isDisabled={isSubmitting}
                />
              )}
              <Button
                variant="solid"
                size="2"
                onClick={onSubmit}
                disabled={isSubmitting || !description.trim()}
                className={styles.submitButton}
              >
                {isSubmitting ? <Spinner size="1" /> : <Bug size={14} />}
                {getSubmitButtonLabel(submitState)}
              </Button>
            </Flex>
          </Flex>
        </Flex>
      )}
    </Flex>
  );
};

export const ReportProblemPopover = ({ children }: ReportProblemPopoverProps): ReactElement => {
  const state = useAtomValue(reportProblemAtom);
  const update = useSetAtom(updateReportProblemAtom);
  const resetForm = useSetAtom(resetReportProblemFormAtom);
  const submitReport = useSetAtom(submitReportAtom);
  const copiedTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleCopyReference = useCallback(async (): Promise<void> => {
    if (state.submitState.type !== "success") return;
    try {
      await navigator.clipboard.writeText(formatReferenceText(state.submitState));
      update({ copiedField: "reference" });
      if (copiedTimeoutRef.current) {
        clearTimeout(copiedTimeoutRef.current);
      }
      copiedTimeoutRef.current = setTimeout(() => {
        update({ copiedField: null });
        copiedTimeoutRef.current = null;
      }, 2000);
    } catch {
      // Clipboard write failed silently
    }
  }, [state.submitState, update]);

  const handleCaptureScreenshot = useCallback(async (): Promise<void> => {
    if (!window.sculptor?.captureScreenshot) return;
    update({ screenshotState: "capturing" });
    try {
      const buffer = await window.sculptor.captureScreenshot();
      update({ screenshotState: "captured", screenshotData: new Uint8Array(buffer) });
    } catch {
      update({ screenshotState: "failed" });
    }
  }, [update]);

  const handleRemoveScreenshot = useCallback((): void => {
    update({ screenshotState: "idle", screenshotData: null });
  }, [update]);

  const isSubmitting = state.submitState.type === "collecting" || state.submitState.type === "reporting";

  return (
    <Popover.Root open={state.isOpen} onOpenChange={(open) => update({ isOpen: open })}>
      <Popover.Trigger>{children}</Popover.Trigger>
      <Popover.Content
        className={styles.content}
        side="top"
        align="start"
        sideOffset={8}
        onPointerDownOutside={(e) => e.preventDefault()}
        onInteractOutside={(e) => e.preventDefault()}
        onOpenAutoFocus={(e) => e.preventDefault()}
        data-testid={ElementIds.REPORT_PROBLEM_POPOVER}
      >
        <ReportProblemContent
          submitState={state.submitState}
          description={state.description}
          shouldIncludeLogs={state.shouldIncludeLogs}
          isDiagnosticsExpanded={state.isDiagnosticsExpanded}
          isSubmitting={isSubmitting}
          copiedField={state.copiedField}
          onClose={() => update({ isOpen: false })}
          onDescriptionChange={(value) => update({ description: value })}
          onIncludeLogsChange={(value) => update({ shouldIncludeLogs: value })}
          onExpandDiagnostics={() => update({ isDiagnosticsExpanded: true })}
          onCollapseDiagnostics={() => update({ isDiagnosticsExpanded: false })}
          onSubmit={submitReport}
          onNewReport={resetForm}
          onCopyReference={handleCopyReference}
          showScreenshotButton={isElectron()}
          screenshotState={state.screenshotState}
          onCaptureScreenshot={handleCaptureScreenshot}
          onRemoveScreenshot={handleRemoveScreenshot}
        />
      </Popover.Content>
    </Popover.Root>
  );
};
