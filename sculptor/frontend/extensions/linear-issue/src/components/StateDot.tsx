import type { ReactElement } from "react";

/** Small colored dot mirroring an issue's Linear workflow-state color. */
export const StateDot = ({ color }: { color: string }): ReactElement => (
  <span
    style={{
      width: 8,
      height: 8,
      borderRadius: "50%",
      background: color || "var(--gray-8)",
      display: "inline-block",
      flexShrink: 0,
    }}
  />
);
