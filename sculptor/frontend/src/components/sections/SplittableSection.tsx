// One section, rendered either as a single PanelSection or, when split, as primary +
// resize handle + secondary. Task 2.4 implements the real split/PanelSection/header/
// body rendering and its memo boundaries. This memoized placeholder keeps
// SectionGrid's memo boundary (primitive props) in place until then.

import type { ReactElement } from "react";
import { memo } from "react";

import type { SectionId } from "./sectionTypes.ts";

type SplittableSectionProps = { section: SectionId };

const SplittableSectionComponent = ({ section }: SplittableSectionProps): ReactElement => {
  return <div data-section-content={section} style={{ height: "100%", width: "100%" }} />;
};

export const SplittableSection = memo(SplittableSectionComponent);
