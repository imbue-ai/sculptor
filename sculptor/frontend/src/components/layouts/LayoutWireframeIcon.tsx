// A small per-layout wireframe icon derived from the captured geometry: an outer
// frame plus a divider for each expanded surrounding section, so the icon is a
// quick mini-map of the layout's shape (left column, right column, bottom row).
// Derived rather than stored so it can never drift from the layout it represents.

import type { ReactElement } from "react";

import type { CapturedLayout } from "~/components/sections/persistence/types.ts";

type LayoutWireframeIconProps = {
  captured: CapturedLayout;
  size?: number;
};

export const LayoutWireframeIcon = ({ captured, size = 16 }: LayoutWireframeIconProps): ReactElement => {
  const dividers: Array<string> = [];
  if (captured.expanded.left === true) {
    dividers.push("M9 3v18");
  }

  if (captured.expanded.right === true) {
    dividers.push("M15 3v18");
  }

  if (captured.expanded.bottom === true) {
    dividers.push("M3 15h18");
  }

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect width="18" height="18" x="3" y="3" rx="2" />
      {dividers.map((path) => (
        <path key={path} d={path} />
      ))}
    </svg>
  );
};
