import { Button, Code, Flex, IconButton, Link, Popover, Spinner, Text } from "@radix-ui/themes";
import {
  AlertCircleIcon,
  CheckCircle2Icon,
  ChevronDownIcon,
  ChevronRightIcon,
  CircleHelpIcon,
  CircleXIcon,
  ExternalLinkIcon,
} from "lucide-react";
import type React from "react";
import type { ReactElement } from "react";
import { useState } from "react";

import styles from "./DependencyCard.module.scss";
import type { DependencyStatus } from "./dependencyTypes.ts";

const CircleProgress = ({ percent, size = 24 }: { percent: number; size?: number }): ReactElement => {
  const strokeWidth = 2;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - Math.min(Math.max(percent, 0), 100) / 100);
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className={styles.circleProgress}>
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--accent-6)" strokeWidth={strokeWidth} />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="var(--accent-11)"
        strokeWidth={strokeWidth}
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
    </svg>
  );
};

type AuthPanelProps = {
  authUrl: string | null;
  authError: string | null;
  onSubmitAuthCode?: (code: string) => Promise<void>;
  // Device flow (e.g. gh): when userCode is set, show the one-time code to enter
  // at authUrl and wait for completion (no paste-back) — the parent polls the
  // dependency's auth status and clears authUrl once authenticated.
  userCode?: string | null;
};

// Headless/remote sign-in panel: the link to open plus a field to paste the
// resulting code back. Owns the code-entry state so DependencyCard doesn't have
// to. Rendered only when there's a sign-in URL to show or an error to surface.
const AuthPanel = ({ authUrl, authError, onSubmitAuthCode, userCode = null }: AuthPanelProps): ReactElement => {
  const [authCode, setAuthCode] = useState<string>("");
  const [isSubmittingCode, setIsSubmittingCode] = useState<boolean>(false);

  const handleSubmitCode = async (): Promise<void> => {
    if (!authCode.trim() || !onSubmitAuthCode) return;
    setIsSubmittingCode(true);
    try {
      await onSubmitAuthCode(authCode.trim());
      setAuthCode("");
    } finally {
      setIsSubmittingCode(false);
    }
  };

  return (
    <Flex direction="column" gap="2" className={styles.details} data-role="auth-panel">
      {authUrl && userCode ? (
        // Device flow (gh): show the one-time code to enter at the URL, then
        // wait — the parent polls auth status and clears authUrl on success.
        <>
          <Text size="1">Open the verification page, enter the code below, and approve access.</Text>
          <Link href={authUrl} target="_blank" size="2" className={styles.installLink} data-role="auth-url-link">
            <Flex align="center" gap="1">
              Open verification page
              <ExternalLinkIcon size={12} />
            </Flex>
          </Link>
          <Flex align="center" gap="2">
            <Text size="1">Code:</Text>
            <Code size="2" data-role="auth-user-code">
              {userCode}
            </Code>
          </Flex>
          <Flex align="center" gap="2">
            <Spinner size="1" />
            <Text size="1" color="gray">
              Waiting for authorization…
            </Text>
          </Flex>
        </>
      ) : authUrl ? (
        <>
          <Text size="1">Open the sign-in page, approve access, then paste the code shown back here.</Text>
          <Link href={authUrl} target="_blank" size="2" className={styles.installLink} data-role="auth-url-link">
            <Flex align="center" gap="1">
              Open sign-in page
              <ExternalLinkIcon size={12} />
            </Flex>
          </Link>
          <Flex align="center" gap="2" style={{ flex: 1, minWidth: 0 }}>
            <input
              className={styles.overrideInput}
              type="text"
              placeholder="Paste code here"
              value={authCode}
              onChange={(e) => setAuthCode(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSubmitCode();
              }}
              data-role="auth-code-input"
            />
            <Button
              size="1"
              variant="solid"
              onClick={handleSubmitCode}
              disabled={isSubmittingCode || !authCode.trim()}
              data-role="auth-code-submit"
            >
              {isSubmittingCode ? <Spinner /> : "Submit"}
            </Button>
          </Flex>
        </>
      ) : null}
      {authError && (
        <Text size="1" color="red" data-role="auth-error">
          {authError}
        </Text>
      )}
    </Flex>
  );
};

