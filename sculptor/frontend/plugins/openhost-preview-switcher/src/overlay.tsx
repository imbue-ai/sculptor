import { FlaskConical, RefreshCw, X } from "lucide-react";
import type { CSSProperties, ReactElement } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

/**
 * The switcher overlay. Two modes, decided from the URL:
 *
 * - On the deployed app (path not under /proxy/): a "previews" pill that lists
 *   the live Vite dev previews found in the band and switches to one on tap.
 * - On a preview (path under /proxy/<port>/): an amber "PREVIEW" badge showing
 *   this preview's identity (its sculptor-preview meta, injected per index.html
 *   request by vite.base.config.ts), with a way back to the main app.
 *
 * Liveness probing mirrors openhost-preview-fallback.html: a HEAD of
 * /proxy/<port>/ answered by nginx itself (502/503/504) means nothing listens
 * on that port; any other status means a dev server replied through the proxy.
 * Only the 51000-51099 range is scanned (the range launch-preview.sh suggests);
 * the /proxy/ switchboard page, linked from the expanded panel, covers
 * full-band scans.
 *
 * Switching is a plain same-origin navigation (window.location / <a href>), NOT
 * openExternal: prod and previews share the origin and the PWA scope, so
 * navigating keeps the installed PWA in its standalone window — which is the
 * whole point. The current #/ route is carried across so the same screen
 * reopens on the other bundle.
 */

const QUICK_BAND_START = 51000;
const QUICK_BAND_END = 51099;
const SCAN_CONCURRENCY = 16;

/** nginx's own dead-upstream statuses; a live dev server never produces them. */
const NGINX_DOWN_STATUSES = new Set([502, 503, 504]);

type Preview = {
  port: number;
  /** Identity from the preview's sculptor-preview meta (or its <title>). */
  label: string;
};

const getPreviewPort = (): number | null => {
  const match = window.location.pathname.match(/^\/proxy\/(5[1-9][0-9][0-9][0-9])(\/|$)/);
  return match ? Number(match[1]) : null;
};

const probeAlive = async (port: number): Promise<boolean> => {
  try {
    const response = await fetch(`/proxy/${port}/`, { method: "HEAD", cache: "no-store" });
    return !NGINX_DOWN_STATUSES.has(response.status);
  } catch {
    return false;
  }
};

const fetchLabel = async (port: number): Promise<string> => {
  try {
    const response = await fetch(`/proxy/${port}/`, { cache: "no-store" });
    const text = await response.text();
    const meta = text.match(/<meta name="sculptor-preview" content="([^"]*)"/);
    if (meta) return meta[1];
    const title = text.match(/<title>([^<]*)<\/title>/i);
    return title ? title[1] : "";
  } catch {
    return "";
  }
};

/**
 * Whether this deployment sits behind the OpenHost nginx front. There /proxy/
 * (no port) serves the switchboard page, marked with a sculptor-switchboard
 * meta; on any other deployment the SPA catch-all answers with the app's own
 * index.html, so the overlay renders nothing at all.
 */
const probeOpenhostFront = async (): Promise<boolean> => {
  try {
    const response = await fetch("/proxy/", { cache: "no-store" });
    return response.ok && (await response.text()).includes('name="sculptor-switchboard"');
  } catch {
    return false;
  }
};

const scanQuickBand = async (onFound: (preview: Preview) => void): Promise<void> => {
  const ports: Array<number> = [];
  for (let port = QUICK_BAND_START; port <= QUICK_BAND_END; port++) ports.push(port);
  const worker = async (): Promise<void> => {
    for (let port = ports.shift(); port !== undefined; port = ports.shift()) {
      if (await probeAlive(port)) onFound({ port, label: await fetchLabel(port) });
    }
  };
  await Promise.all(Array.from({ length: SCAN_CONCURRENCY }, () => worker()));
};

/** Same-origin navigation carrying the current #/ route to the other bundle. */
const navigateKeepingRoute = (basePath: string): void => {
  window.location.assign(basePath + window.location.hash);
};

const containerStyle: CSSProperties = {
  position: "fixed",
  // The bottom-left corner of PageLayout's dev/version footer strip, whose
  // left column is empty — visually part of the dev provisions, overlapping
  // nothing.
  bottom: 4,
  left: 8,
  pointerEvents: "auto",
  fontSize: 11,
  color: "var(--gray-11)",
};

const pillStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 4,
  padding: "2px 8px",
  borderRadius: 999,
  border: "1px solid var(--gray-a6)",
  background: "var(--color-panel-solid)",
  color: "inherit",
  font: "inherit",
  cursor: "pointer",
};

const previewPillStyle: CSSProperties = {
  ...pillStyle,
  border: "1px solid var(--amber-a7)",
  background: "var(--amber-a3)",
  color: "var(--amber-11)",
};

const panelStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 2,
  minWidth: 240,
  maxWidth: 340,
  padding: 8,
  borderRadius: "var(--radius-4)",
  border: "1px solid var(--gray-a6)",
  background: "var(--color-panel-solid)",
  boxShadow: "var(--shadow-4)",
};

const rowStyle: CSSProperties = {
  display: "block",
  width: "100%",
  boxSizing: "border-box",
  padding: "4px 6px",
  borderRadius: "var(--radius-2)",
  border: "none",
  background: "none",
  color: "var(--gray-12)",
  font: "inherit",
  textAlign: "left",
  textDecoration: "none",
  cursor: "pointer",
};

const headerButtonStyle: CSSProperties = {
  display: "inline-flex",
  padding: 2,
  border: "none",
  background: "none",
  color: "var(--gray-10)",
  cursor: "pointer",
};

export const PreviewSwitcherOverlay = (): ReactElement | null => {
  const previewPort = useMemo(getPreviewPort, []);
  // On a preview the front is implied by the URL; on prod probe for it once.
  const [onOpenhostFront, setOnOpenhostFront] = useState(previewPort !== null);
  const [expanded, setExpanded] = useState(false);
  const [previews, setPreviews] = useState<Array<Preview>>([]);
  const [scanning, setScanning] = useState(false);

  // This page's own identity: the meta reflects the last full load (HMR does
  // not refetch index.html), which is exactly what this page is running.
  const ownIdentity = useMemo(
    (): string => document.querySelector('meta[name="sculptor-preview"]')?.getAttribute("content") ?? "",
    [],
  );

  useEffect(() => {
    if (previewPort === null) {
      void probeOpenhostFront().then(setOnOpenhostFront);
    }
  }, [previewPort]);

  const rescan = useCallback((): void => {
    setPreviews([]);
    setScanning(true);
    void scanQuickBand((found) =>
      setPreviews((current) =>
        [...current.filter((preview) => preview.port !== found.port), found].sort((a, b) => a.port - b.port),
      ),
    ).finally(() => setScanning(false));
  }, []);

  useEffect(() => {
    if (onOpenhostFront) rescan();
  }, [onOpenhostFront, rescan]);

  if (!onOpenhostFront) return null;

  const others = previews.filter((preview) => preview.port !== previewPort);

  if (!expanded) {
    const pillText =
      previewPort === null
        ? `previews${previews.length > 0 ? ` (${previews.length})` : ""}`
        : `:${previewPort}${ownIdentity === "" ? "" : ` · ${ownIdentity}`}`;
    return (
      <div style={containerStyle}>
        <button
          type="button"
          style={previewPort === null ? pillStyle : previewPillStyle}
          title={previewPort === null ? "Live dev previews" : "This is a dev preview — tap to switch"}
          onClick={(): void => setExpanded(true)}
        >
          <FlaskConical size={11} />
          {pillText}
        </button>
      </div>
    );
  }

  return (
    <div style={containerStyle}>
      <div style={panelStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: 4, padding: "0 6px 4px" }}>
          <span style={{ fontWeight: 600, flex: 1 }}>Dev previews</span>
          {scanning ? <span style={{ color: "var(--gray-10)" }}>scanning…</span> : null}
          <button type="button" style={headerButtonStyle} title="Rescan" onClick={rescan}>
            <RefreshCw size={12} />
          </button>
          <button type="button" style={headerButtonStyle} title="Close" onClick={(): void => setExpanded(false)}>
            <X size={12} />
          </button>
        </div>
        {previewPort === null ? null : (
          <>
            <div style={{ padding: "0 6px", color: "var(--amber-11)" }}>
              on :{previewPort}
              {ownIdentity === "" ? "" : ` · ${ownIdentity}`}
            </div>
            <button type="button" style={rowStyle} onClick={(): void => navigateKeepingRoute("/")}>
              ← Back to main app
            </button>
          </>
        )}
        {others.map((preview) => (
          <button
            key={preview.port}
            type="button"
            style={rowStyle}
            onClick={(): void => navigateKeepingRoute(`/proxy/${preview.port}/`)}
          >
            :{preview.port}
            {preview.label === "" ? "" : ` · ${preview.label}`}
          </button>
        ))}
        {others.length === 0 && !scanning ? (
          <div style={{ padding: "0 6px", color: "var(--gray-10)" }}>
            no other live previews in :{QUICK_BAND_START}–:{QUICK_BAND_END}
          </div>
        ) : null}
        <a style={{ ...rowStyle, color: "var(--gray-10)" }} href={`/proxy/${window.location.hash}`}>
          switchboard (full-band scan) →
        </a>
      </div>
    </div>
  );
};
