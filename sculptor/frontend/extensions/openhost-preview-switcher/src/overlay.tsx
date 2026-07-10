import { Button, Flex, IconButton, Text } from "@radix-ui/themes";
import { FlaskConical, RefreshCw, X } from "lucide-react";
import type { CSSProperties, MouseEvent, ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { NGINX_DOWN_STATUSES, QUICK_BAND_END, QUICK_BAND_START, parsePreviewLabel, parsePreviewPort } from "./scan.ts";

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
 * whole point. The current #/ route is read at click time and carried across so
 * the same screen reopens on the other bundle.
 */

const SCAN_CONCURRENCY = 16;
/**
 * Mirrors the fallback page's probe timeout. nginx proxies the band with a
 * day-long read timeout, so a listener that accepts but never answers would
 * otherwise hang its scan lane (and the "scanning" state) forever.
 */
const PROBE_TIMEOUT_MS = 5000;

type Preview = {
  port: number;
  /** Identity from the preview's sculptor-preview meta (or its <title>). */
  label: string;
};

const probeAlive = async (port: number): Promise<boolean> => {
  try {
    const response = await fetch(`/proxy/${port}/`, {
      method: "HEAD",
      cache: "no-store",
      signal: AbortSignal.timeout(PROBE_TIMEOUT_MS),
    });
    return !NGINX_DOWN_STATUSES.has(response.status);
  } catch {
    return false;
  }
};

const fetchLabel = async (port: number): Promise<string> => {
  try {
    const response = await fetch(`/proxy/${port}/`, {
      cache: "no-store",
      signal: AbortSignal.timeout(PROBE_TIMEOUT_MS),
    });
    return parsePreviewLabel(await response.text());
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
    const response = await fetch("/proxy/", { cache: "no-store", signal: AbortSignal.timeout(PROBE_TIMEOUT_MS) });
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
  bottom: "var(--space-1)",
  left: "var(--space-2)",
  pointerEvents: "auto",
};

const panelStyle: CSSProperties = {
  minWidth: 240,
  maxWidth: 340,
  padding: "var(--space-2)",
  borderRadius: "var(--radius-4)",
  border: "1px solid var(--gray-a6)",
  background: "var(--color-panel-solid)",
  boxShadow: "var(--shadow-4)",
};

/** Radix ghost buttons hug content; stretch list rows full-width instead. */
const rowStyle: CSSProperties = {
  width: "100%",
  justifyContent: "flex-start",
};

export const PreviewSwitcherOverlay = (): ReactElement | null => {
  const previewPort = useMemo((): number | null => parsePreviewPort(window.location.pathname), []);
  // On a preview the front is implied by the URL; on prod probe for it once.
  const [isOnOpenhostFront, setIsOnOpenhostFront] = useState(previewPort !== null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [previews, setPreviews] = useState<Array<Preview>>([]);
  const [isScanning, setIsScanning] = useState(false);
  const isScanningRef = useRef(false);
  const isDisposedRef = useRef(false);

  // This page's own identity: the meta reflects the last full load (HMR does
  // not refetch index.html), which is exactly what this page is running.
  const ownIdentity = useMemo(
    (): string => document.querySelector('meta[name="sculptor-preview"]')?.getAttribute("content") ?? "",
    [],
  );

  useEffect(() => {
    return (): void => {
      isDisposedRef.current = true;
    };
  }, []);

  useEffect(() => {
    if (previewPort !== null) return undefined;
    // The extension can be unloaded mid-probe (sculpt extension unload/reload) —
    // don't set state on the unmounted overlay.
    let isIgnored = false;
    void probeOpenhostFront().then((isFront) => {
      if (!isIgnored) setIsOnOpenhostFront(isFront);
    });
    return (): void => {
      isIgnored = true;
    };
  }, [previewPort]);

  const rescan = useCallback((): void => {
    if (isScanningRef.current) return;
    isScanningRef.current = true;
    setIsScanning(true);
    setPreviews([]);
    void scanQuickBand((found) => {
      if (isDisposedRef.current) return;
      setPreviews((current) =>
        [...current.filter((preview) => preview.port !== found.port), found].sort((a, b) => a.port - b.port),
      );
    }).finally(() => {
      isScanningRef.current = false;
      if (!isDisposedRef.current) setIsScanning(false);
    });
  }, []);

  useEffect(() => {
    if (isOnOpenhostFront) rescan();
  }, [isOnOpenhostFront, rescan]);

  const openSwitchboard = useCallback((event: MouseEvent<HTMLAnchorElement>): void => {
    // Navigate at click time so the CURRENT #/ route is carried across (an
    // href captured at render time would go stale — hash-route changes don't
    // re-render this overlay). The href stays for middle-click/long-press.
    event.preventDefault();
    navigateKeepingRoute("/proxy/");
  }, []);

  if (!isOnOpenhostFront) return null;

  const isPreview = previewPort !== null;
  const others = previews.filter((preview) => preview.port !== previewPort);

  if (!isExpanded) {
    const pillText = isPreview
      ? `:${previewPort}${ownIdentity === "" ? "" : ` · ${ownIdentity}`}`
      : `previews${previews.length > 0 ? ` (${previews.length})` : ""}`;
    return (
      <div style={containerStyle}>
        <Button
          size="1"
          radius="full"
          variant="surface"
          color={isPreview ? "amber" : "gray"}
          title={isPreview ? "This is a dev preview — tap to switch" : "Live dev previews"}
          onClick={(): void => setIsExpanded(true)}
        >
          <FlaskConical size={11} />
          {pillText}
        </Button>
      </div>
    );
  }

  return (
    <div style={containerStyle}>
      <Flex direction="column" gap="1" style={panelStyle}>
        <Flex align="center" gap="2" px="1">
          <Text size="1" weight="bold" style={{ flex: 1 }}>
            Dev previews
          </Text>
          {isScanning ? (
            <Text size="1" color="gray">
              scanning…
            </Text>
          ) : null}
          <IconButton
            size="1"
            variant="ghost"
            color="gray"
            aria-label="Rescan"
            title="Rescan"
            disabled={isScanning}
            onClick={rescan}
          >
            <RefreshCw size={12} />
          </IconButton>
          <IconButton
            size="1"
            variant="ghost"
            color="gray"
            aria-label="Close"
            title="Close"
            onClick={(): void => setIsExpanded(false)}
          >
            <X size={12} />
          </IconButton>
        </Flex>
        {isPreview ? (
          <>
            <Text size="1" color="amber" style={{ padding: "0 var(--space-1)" }}>
              on :{previewPort}
              {ownIdentity === "" ? "" : ` · ${ownIdentity}`}
            </Text>
            <Button
              size="1"
              variant="ghost"
              color="gray"
              style={rowStyle}
              onClick={(): void => navigateKeepingRoute("/")}
            >
              ← Back to main app
            </Button>
          </>
        ) : null}
        {others.map((preview) => (
          <Button
            key={preview.port}
            size="1"
            variant="ghost"
            color="gray"
            style={rowStyle}
            onClick={(): void => navigateKeepingRoute(`/proxy/${preview.port}/`)}
          >
            :{preview.port}
            {preview.label === "" ? "" : ` · ${preview.label}`}
          </Button>
        ))}
        {others.length === 0 && !isScanning ? (
          <Text size="1" color="gray" style={{ padding: "0 var(--space-1)" }}>
            no other live previews in :{QUICK_BAND_START}–:{QUICK_BAND_END}
          </Text>
        ) : null}
        <Button asChild size="1" variant="ghost" color="gray" style={rowStyle}>
          <a href="/proxy/" onClick={openSwitchboard}>
            switchboard (full-band scan) →
          </a>
        </Button>
      </Flex>
    </div>
  );
};