type DependencyCardProps = {
  name: string;
  cliName: string;
  status: DependencyStatus;
  installUrl: string;
  brewPackage?: string;
  optional?: boolean;
  // Sculptor can install this dependency itself (a managed download): the
  // Install button triggers it directly instead of opening the popover of
  // manual install instructions.
  onInstall?: () => void;
  onApplyOverride?: (path: string) => Promise<void>;
  onAuthenticate?: () => void;
  // Interactive sign-in (headless/remote): when authUrl is set, the card shows
  // the link to open plus a field to paste the resulting code, submitted via
  // onSubmitAuthCode. authError surfaces a failed start/submit.
  authUrl?: string | null;
  authError?: string | null;
  onSubmitAuthCode?: (code: string) => Promise<void>;
  // Device flow (e.g. gh): when userCode is set, the card shows the one-time code
  // to enter at authUrl and waits for completion (no paste-back) — the parent
  // polls the dependency's auth status and clears authUrl once authenticated.
  userCode?: string | null;
  onModeSwitch?: (mode: string) => void;
  modeControls?: Array<{ label: string; mode: string }>;
  helpText?: string;
  installProgress?: { bytesDownloaded: number; totalBytes?: number | null } | null;
};

const isMac = (): boolean => {
  return navigator.platform.startsWith("Mac") || navigator.userAgent.includes("Mac");
};

const STATUS_LABELS: Record<DependencyStatus["state"], string> = {
  loading: "checking",
  installed: "installed",
  "not-installed": "not installed",
  installing: "installing",
  "needs-auth": "not signed in",
  authenticating: "authenticating",
  "wrong-version": "version mismatch",
  error: "error",
};

const STATUS_ICONS: Record<DependencyStatus["state"], ReactElement | null> = {
  loading: null,
  installing: null,
  authenticating: null,
  installed: <CheckCircle2Icon size={14} className={styles.iconInstalled} />,
  "needs-auth": <AlertCircleIcon size={14} className={styles.iconWarning} />,
  "not-installed": <CircleXIcon size={14} className={styles.iconError} />,
  "wrong-version": <CircleXIcon size={14} className={styles.iconError} />,
  error: <CircleXIcon size={14} className={styles.iconError} />,
};

const ROW_CLASSES: Record<DependencyStatus["state"], string> = {
  loading: styles.row,
  "not-installed": styles.row,
  installing: styles.row,
  authenticating: styles.row,
  installed: styles.rowInstalled,
  "needs-auth": styles.rowWarning,
  "wrong-version": styles.rowError,
  error: styles.rowError,
};

