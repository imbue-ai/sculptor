import type { ReactElement } from "react";

// Glyph color for the mark drawn on a filled circle (check, ✕, exclamation).
// A near-white that reads on the saturated state colors of completed/cancelled/
// triage in both themes.
const CONTRAST = "#fff";

/**
 * A workflow-state glyph mirroring Linear's own state iconography, tinted with
 * the state's color. Linear ships no embeddable icon set, but the shape language
 * (dashed ring → hollow ring → half-pie → check → ✕) is a generic convention we
 * can draw ourselves — and, unlike Linear's logo, ours takes any color.
 *
 * `type` is Linear's `state.type`: backlog | unstarted | started | completed |
 * canceled | triage (Linear spells it with one "l"). Any other value (or
 * `null`) falls back to a neutral
 * hollow ring so the chip always has a leading glyph. Drawn in a 24-unit
 * viewBox at lucide's stroke weight (2) so it sits beside lucide icons at the
 * same visual size.
 */
export const StateIcon = ({
  type,
  color,
  size = 12,
}: {
  type: string | null;
  color: string;
  size?: number;
}): ReactElement => {
  // Incomplete states (backlog/unstarted) are low-emphasis in Linear, and the
  // colors it returns for them are near-white greys tuned for Linear's own
  // surfaces — they wash out on a light chip here. Their meaning is carried by
  // the shape (dashed vs hollow ring), so draw them in a theme-aware grey that
  // always contrasts, and reserve the issue's own color for the saturated
  // started/completed/cancelled/triage glyphs.
  const outline = "var(--gray-9)";
  const c = color || outline;
  const common = { width: size, height: size, viewBox: "0 0 24 24", fill: "none", "aria-hidden": true } as const;

  switch (type) {
    case "backlog":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="9" stroke={outline} strokeWidth="2" strokeDasharray="2.5 2.7" />
        </svg>
      );
    case "started":
      // Color ring with a right-half pie inside — Linear's "in progress".
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="9" stroke={c} strokeWidth="2" />
          <path d="M12 12V6.5A5.5 5.5 0 0 1 12 17.5Z" fill={c} />
        </svg>
      );
    case "completed":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="9" fill={c} />
          <path
            d="M8 12.5l2.5 2.5 5.5-6"
            stroke={CONTRAST}
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      );
    case "canceled":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="9" fill={c} />
          <path d="M9 9l6 6M15 9l-6 6" stroke={CONTRAST} strokeWidth="2" strokeLinecap="round" />
        </svg>
      );
    case "triage":
      // Filled disc with an exclamation — Linear's "needs triage".
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="9" fill={c} />
          <path d="M12 7.5v5" stroke={CONTRAST} strokeWidth="2" strokeLinecap="round" />
          <circle cx="12" cy="16.2" r="1.15" fill={CONTRAST} />
        </svg>
      );
    case "unstarted":
    default:
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="9" stroke={outline} strokeWidth="2" />
        </svg>
      );
  }
};
