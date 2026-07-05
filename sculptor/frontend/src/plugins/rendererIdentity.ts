import type { RendererIdentity } from "~/api";
import { isElectron } from "~/electron/platform.ts";

/**
 * sessionStorage key holding this page load's renderer id. Scoped to the tab/
 * window (sessionStorage, not localStorage) so each open renderer gets its own
 * stable id for the life of the page, and a reload mints a fresh one — matching
 * the backend's "one identity per page load" contract for `PluginCommandResult`.
 */
const RENDERER_ID_KEY = "sculptor-plugin-renderer-id";

/**
 * A stable id for this renderer instance, reused across every plugin-command
 * reply from this page load. Generated lazily and cached in sessionStorage so
 * it survives re-invocations within the same page but not a reload.
 *
 * Falls back to an in-memory id if sessionStorage is unavailable (e.g. a
 * privacy mode that throws on access) — the id is then merely page-stable in
 * practice rather than guaranteed, which is acceptable for correlating replies.
 */
let inMemoryRendererId: string | undefined;

export const getRendererId = (): string => {
  try {
    const existing = sessionStorage.getItem(RENDERER_ID_KEY);
    if (existing) return existing;
    const id = crypto.randomUUID();
    sessionStorage.setItem(RENDERER_ID_KEY, id);
    return id;
  } catch {
    inMemoryRendererId ??= crypto.randomUUID();
    return inMemoryRendererId;
  }
};

/**
 * This renderer's self-reported identity for a `PluginCommandResult`. The
 * `environment` is the renderer's own `isElectron()` verdict (not sniffed from
 * the WebSocket), and `origin` is the page origin — which determines the
 * localStorage domain, so two renderers on different origins can legitimately
 * hold different plugin state.
 */
export const getRendererIdentity = (): RendererIdentity => ({
  rendererId: getRendererId(),
  environment: isElectron() ? "electron" : "browser",
  origin: window.location.origin,
});