export const DependencyCard = ({
  name,
  cliName,
  status,
  installUrl,
  brewPackage,
  optional = false,
  onInstall,
  onApplyOverride,
  onAuthenticate,
  authUrl = null,
  authError = null,
  onSubmitAuthCode,
  userCode = null,
  onModeSwitch,
  modeControls,
  helpText,
  installProgress = null,
}: DependencyCardProps): ReactElement => {
  const [isExpanded, setIsExpanded] = useState<boolean>(false);
  const [isOverrideVisible, setIsOverrideVisible] = useState<boolean>(false);
  const [overridePath, setOverridePath] = useState<string>("");
  const [overrideError, setOverrideError] = useState<string | undefined>(undefined);
  const [isApplying, setIsApplying] = useState<boolean>(false);

  const canExpand = status.state !== "loading" && status.state !== "installing" && status.state !== "authenticating";

  const isNeutralOptional =
    optional && (status.state === "not-installed" || status.state === "needs-auth" || status.state === "wrong-version");

  const isSpinnerVisible =
    status.state === "loading" || status.state === "installing" || status.state === "authenticating";

  const handleApply = async (): Promise<void> => {
    if (!overridePath.trim() || !onApplyOverride) return;
    setIsApplying(true);
    setOverrideError(undefined);
    try {
      await onApplyOverride(overridePath.trim());
      setIsOverrideVisible(false);
    } catch {
      setOverrideError("No executable found at this path");
    } finally {
      setIsApplying(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent): void => {
    if (e.key === "Enter") {
      handleApply();
    }
  };

  const handleToggle = (): void => {
    // Runtime enforcement of the gate the wrapper's `aria-disabled` declares —
    // `aria-disabled` is advisory and does not block a real pointer event.
    if (!canExpand) return;
    setIsExpanded(!isExpanded);
  };

  const progressPercent =
    installProgress && installProgress.totalBytes
      ? Math.round((installProgress.bytesDownloaded / installProgress.totalBytes) * 100)
      : null;

  const shouldShowInstallAction = status.state === "not-installed" || status.state === "wrong-version";
  const shouldShowBrew = Boolean(brewPackage) && isMac();

  const hasPathAndVersion =
    status.state === "installed" ||
    status.state === "wrong-version" ||
    status.state === "needs-auth" ||
    status.state === "authenticating";

  return (
    // `aria-disabled` reflects the `canExpand` gate that `handleToggle` enforces. Without
    // it the card renders as a plain actionable element while the dependency probe is
    // loading/installing/authenticating, so a click landing in that window is silently
    // dropped by the early-return. Surfacing the gate as `aria-disabled` makes the
    // framework's actionability contract honor it — Playwright auto-waits for the card to
    // become ready instead of dropping the click and timing out downstream (SCU-1215).
    <Flex
      direction="column"
      className={isNeutralOptional ? styles.row : ROW_CLASSES[status.state]}
      data-dependency={cliName}
      aria-disabled={!canExpand}
    >
      <Flex
        align="center"
        gap="2"
        className={canExpand ? styles.mainRowClickable : styles.mainRow}
        onClick={handleToggle}
      >
        {isSpinnerVisible ? (
          status.state === "installing" && progressPercent !== null ? (
            <CircleProgress percent={progressPercent} size={16} />
          ) : (
            <Spinner size="1" />
          )
        ) : isNeutralOptional ? (
          <AlertCircleIcon size={14} className={styles.iconNeutral} />
        ) : (
          STATUS_ICONS[status.state]
        )}

        <Code size="2" className={styles.cliName}>
          {cliName}
        </Code>

        <Text size="2" className={isSpinnerVisible ? styles.label : styles.statusText} data-role="status">
          {STATUS_LABELS[status.state]}
        </Text>

        <Flex align="center" gap="2" ml="auto" style={{ flexShrink: 0 }}>
          {optional && status.state !== "installed" && (
            <Text size="2" className={styles.optionalTag}>
              optional
            </Text>
          )}

          {helpText && status.state === "installing" && (
            <Popover.Root>
              <Popover.Trigger>
                <IconButton size="1" variant="ghost" onClick={(e) => e.stopPropagation()}>
                  <CircleHelpIcon size={14} className={styles.chevron} />
                </IconButton>
              </Popover.Trigger>
              <Popover.Content side="top" align="center" sideOffset={4} style={{ maxWidth: 240 }}>
                <Text size="1">
                  {helpText} <Code size="1">{cliName}</Code>.
                </Text>
              </Popover.Content>
            </Popover.Root>
          )}

          {shouldShowInstallAction &&
            (onInstall ? (
              <Button
                size="1"
                variant="soft"
                data-role="install-button"
                onClick={(e) => {
                  e.stopPropagation();
                  onInstall();
                }}
              >
                Install
              </Button>
            ) : (
              <Popover.Root>
                <Popover.Trigger>
                  <Button
                    size="1"
                    variant="soft"
                    data-role="install-button"
                    onClick={(e) => {
                      e.stopPropagation();
                    }}
                  >
                    Install
                  </Button>
                </Popover.Trigger>
                <Popover.Content side="bottom" align="end" sideOffset={4}>
                  <Flex direction="column" gap="2" style={{ minWidth: 220 }}>
                    <Text size="2" weight="medium">
                      Install {name}
                    </Text>
                    {shouldShowBrew && (
                      <Code size="1" className={styles.brewCommand}>
                        brew install {brewPackage}
                      </Code>
                    )}
                    <Link href={installUrl} target="_blank" size="2" className={styles.installLink}>
                      <Flex align="center" gap="1">
                        Details
                        <ExternalLinkIcon size={12} />
                      </Flex>
                    </Link>
                  </Flex>
                </Popover.Content>
              </Popover.Root>
            ))}

          {status.state === "needs-auth" && onAuthenticate && !authUrl && (
            <Button
              size="1"
              variant="soft"
              data-role="authenticate-button"
              onClick={(e) => {
                e.stopPropagation();
                onAuthenticate();
              }}
            >
              Sign in
            </Button>
          )}

          {status.state === "authenticating" && (
            <Popover.Root>
              <Popover.Trigger>
                <IconButton size="1" variant="ghost" onClick={(e) => e.stopPropagation()}>
                  <CircleHelpIcon size={14} className={styles.chevron} />
                </IconButton>
              </Popover.Trigger>
              <Popover.Content side="top" align="center" sideOffset={4} style={{ maxWidth: 240 }}>
                <Text size="1">
                  Run <Code size="1">claude auth login</Code> in your terminal to sign in if a browser did not
                  automatically open.
                </Text>
              </Popover.Content>
            </Popover.Root>
          )}

          {canExpand &&
            (isExpanded ? (
              <ChevronDownIcon size={14} className={styles.chevron} />
            ) : (
              <ChevronRightIcon size={14} className={styles.chevron} />
            ))}
        </Flex>
      </Flex>

      {(authUrl || authError) && (
        <AuthPanel authUrl={authUrl} authError={authError} onSubmitAuthCode={onSubmitAuthCode} userCode={userCode} />
      )}

      {isExpanded && (
        <Flex direction="column" gap="2" className={styles.details}>
          {status.state === "error" && (
            <Text size="1" color="red">
              {status.message}
            </Text>
          )}

          {status.state === "wrong-version" && (
            <Text size="1" color="red">
              Found version {status.version}, requires {status.requiredVersion}
            </Text>
          )}

          <Flex align="center" gap="2">
            <Text className={styles.detailLabel}>Path</Text>
            {isOverrideVisible ? (
              <Flex align="center" gap="2" style={{ flex: 1, minWidth: 0 }}>
                <input
                  className={`${styles.overrideInput} ${overrideError ? styles.overrideInputError : ""}`}
                  type="text"
                  placeholder={`/usr/local/bin/${cliName}`}
                  value={overridePath}
                  onChange={(e) => setOverridePath(e.target.value)}
                  onKeyDown={handleKeyDown}
                  data-role="override-input"
                />
                <Button
                  size="1"
                  variant="solid"
                  onClick={handleApply}
                  disabled={isApplying || !overridePath.trim()}
                  data-role="override-apply"
                >
                  {isApplying ? <Spinner /> : "Apply"}
                </Button>
                <Text
                  className={styles.overrideLink}
                  data-role="override-cancel"
                  onClick={(e) => {
                    e.stopPropagation();
                    setIsOverrideVisible(false);
                    setOverridePath("");
                    setOverrideError(undefined);
                  }}
                >
                  cancel
                </Text>
              </Flex>
            ) : (
              <>
                <Text
                  className={`${styles.detailValue} ${styles.pathValue}`}
                  data-role="path"
                  title={hasPathAndVersion ? status.path : undefined}
                >
                  {hasPathAndVersion ? status.path : "—"}
                </Text>
                {onApplyOverride && (
                  <Text
                    className={styles.overrideLink}
                    data-role="override-link"
                    onClick={(e) => {
                      e.stopPropagation();
                      setIsOverrideVisible(true);
                    }}
                  >
                    override
                  </Text>
                )}
              </>
            )}
          </Flex>
          {overrideError && (
            <Text className={styles.overrideErrorText} data-role="override-error">
              {overrideError}
            </Text>
          )}

          <Flex align="center" gap="2">
            <Text className={styles.detailLabel}>Version</Text>
            <Text className={styles.detailValue} data-role="version">
              {hasPathAndVersion ? status.version : "—"}
            </Text>
          </Flex>

          {modeControls && modeControls.length > 0 && (
            <Flex align="center" gap="2" className={styles.modeControlRow}>
              {modeControls.map((control) => (
                <Text
                  key={control.mode}
                  className={styles.overrideLink}
                  data-role="mode-switch"
                  onClick={(e) => {
                    e.stopPropagation();
                    onModeSwitch?.(control.mode);
                  }}
                >
                  {control.label}
                </Text>
              ))}
            </Flex>
          )}
        </Flex>
      )}
    </Flex>
  );
};
