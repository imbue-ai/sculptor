import { useCallback, useEffect, useRef, useState } from "react";

const COPIED_FEEDBACK_MS = 1500;

/** Copy text to the clipboard, and report it as copied for a moment afterwards. */
export const useCopyFeedback = (): { isCopied: boolean; copy: (text: string) => void } => {
  const [isCopied, setIsCopied] = useState<boolean>(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Prevent setState-on-unmount from the feedback timer.
  useEffect(() => {
    return (): void => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const copy = useCallback((text: string): void => {
    navigator.clipboard
      .writeText(text)
      .then(() => {
        setIsCopied(true);
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(() => setIsCopied(false), COPIED_FEEDBACK_MS);
      })
      .catch((error) => {
        console.warn("Failed to copy to the clipboard.", error);
      });
  }, []);

  return { isCopied, copy };
};
