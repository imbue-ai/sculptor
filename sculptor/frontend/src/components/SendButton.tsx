import { IconButton, Tooltip } from "@radix-ui/themes";
import { ArrowRightIcon } from "lucide-react";
import type { ReactElement } from "react";

import styles from "./SendButton.module.scss";

type SendButtonProps = {
  onClick: () => void;
  disabled: boolean;
  tooltip: string;
  ariaLabel: string;
  testId: string;
  /** Rendered as `data-last-send-error`; attribute is omitted when null. */
  lastSendError?: string | null;
  /**
   * While a send is in flight: swaps the arrow for Radix's spinner (which also
   * makes the button non-interactive). Mirrored as `data-loading` so tests can
   * assert the in-flight state without reaching into Radix internals.
   */
  loading?: boolean;
};

export const SendButton = ({
  onClick,
  disabled,
  tooltip,
  ariaLabel,
  testId,
  lastSendError,
  loading = false,
}: SendButtonProps): ReactElement => (
  <Tooltip content={tooltip}>
    <IconButton
      onClick={onClick}
      disabled={disabled}
      loading={loading}
      className={styles.button}
      aria-label={ariaLabel}
      data-testid={testId}
      {...(loading ? { "data-loading": "true" } : {})}
      {...(lastSendError !== null && lastSendError !== undefined ? { "data-last-send-error": lastSendError } : {})}
    >
      <ArrowRightIcon size={16} />
    </IconButton>
  </Tooltip>
);
