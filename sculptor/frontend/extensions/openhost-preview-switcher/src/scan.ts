/**
 * Pure helpers for the preview-band scanning done by the overlay. Kept free of
 * DOM/window access so they are unit-testable (see scan.test.ts); the fetch
 * plumbing that uses them lives in overlay.tsx.
 */

/** Loopback preview band fronted by the OpenHost nginx /proxy route. */
export const QUICK_BAND_START = 51000;
/** launch-preview.sh suggests this range, so the quick scan covers it. */
export const QUICK_BAND_END = 51099;

/** nginx's own dead-upstream statuses; a live dev server never produces them. */
export const NGINX_DOWN_STATUSES: ReadonlySet<number> = new Set([502, 503, 504]);

/** The preview port encoded in a `/proxy/<port>/` pathname, or null off-preview. */
export const parsePreviewPort = (pathname: string): number | null => {
  const match = pathname.match(/^\/proxy\/(5[1-9][0-9][0-9][0-9])(\/|$)/);
  return match ? Number(match[1]) : null;
};

/**
 * Best-effort identity for a live preview's index.html: the sculptor-preview
 * meta if the dev server injects one (see previewIdentity in
 * vite.base.config.ts), else the document title, else "".
 */
export const parsePreviewLabel = (html: string): string => {
  const meta = html.match(/<meta name="sculptor-preview" content="([^"]*)"/);
  if (meta) return meta[1];
  const title = html.match(/<title>([^<]*)<\/title>/i);
  return title ? title[1] : "";
};
