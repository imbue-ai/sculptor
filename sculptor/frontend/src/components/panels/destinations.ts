// The list of sections a panel can be added to, named naturally for the Add
// Panel palette's destination selector.
//
// A section that is NOT split appears once under its plain name ("Left",
// "Center", "Right", "Bottom"). A section that IS split expands into its two
// halves with natural names derived from the split axis:
//   - horizontal (stacked) → "Top <base>" / "Bottom <base>"  (e.g. "Top right")
//   - vertical (side-by-side) → "<base> left" / "<base> right" (e.g. "Bottom left")
// So no "phantom" halves ever show when nothing is split.

import { useAtomValue } from "jotai";
import { useMemo } from "react";

import { SECTION_ZONES } from "~/components/panels/sectionHooks.ts";
import type { SectionSplit } from "~/components/panels/sectionLayoutAtoms.ts";
import { sectionSplitAtom } from "~/components/panels/sectionLayoutAtoms.ts";
import type { ZoneId } from "~/components/panels/types.ts";
import { toSplitZone } from "~/components/panels/types.ts";

export type PanelDestination = {
  /** The zone a panel lands in when this destination is chosen. */
  zone: ZoneId;
  /** Standalone label, capitalized (e.g. "Right", "Top right"). */
  label: string;
};

const BASE_LABEL: Partial<Record<ZoneId, string>> = {
  "top-left": "Left",
  center: "Center",
  "top-right": "Right",
  bottom: "Bottom",
};

/** Pure: turn the current split state into the ordered destination list. */
export const sectionDestinations = (
  sectionSplit: Partial<Record<ZoneId, SectionSplit>>,
): ReadonlyArray<PanelDestination> =>
  SECTION_ZONES.flatMap((zone): ReadonlyArray<PanelDestination> => {
    const base = BASE_LABEL[zone] ?? zone;
    const split = sectionSplit[zone];
    if (!split) return [{ zone, label: base }];
    const [primary, secondary] =
      split.axis === "horizontal"
        ? [`Top ${base.toLowerCase()}`, `Bottom ${base.toLowerCase()}`]
        : [`${base} left`, `${base} right`];
    return [
      { zone, label: primary },
      { zone: toSplitZone(zone), label: secondary },
    ];
  });

/** Lowercase a destination label for use inside a sentence (e.g. the pill:
 *  "add to the top right section"). Standalone labels stay capitalized. */
export const inSentence = (label: string): string => label.toLowerCase();

export const useDestinationSections = (): ReadonlyArray<PanelDestination> => {
  const sectionSplit = useAtomValue(sectionSplitAtom);
  return useMemo(() => sectionDestinations(sectionSplit), [sectionSplit]);
};
