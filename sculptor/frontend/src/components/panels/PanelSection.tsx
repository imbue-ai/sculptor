import { DropdownMenu, IconButton } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { Plus } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useMemo } from "react";

import {
  activePanelPerZoneAtom,
  panelRegistryAtom,
  panelsInZoneAtom,
  zoneOrderAtom,
} from "~/components/panels/atoms.ts";
import {
  useActivatePanel,
  useAddablePanels,
  useAddPanelToSection,
  useRemovePanelFromSection,
} from "~/components/panels/sectionHooks.ts";
import type { PanelId, ZoneId } from "~/components/panels/types.ts";
import { TabBar } from "~/components/tabs/TabBar.tsx";
import type { TabDefinition } from "~/components/tabs/types.ts";

import styles from "./PanelSection.module.scss";

type PanelSectionProps = {
  zone: ZoneId;
  side: "left" | "right";
};

/**
 * One panel section for a peripheral side (Left / Right). Shows a single tab
 * strip (styled to match the terminal tabs), a "+" dropdown to add panels not
 * currently in this section, a collapse toggle, and the active panel's content.
 * A section never auto-collapses — it can sit open and empty showing just "+".
 * (REQ-SECTION-1..3, REQ-ZONE-2)
 */
export const PanelSection = ({ zone, side }: PanelSectionProps): ReactElement => {
  const registry = useAtomValue(panelRegistryAtom);
  const panelIds = useAtomValue(panelsInZoneAtom(zone));
  const activePanelPerZone = useAtomValue(activePanelPerZoneAtom);
  const setZoneOrder = useSetAtom(zoneOrderAtom);
  const activatePanel = useActivatePanel();
  const addPanel = useAddPanelToSection();
  const removePanel = useRemovePanelFromSection();
  const addablePanels = useAddablePanels(zone);

  const activePanelId: PanelId | undefined =
    activePanelPerZone[zone] && panelIds.includes(activePanelPerZone[zone]!) ? activePanelPerZone[zone] : panelIds[0];

  const tabs = useMemo<Array<TabDefinition>>(
    () =>
      panelIds.flatMap((panelId) => {
        const def = registry.find((p) => p.id === panelId);
        if (!def) return [];
        const Icon = def.icon;
        return [
          {
            id: panelId,
            label: def.displayName,
            icon: <Icon size={13} />,
            dataTestId: `panel-tab-${panelId}`,
          },
        ];
      }),
    [panelIds, registry],
  );

  const handleReorder = useCallback(
    (newOrder: Array<string>): void => {
      setZoneOrder((prev) => ({ ...prev, [zone]: newOrder as Array<PanelId> }));
    },
    [setZoneOrder, zone],
  );

  const ActivePanelComponent = activePanelId ? registry.find((p) => p.id === activePanelId)?.component : undefined;

  const addButton = (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger>
        <IconButton
          variant="ghost"
          size="1"
          color="gray"
          className={styles.headerButton}
          aria-label="Add panel"
          data-testid={`panel-section-add-${side}`}
        >
          <Plus size={14} />
        </IconButton>
      </DropdownMenu.Trigger>
      <DropdownMenu.Content size="1" align={side === "left" ? "start" : "end"}>
        {addablePanels.length === 0 ? (
          <DropdownMenu.Item disabled>All panels added</DropdownMenu.Item>
        ) : (
          addablePanels.map((panel) => {
            const Icon = panel.icon;
            return (
              <DropdownMenu.Item key={panel.id} onSelect={() => addPanel(panel.id, zone)}>
                <Icon size={14} /> {panel.displayName}
              </DropdownMenu.Item>
            );
          })
        )}
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );

  return (
    <div className={styles.section} data-testid={`panel-section-${side}`}>
      <TabBar
        tabs={tabs}
        openTabIds={panelIds as Array<string>}
        activeTabId={activePanelId ?? ""}
        onActivate={(id) => activatePanel(id, zone)}
        onClose={(id) => removePanel(id)}
        onReorder={handleReorder}
        variant="compact"
        alwaysCloseable
        closeReplacesIcon
        tabBarClassName={styles.tabBar}
        rightContent={<div className={styles.headerControls}>{addButton}</div>}
      />
      <div className={styles.content} data-zone-id={zone} tabIndex={-1}>
        {ActivePanelComponent ? (
          <ActivePanelComponent />
        ) : (
          <div className={styles.emptyState}>
            <DropdownMenu.Root>
              <DropdownMenu.Trigger>
                <IconButton variant="soft" size="2" color="gray" aria-label="Add a panel">
                  <Plus size={18} />
                </IconButton>
              </DropdownMenu.Trigger>
              <DropdownMenu.Content size="1" align="center">
                {addablePanels.map((panel) => {
                  const Icon = panel.icon;
                  return (
                    <DropdownMenu.Item key={panel.id} onSelect={() => addPanel(panel.id, zone)}>
                      <Icon size={14} /> {panel.displayName}
                    </DropdownMenu.Item>
                  );
                })}
              </DropdownMenu.Content>
            </DropdownMenu.Root>
            <span className={styles.emptyHint}>Add a panel</span>
          </div>
        )}
      </div>
    </div>
  );
};
