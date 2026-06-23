import { useEffect, useRef, useState } from "react";

import type { ChatMessage } from "~/api";

const DEBOUNCE_MS = 150;

type JumpToBottomLabel = "jump" | "new";

type UseJumpToBottomReturn = {
  isVisible: boolean;
  label: JumpToBottomLabel;
};

export const useJumpToBottom = (
  isAtBottom: boolean,
  chatMessages: ReadonlyArray<ChatMessage>,
  isStreaming: boolean,
  isJumpSuppressed: boolean,
): UseJumpToBottomReturn => {
  const [isVisible, setIsVisible] = useState(false);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const hasMessages = chatMessages.length > 0;

  // Debounced visibility: show after 150ms, hide immediately
  useEffect(() => {
    if (isJumpSuppressed || isAtBottom || !hasMessages) {
      if (debounceTimer.current) {
        clearTimeout(debounceTimer.current);
        debounceTimer.current = null;
      }
      setIsVisible(false);
    } else {
      debounceTimer.current = setTimeout(() => {
        setIsVisible(true);
      }, DEBOUNCE_MS);
    }

    return (): void => {
      if (debounceTimer.current) {
        clearTimeout(debounceTimer.current);
      }
    };
  }, [isJumpSuppressed, isAtBottom, hasMessages]);

  // "New activity" while the agent is actively streaming; once streaming
  // stops the label reverts to "Jump" (a neutral scroll-to-bottom action).
  const label: JumpToBottomLabel = isStreaming ? "new" : "jump";

  return { isVisible, label };
};
