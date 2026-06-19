import { useDraggable } from "@dnd-kit/core";
import { Tooltip } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { type ReactElement, useState } from "react";

import { ElementIds } from "~/api";
import { activePanelPerZoneAtom, zoneAssignmentsAtom, zoneVisibilityAtom } from "~/components/panels/atoms.ts";
import { usePanelActions, usePanelById } from "~/components/panels/hooks.ts";
import { PanelContextMenu } from "~/components/panels/PanelContextMenu";
import type { PanelId, ZoneId } from "~/components/panels/types.ts";

import styles from "./SidebarIcon.module.scss";

const PANEL_ICON_TEST_IDS: Partial<Record<PanelId, ElementIds>> = {
  files: ElementIds.PANEL_ICON_FILES,
  actions: ElementIds.PANEL_ICON_ACTIONS,
  terminal: ElementIds.PANEL_ICON_TERMINAL,
  notes: ElementIds.PANEL_ICON_NOTES,
  browser: ElementIds.PANEL_ICON_BROWSER,
  skills: ElementIds.PANEL_ICON_SKILLS,
};

type SidebarIconProps = {
  panelId: PanelId;
  zoneId: ZoneId;
};

export const SidebarIcon = ({ panelId, zoneId }: SidebarIconProps): ReactElement | null => {
  const panelDef = usePanelById(panelId);
  const zoneAssignments = useAtomValue(zoneAssignmentsAtom);
  const activePanelPerZone = useAtomValue(activePanelPerZoneAtom);
  const zoneVisibility = useAtomValue(zoneVisibilityAtom);
  const { togglePanel } = usePanelActions();

  const [isContextMenuOpen, setIsContextMenuOpen] = useState(false);
  const { attributes, listeners, setNodeRef } = useDraggable({ id: panelId });

  if (!panelDef) return null;

  const zone = zoneAssignments[panelId];
  const isActive = activePanelPerZone[zone] === panelId && (zoneVisibility[zone] ?? false);
  const Icon = panelDef.icon;

  const handleClick = (): void => {
    togglePanel(panelId);
  };

  const iconClassName = [styles.icon, isActive ? styles.active : ""].filter(Boolean).join(" ");

  return (
    <div data-panel-icon={panelId} data-testid={PANEL_ICON_TEST_IDS[panelId]}>
      <Tooltip content={panelDef.displayName} side="right" open={isContextMenuOpen ? false : undefined}>
        <div>
          <PanelContextMenu panelId={panelId} zoneId={zoneId} onOpenChange={setIsContextMenuOpen}>
            <div ref={setNodeRef} className={iconClassName} onClick={handleClick} {...listeners} {...attributes}>
              <Icon size={18} />
            </div>
          </PanelContextMenu>
        </div>
      </Tooltip>
    </div>
  );
};
