import { ContextMenu } from "@radix-ui/themes";
import type { ReactElement, ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { ElementIds } from "~/api";
import { ZONE_DISPLAY_NAMES } from "~/components/panels/constants.ts";
import { usePanelActions, usePanelById, usePanelsByZone } from "~/components/panels/hooks.ts";
import type { PanelId, ZoneId } from "~/components/panels/types.ts";
import { isSplitZone, ZONE_IDS } from "~/components/panels/types.ts";

// Split sub-section zones are not standalone move targets.
const MOVE_TARGET_ZONE_IDS = ZONE_IDS.filter((zoneId) => !isSplitZone(zoneId));
import { isZoneMoveDisabled } from "~/components/panels/utils.ts";

type PanelContextMenuProps = {
  panelId: PanelId;
  zoneId: ZoneId;
  children: ReactNode;
  onOpenInModal?: () => void;
  onOpenChange?: (open: boolean) => void;
};

export const PanelContextMenu = ({
  panelId,
  zoneId,
  children,
  onOpenInModal,
  onOpenChange,
}: PanelContextMenuProps): ReactElement => {
  const panelDef = usePanelById(panelId);
  const panelsByZone = usePanelsByZone();
  const { movePanel } = usePanelActions();
  const navigate = useNavigate();

  const isDisabled = (targetZone: ZoneId): boolean =>
    targetZone === zoneId || isZoneMoveDisabled({ panelId, targetZone, panelsByZone });

  const handleMoveToZone = (targetZone: ZoneId): void => {
    if (isDisabled(targetZone)) return;
    movePanel(panelId, targetZone);
  };

  const handleConfigurePanels = (): void => {
    navigate(`/settings?section=PANELS&panel=${encodeURIComponent(panelId)}`);
  };

  return (
    <ContextMenu.Root onOpenChange={onOpenChange}>
      <ContextMenu.Trigger>{children}</ContextMenu.Trigger>
      <ContextMenu.Content size="1">
        <ContextMenu.Label>{panelDef?.displayName ?? panelId}</ContextMenu.Label>

        <ContextMenu.Sub>
          <ContextMenu.SubTrigger data-testid={ElementIds.PANEL_CONTEXT_MENU_MOVE_TO}>Move to</ContextMenu.SubTrigger>
          <ContextMenu.SubContent>
            {MOVE_TARGET_ZONE_IDS.map((targetZone) => (
              <ContextMenu.Item
                key={targetZone}
                disabled={isDisabled(targetZone)}
                onSelect={() => handleMoveToZone(targetZone)}
                data-testid={`${ElementIds.PANEL_CONTEXT_MENU_ZONE_OPTION}-${targetZone}`}
              >
                {ZONE_DISPLAY_NAMES[targetZone]}
              </ContextMenu.Item>
            ))}
          </ContextMenu.SubContent>
        </ContextMenu.Sub>

        <ContextMenu.Item onSelect={() => onOpenInModal?.()}>Open in Modal</ContextMenu.Item>

        <ContextMenu.Item onSelect={handleConfigurePanels} data-testid={ElementIds.PANEL_CONTEXT_MENU_CONFIGURE}>
          Configure panels…
        </ContextMenu.Item>

        {panelDef?.contextMenuItems && panelDef.contextMenuItems.length > 0 && (
          <>
            <ContextMenu.Separator />
            {panelDef.contextMenuItems.map((item) => (
              <ContextMenu.Item key={item.label} onSelect={() => item.action()}>
                {item.label}
              </ContextMenu.Item>
            ))}
          </>
        )}
      </ContextMenu.Content>
    </ContextMenu.Root>
  );
};
