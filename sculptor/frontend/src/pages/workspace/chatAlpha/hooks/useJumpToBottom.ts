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
  const shouldHide = isJumpSuppressed || isAtBottom || !hasMessages;

  // Hide immediately when the button should no longer show. Adjusting during
  // render with a prev-value guard keeps the synchronous reset out of the
  // effect and re-arms the 150ms debounce the next time the button reappears.
  const [prevShouldHide, setPrevShouldHide] = useState({ value: shouldHide });
  if (shouldHide !== prevShouldHide.value) {
    setPrevShouldHide({ value: shouldHide });
    if (shouldHide) {
      setIsVisible(false);
    }
  }

  // Debounced visibility: show after 150ms once the button should appear.
  useEffect(() => {
    if (shouldHide) {
      if (debounceTimer.current) {
        clearTimeout(debounceTimer.current);
        debounceTimer.current = null;
      }
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
  }, [shouldHide]);

  // "New activity" while the agent is actively streaming; once streaming
  // stops the label reverts to "Jump" (a neutral scroll-to-bottom action).
  const label: JumpToBottomLabel = isStreaming ? "new" : "jump";

  return { isVisible, label };
};
