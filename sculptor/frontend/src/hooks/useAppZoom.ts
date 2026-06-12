import { useAtom } from "jotai";
import { useEffect, useRef } from "react";

import { clampZoomLevel, factorForZoomLevel, zoomLevelAtom } from "../common/state/atoms/zoom.ts";
import type { ZoomCommand } from "../shared/types.ts";

// Page zoom is owned by the renderer so the Chromium repaint
// (webFrame.setZoomFactor) and the --app-zoom CSS variable update happen in
// the same synchronous task — otherwise the title-bar gutter recomputes one
// frame late and the top-bar contents jitter on every Cmd+/Cmd- press.
//
// The macOS traffic-light buttons are drawn by the OS at a fixed device-pixel
// size, so the gutter divides its base px values by --app-zoom to stay pegged
// to them at any zoom level.

export const useAppZoom = (): void => {
  const [level, setStoredLevel] = useAtom(zoomLevelAtom);

  // Skip pushing the renderer zoom factor on mount when the user hasn't
  // actually zoomed yet — Electron's default is already 1.0, and an
  // unsolicited setZoomFactor(1) call appears to disturb the Browser panel's
  // <webview> guest-visible-size calculation on Linux (passes locally on
  // macOS, fails reliably on the Linux CI runner). Once we've ever pushed a
  // non-default factor, every subsequent level change (including a return
  // to 1.0) goes through setZoomFactor so the renderer stays in sync.
  const hasAppliedRef = useRef(false);

  const applyFactor = (factor: number, force: boolean): void => {
    document.documentElement.style.setProperty("--app-zoom", String(factor));
    if (force || hasAppliedRef.current || factor !== 1) {
      hasAppliedRef.current = true;
      window.sculptor?.setZoomFactor(factor);
    }
  };

  // Sync the rendered zoom whenever the persisted level changes (initial mount,
  // cross-tab updates via storage events, or local writes through setStoredLevel).
  useEffect(() => {
    applyFactor(factorForZoomLevel(clampZoomLevel(level)), false);
  }, [level]);

  useEffect(() => {
    const sculptor = window.sculptor;
    if (!sculptor) return;
    const wrappedCallback = sculptor.onZoomCommand((command: ZoomCommand) => {
      switch (command.kind) {
        case "in":
          setStoredLevel((prev) => clampZoomLevel(prev + 1));
          break;
        case "out":
          setStoredLevel((prev) => clampZoomLevel(prev - 1));
          break;
        case "reset":
          setStoredLevel(0);
          break;
        case "setFactor":
          // Test/override path (SCULPTOR_ZOOM_FACTOR): don't update the
          // persisted level so the override stays scoped to this session.
          // Force the setZoomFactor call so the override always lands.
          applyFactor(command.factor, true);
          break;
      }
    });
    return (): void => sculptor.removeZoomCommandListener(wrappedCallback);
  }, [setStoredLevel]);
};
