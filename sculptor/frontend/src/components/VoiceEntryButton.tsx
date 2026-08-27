import { IconButton, Tooltip } from "@radix-ui/themes";
import { Mic } from "lucide-react";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";
import { useIsMobile } from "~/common/hooks/useLayoutMode.ts";
import { useVoiceEntry } from "~/common/hooks/useVoiceEntry.ts";
import { neutral } from "~/common/theme/neutralColor.ts";
import { optional } from "~/common/utils/optional.ts";

import styles from "./VoiceEntryButton.module.scss";

const ICON_SIZE_PX = 16;
const RING_SIZE_PX = 28;
const RING_STROKE_PX = 2;

/** A determinate circular progress overlay (Radix has only an indeterminate Spinner). */
const ProgressRing = ({ percent }: { percent: number }): ReactElement => {
  const radius = (RING_SIZE_PX - RING_STROKE_PX) / 2;
  const center = RING_SIZE_PX / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(100, percent));
  const dashOffset = circumference * (1 - clamped / 100);
  return (
    <svg
      className={styles.ring}
      width={RING_SIZE_PX}
      height={RING_SIZE_PX}
      viewBox={`0 0 ${RING_SIZE_PX} ${RING_SIZE_PX}`}
      aria-hidden
    >
      <circle
        className={styles.ringTrack}
        cx={center}
        cy={center}
        r={radius}
        strokeWidth={RING_STROKE_PX}
        fill="none"
      />
      <circle
        className={styles.ringIndicator}
        cx={center}
        cy={center}
        r={radius}
        strokeWidth={RING_STROKE_PX}
        fill="none"
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={dashOffset}
      />
    </svg>
  );
};

type VoiceEntryButtonProps = {
  /** Receives each transcribed segment verbatim; the caller appends it to its
   *  own draft (with smart spacing) so persistence/undo match typing. */
  onAppendTranscript: (text: string) => void;
  /** Interim transcription (non-empty) of the utterance being spoken. */
  onPreviewChange?: (preview: string) => void;
  /** The utterance produced no final; discard the shown preview. */
  onPreviewDiscard?: () => void;
  /** Fires when voice takes/releases ownership of the surface's text entry;
   *  the surface should lock typing/paste while held. */
  onCaptureLockChange?: (locked: boolean) => void;
};

/**
 * The square mic toggle that sits immediately left of the send button. It folds
 * the whole voice-entry lifecycle into one button: trigger/monitor the managed
 * voice-models download (determinate ring while installing), then start/stop the
 * on-device speech engine. Desktop-only, and hidden outside a secure context
 * (mic capture requires one). Harness-agnostic — always rendered, regardless of
 * the active agent type.
 */
export const VoiceEntryButton = ({
  onAppendTranscript,
  onPreviewChange,
  onPreviewDiscard,
  onCaptureLockChange,
}: VoiceEntryButtonProps): ReactElement | null => {
  const isMobile = useIsMobile();
  const voice = useVoiceEntry({ onAppendTranscript, onPreviewChange, onPreviewDiscard, onCaptureLockChange });

  // Voice entry is desktop-only, and getUserMedia is unavailable off a secure
  // context, so there is nothing the button could do there.
  if (isMobile || !window.isSecureContext) {
    return null;
  }

  const icon = <Mic size={ICON_SIZE_PX} />;

  // Radix Tooltip does not fire on a disabled button (pointer-events: none), so
  // during install the hover target and test id live on a wrapping span, with
  // the progress ring overlaid.
  if (voice.status === "installing") {
    return (
      <Tooltip content={voice.tooltip}>
        <span
          className={styles.wrapper}
          data-testid={ElementIds.VOICE_ENTRY_TOGGLE}
          data-voice-state={voice.status}
          data-progress-percent={voice.progressPercent ?? undefined}
          // Mirrors the Tooltip copy (which Radix only renders on hover) so the
          // derived state is assertable without simulating a hover.
          data-tooltip={voice.tooltip}
        >
          <IconButton
            disabled
            aria-disabled
            variant="ghost"
            size="3"
            color={neutral}
            aria-label={voice.ariaLabel}
            style={{ margin: 0 }}
          >
            {icon}
          </IconButton>
          <ProgressRing percent={voice.progressPercent ?? 0} />
        </span>
      </Tooltip>
    );
  }

  return (
    <Tooltip content={voice.tooltip}>
      <IconButton
        onClick={voice.handleClick}
        loading={voice.isBusy}
        variant={voice.isActive ? "solid" : "ghost"}
        size="3"
        color={voice.isError ? "red" : undefined}
        className={optional(voice.isActive, styles.listening)}
        aria-label={voice.ariaLabel}
        aria-pressed={voice.isActive}
        data-testid={ElementIds.VOICE_ENTRY_TOGGLE}
        data-voice-state={voice.status}
        data-tooltip={voice.tooltip}
        style={{ margin: 0 }}
      >
        {icon}
      </IconButton>
    </Tooltip>
  );
};
