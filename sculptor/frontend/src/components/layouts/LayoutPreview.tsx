// The mini section-grid preview of a layout's arrangement, shared by the
// save/edit dialog and the tidy confirmation. It reads a CapturedLayout (or the
// live workspace) and lays the static panels out across left/center/right/bottom
// cells, marking the fixed agent/terminal homes with dashed chips. The tidy
// confirmation passes `removingPanelIds` to tint the panels a layout would close.

import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";
import { openPanelsInSubSection, SECTION_LABELS } from "~/components/sections/layoutQueries.ts";
import type { CapturedLayout, WorkspaceLayoutState } from "~/components/sections/persistence/types.ts";
import { isMultiInstancePanelId } from "~/components/sections/registry/dynamicPanels.tsx";
import { panelRegistryAtom } from "~/components/sections/registry/panelRegistry.ts";
import { workspaceLayoutAtom } from "~/components/sections/sectionAtoms.ts";
import type { PanelId, SectionId } from "~/components/sections/sectionTypes.ts";
import { toSecondary } from "~/components/sections/sectionTypes.ts";

import styles from "./LayoutPreview.module.scss";

const PREVIEW_SECTIONS: ReadonlyArray<{ section: SectionId; areaClass: string }> = [
  { section: "left", areaClass: styles.cellLeft },
  { section: "center", areaClass: styles.cellCenter },
  { section: "right", areaClass: styles.cellRight },
  { section: "bottom", areaClass: styles.cellBottom },
];

// A layout never declares agents/terminals; default seeding creates them in fixed
// sections. The preview marks those homes with a dashed chip.
const DEFAULT_DYNAMIC_CHIPS: Partial<Record<SectionId, string>> = {
  center: "Agent default",
  bottom: "Terminal default",
};

type LayoutPreviewProps = {
  // The layout's stored capture (edit/save mode); when omitted the preview reflects
  // the live workspace arrangement (create mode, and the tidy confirmation). A
  // CapturedLayout carries the placement/order/activePanel the preview reads, so it
  // stands in for the live workspace layout structurally.
  source?: CapturedLayout;
  // Panels to render with the danger "removing" treatment — the tidy confirmation
  // passes the panels the target layout will close.
  removingPanelIds?: ReadonlySet<PanelId>;
  // Labels for the dashed agent/terminal home chips. The default names them as the
  // seeding "default" homes; the tidy dialog names the live agent/terminal.
  dynamicChips?: Partial<Record<SectionId, string>>;
};

export const LayoutPreview = ({
  source,
  removingPanelIds,
  dynamicChips = DEFAULT_DYNAMIC_CHIPS,
}: LayoutPreviewProps): ReactElement => {
  const workspaceLayout = useAtomValue(workspaceLayoutAtom);
  const registry = useAtomValue(panelRegistryAtom);
  const dangerColor = useThemeDangerColor();
  const layout: WorkspaceLayoutState = source ?? workspaceLayout;

  const nameOf = (id: PanelId): string => registry.find((definition) => definition.id === id)?.displayName ?? id;

  return (
    // data-accent-color remaps --accent-* to the dialog's danger scale so the
    // "removing" tint matches the confirm button even under a custom danger theme.
    <div className={styles.preview} data-accent-color={removingPanelIds !== undefined ? dangerColor : undefined}>
      {PREVIEW_SECTIONS.map(({ section, areaClass }) => {
        const ids = [
          ...openPanelsInSubSection(layout, section),
          ...openPanelsInSubSection(layout, toSecondary(section)),
        ];
        const statics = ids.filter((id) => !isMultiInstancePanelId(id));
        const activeId = layout.activePanel[section];
        const defaultChip = dynamicChips[section];

        return (
          <div
            key={section}
            className={`${styles.cell} ${statics.length > 0 ? styles.cellSaved : styles.cellStays} ${areaClass}`}
          >
            <div className={styles.cellLabel}>{SECTION_LABELS[section]}</div>
            {statics.length > 0 || defaultChip !== undefined ? (
              <div className={styles.cellTabs}>
                {statics.map((id) => {
                  const isRemoving = removingPanelIds?.has(id) === true;
                  const tabClass = isRemoving ? styles.tabRemoving : id === activeId ? styles.tabActive : "";
                  return (
                    <span key={id} className={`${styles.tab} ${tabClass}`}>
                      {nameOf(id)}
                    </span>
                  );
                })}
                {defaultChip !== undefined ? (
                  <span className={`${styles.tab} ${styles.tabDefault}`}>{defaultChip}</span>
                ) : undefined}
              </div>
            ) : undefined}
          </div>
        );
      })}
    </div>
  );
};
