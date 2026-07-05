import { Button, Flex, Text } from "@radix-ui/themes";
import { X } from "lucide-react";
import { type ReactElement, useCallback, useEffect, useRef, useState } from "react";

import { ElementIds } from "../../../api";
import { formatShortcutForDisplay } from "../../../common/keybindings/format.ts";
import { isMac } from "../../../electron/utils.ts";
import styles from "./HotkeyChip.module.scss";

type HotkeyState = "idle" | "recording" | "set";

type HotkeyChipProps = {
  value: string | undefined;
  onSet: (keys: string) => void;
  onClear: () => void;
  onRecordComplete?: (keys: string) => boolean | void;
  disabled?: boolean;
};

const formatHotkey = (keys: Array<string>): string =>
  keys
    .map((key) => {
      switch (key) {
        case "Meta":
          return "Cmd";
        case "Control":
          return "Ctrl";
        case "Alt":
          return "Alt";
        case "Shift":
          return "Shift";
        default:
          return key.toUpperCase();
      }
    })
    .join("+");

export const HotkeyChip = ({
  value,
  onSet,
  onClear,
  onRecordComplete,
  disabled = false,
}: HotkeyChipProps): ReactElement => {
  // `recording` is the only genuinely local state; idle/set are derived from `value`.
  const [isRecording, setIsRecording] = useState(false);
  const recordingChipRef = useRef<HTMLDivElement>(null);
  // Exit recording when `value` changes externally (e.g., websocket-driven update).
  // State-during-render: React re-renders immediately with the adjusted value.
  const [prevValue, setPrevValue] = useState(value);
  if (value !== prevValue) {
    setPrevValue(value);
    setIsRecording(false);
  }

  const state: HotkeyState = isRecording ? "recording" : value ? "set" : "idle";

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      e.preventDefault();
      e.stopImmediatePropagation();

      if (e.key === "Escape") {
        setIsRecording(false);
        return;
      }

      const isModifierOnly = ["Meta", "Control", "Alt", "Shift"].includes(e.key);
      if (isModifierOnly) return;

      const keys: Array<string> = [];
      const isMacOS = isMac();
      if (isMacOS) {
        if (e.metaKey) keys.push("Meta");
        if (e.ctrlKey && !e.metaKey) keys.push("Control");
      } else if (e.ctrlKey) {
        keys.push("Meta");
      }
      if (e.altKey) keys.push("Alt");
      if (e.shiftKey) keys.push("Shift");
      keys.push(e.key);

      const hotkeyString = formatHotkey(keys);
      if (onRecordComplete) {
        const shouldProceed = onRecordComplete(hotkeyString);
        if (shouldProceed === false) {
          setIsRecording(false);
          return;
        }
      }

      onSet(hotkeyString);
      setIsRecording(false);
    },
    [onSet, onRecordComplete],
  );

  useEffect(() => {
    if (!isRecording) return;
    window.addEventListener("keydown", handleKeyDown, { capture: true });
    return (): void => window.removeEventListener("keydown", handleKeyDown, { capture: true });
  }, [isRecording, handleKeyDown]);

  // Cancel recording on any click outside the recording chip. Listening on
  // mousedown (rather than click) means a click on another HotkeyChip's
  // "Click to set" button cancels this one before that chip's onClick fires
  // — guaranteeing only one chip is recording at a time.
  useEffect(() => {
    if (!isRecording) return;
    const handleMouseDown = (e: MouseEvent): void => {
      if (recordingChipRef.current && !recordingChipRef.current.contains(e.target as Node)) {
        setIsRecording(false);
      }
    };
    window.addEventListener("mousedown", handleMouseDown);
    return (): void => window.removeEventListener("mousedown", handleMouseDown);
  }, [isRecording]);

  const handleClick = (): void => {
    if (disabled || isRecording) return;
    setIsRecording(true);
  };

  const handleClear = (): void => {
    setIsRecording(false);
    onClear();
  };

  const opacityStyle = disabled ? { opacity: 0.5 } : undefined;

  if (state === "idle") {
    return (
      <Button
        variant="soft"
        onClick={handleClick}
        disabled={disabled}
        style={opacityStyle}
        data-testid={ElementIds.SETTINGS_HOTKEY_SET_BUTTON}
      >
        Click to set
      </Button>
    );
  }

  if (state === "recording") {
    return (
      <Flex
        ref={recordingChipRef}
        className={styles.hotkeyRecording}
        align="center"
        justify="center"
        py="2"
        px="4"
        data-testid={ElementIds.SETTINGS_HOTKEY_SET_BUTTON}
      >
        <Text size="2">Press keys... Esc to cancel</Text>
      </Flex>
    );
  }
  return (
    <Flex
      className={styles.hotkeySet}
      align="center"
      justify="between"
      gap="3"
      py="2"
      px="4"
      onClick={handleClick}
      aria-disabled={disabled}
      style={{ cursor: disabled ? "default" : "pointer", ...opacityStyle }}
      data-testid={ElementIds.SETTINGS_HOTKEY_SET_BUTTON}
    >
      <Text size="2">{formatShortcutForDisplay(value)}</Text>
      <Button
        variant="ghost"
        size="1"
        onClick={(e) => {
          e.stopPropagation();
          handleClear();
        }}
        disabled={disabled}
        className={styles.hotkeyClear}
        data-testid={ElementIds.SETTINGS_HOTKEY_CLEAR_BUTTON}
      >
        <X size={14} />
      </Button>
    </Flex>
  );
};
