// A terminal-style "background box" mirroring the bottom TerminalPanel surface.
// Presentational only: it renders a command title bar plus a bounded, scrolling
// tail of log lines. The only color here is authentic terminal log content
// (passed in as plain strings) — the chrome stays neutral gray. When the
// process is running it shows a blinking block cursor at the end of the tail.
import { IconButton } from "@radix-ui/themes";
import { ExternalLink } from "lucide-react";
import type { ReactElement } from "react";

import styles from "./BackgroundProcessOutputBox.module.scss";

type BackgroundProcessOutputBoxProps = {
  command: string;
  lines: ReadonlyArray<string>;
  isRunning?: boolean;
  onOpenInTerminal?: () => void;
};

export const BackgroundProcessOutputBox = ({
  command,
  lines,
  isRunning,
  onOpenInTerminal,
}: BackgroundProcessOutputBoxProps): ReactElement => {
  const isProcessRunning = isRunning ?? false;

  return (
    <div className={styles.box}>
      <div className={styles.titleBar}>
        <span className={styles.command} title={command}>
          {command}
        </span>
        {onOpenInTerminal !== undefined ? (
          <IconButton
            size="1"
            variant="ghost"
            color="gray"
            className={styles.openButton}
            onClick={onOpenInTerminal}
            title="Open in terminal panel"
            aria-label="Open in terminal panel"
          >
            <ExternalLink size={12} />
          </IconButton>
        ) : undefined}
      </div>
      <pre className={styles.body}>
        {lines.map((line, index) => (
          // Log lines are an ordered append-only tail with no stable id; the
          // index is the natural key for a render-only bounded list.
          <div key={index} className={styles.line}>
            {line}
            {isProcessRunning && index === lines.length - 1 ? <span className={styles.cursor} /> : undefined}
          </div>
        ))}
        {isProcessRunning && lines.length === 0 ? <span className={styles.cursor} /> : undefined}
      </pre>
    </div>
  );
};
