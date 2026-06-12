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
};

export const SendButton = ({
  onClick,
  disabled,
  tooltip,
  ariaLabel,
  testId,
  lastSendError,
}: SendButtonProps): ReactElement => (
  <Tooltip content={tooltip}>
    <IconButton
      onClick={onClick}
      disabled={disabled}
      className={styles.button}
      aria-label={ariaLabel}
      data-testid={testId}
      {...(lastSendError !== null && lastSendError !== undefined ? { "data-last-send-error": lastSendError } : {})}
    >
      <ArrowRightIcon size={16} />
    </IconButton>
  </Tooltip>
);
