import { Button } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ElementIds } from "~/api";
import { formatShortcutForDisplay } from "~/common/ShortcutUtils.ts";
import { zenModeActiveAtom } from "~/components/panels/atoms.ts";
import { useZenMode } from "~/components/panels/hooks.ts";

import styles from "./ExitZenModeButton.module.scss";

/** Floating button near the macOS traffic lights that appears when the mouse enters the top-left hot zone. */
export const ExitZenModeButton = (): ReactElement | null => {
  const isZenModeActive = useAtomValue(zenModeActiveAtom);
  const { toggleZenMode } = useZenMode();
  const [isVisible, setIsVisible] = useState(false);
  const hideTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearHideTimeout = useCallback(() => {
    if (hideTimeout.current !== null) {
      clearTimeout(hideTimeout.current);
      hideTimeout.current = null;
    }
  }, []);

  useEffect((): (() => void) => {
    return () => clearHideTimeout();
  }, [clearHideTimeout]);

  const handleMouseEnter = useCallback(() => {
    clearHideTimeout();
    setIsVisible(true);
  }, [clearHideTimeout]);

  const handleMouseLeave = useCallback(() => {
    clearHideTimeout();
    // Small delay so the cursor can travel from the hot zone to the button without flickering.
    hideTimeout.current = setTimeout(() => setIsVisible(false), 150);
  }, [clearHideTimeout]);

  if (!isZenModeActive) return null;

  return (
    <div className={styles.hotZone} onMouseEnter={handleMouseEnter} onMouseLeave={handleMouseLeave}>
      <div
        className={`${styles.container} ${isVisible ? styles.visible : ""}`}
        data-testid={ElementIds.EXIT_ZEN_MODE_BUTTON}
      >
        <Button variant="soft" color="gray" size="1" className={styles.button} onClick={toggleZenMode}>
          Exit zen mode <kbd className={styles.kbd}>{formatShortcutForDisplay("Meta+Shift+\\")}</kbd>
        </Button>
      </div>
    </div>
  );
};
