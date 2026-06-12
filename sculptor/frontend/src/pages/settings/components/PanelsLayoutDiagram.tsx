import type { DragEndEvent, DragOverEvent, DragStartEvent } from "@dnd-kit/core";
import { DndContext, PointerSensor, useDraggable, useDroppable, useSensor, useSensors } from "@dnd-kit/core";
import { Button, Flex, Text } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { type KeyboardEvent as ReactKeyboardEvent, type ReactElement, useState } from "react";

import { ElementIds } from "~/api";
import { panelRegistryAtom, panelsInZoneAtom, zoneAssignmentsAtom } from "~/components/panels/atoms.ts";
import { ZONE_DISPLAY_NAMES } from "~/components/panels/constants.ts";
import { usePanelActions, usePanelsByZone } from "~/components/panels/hooks.ts";
import type { PanelDefinition, PanelId, ZoneId } from "~/components/panels/types.ts";
import { isZoneMoveDisabled } from "~/components/panels/utils.ts";

import styles from "./PanelsLayoutDiagram.module.scss";

type PanelsLayoutDiagramProps = {
  filterZone: ZoneId | null;
  onFilterZone: (zone: ZoneId | null) => void;
};

export const PanelsLayoutDiagram = ({ filterZone, onFilterZone }: PanelsLayoutDiagramProps): ReactElement => {
  const zoneAssignments = useAtomValue(zoneAssignmentsAtom);
  const panelsByZone = usePanelsByZone();
  const { movePanel } = usePanelActions();
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));
  const [activeDragId, setActiveDragId] = useState<PanelId | null>(null);
  const [overZone, setOverZone] = useState<ZoneId | null>(null);

  const handleDragStart = (event: DragStartEvent): void => {
    setActiveDragId(event.active.id as PanelId);
  };

  const handleDragOver = (event: DragOverEvent): void => {
    const id = event.over?.id;
    setOverZone(id ? (id as ZoneId) : null);
  };

  const handleDragEnd = (event: DragEndEvent): void => {
    setActiveDragId(null);
    setOverZone(null);
    const panelId = event.active.id as PanelId;
    const targetZone = event.over?.id as ZoneId | undefined;
    if (!targetZone) return;
    const currentZone = zoneAssignments[panelId];
    if (!currentZone || currentZone === targetZone) return;
    if (isZoneMoveDisabled({ panelId, targetZone, panelsByZone })) return;
    movePanel(panelId, targetZone);
  };

  const handleDragCancel = (): void => {
    setActiveDragId(null);
    setOverZone(null);
  };

  const isInvalidHover =
    activeDragId !== null &&
    overZone !== null &&
    isZoneMoveDisabled({
      panelId: activeDragId,
      targetZone: overZone,
      panelsByZone,
    });

  return (
    <DndContext
      sensors={sensors}
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragEnd={handleDragEnd}
      onDragCancel={handleDragCancel}
    >
      <div
        className={`${styles.diagram} ${isInvalidHover ? styles.diagramInvalidDrop : ""}`}
        data-testid={ElementIds.SETTINGS_PANELS_DIAGRAM}
      >
        <DiagramSide side="left" filterZone={filterZone} onFilterZone={onFilterZone} activeDragId={activeDragId} />
        <FixedRegion
          label="Files"
          className={styles.fixedFiles}
          testId={`${ElementIds.SETTINGS_PANELS_DIAGRAM}-fixed-files`}
        />
        <FixedRegion
          label="Chat"
          className={styles.fixedChat}
          testId={`${ElementIds.SETTINGS_PANELS_DIAGRAM}-fixed-chat`}
        />
        <DiagramSide side="right" filterZone={filterZone} onFilterZone={onFilterZone} activeDragId={activeDragId} />
        <DiagramZone zoneId="bottom" filterZone={filterZone} onFilterZone={onFilterZone} className={styles.zoneSpan} />
        {filterZone != null && (
          <Button
            variant="soft"
            size="1"
            className={styles.clearFilter}
            data-testid={ElementIds.SETTINGS_PANELS_DIAGRAM_CLEAR_FILTER}
            onClick={() => onFilterZone(null)}
          >
            Clear filter
          </Button>
        )}
      </div>
    </DndContext>
  );
};

type DiagramSideProps = {
  side: "left" | "right";
  filterZone: ZoneId | null;
  onFilterZone: (zone: ZoneId | null) => void;
  activeDragId: PanelId | null;
};

const DiagramSide = ({ side, filterZone, onFilterZone, activeDragId }: DiagramSideProps): ReactElement => {
  const topZoneId: ZoneId = side === "left" ? "top-left" : "top-right";
  const bottomZoneId: ZoneId = side === "left" ? "bottom-left" : "bottom-right";
  const bottomPanels = useAtomValue(panelsInZoneAtom(bottomZoneId));
  const panelsByZone = usePanelsByZone();

  // Bottom is revealed during a drag if the drop would not leave its sibling
  // top empty (handled by isZoneMoveDisabled).
  const canBottomAcceptDraggedPanel =
    activeDragId !== null &&
    !isZoneMoveDisabled({
      panelId: activeDragId,
      targetZone: bottomZoneId,
      panelsByZone,
    });

  const shouldShowBottom = bottomPanels.length > 0 || canBottomAcceptDraggedPanel;

  const sideClass = side === "left" ? styles.sideLeft : styles.sideRight;

  const collapsedLabel = side === "left" ? "Left" : "Right";

  return (
    <div className={`${styles.side} ${sideClass}`}>
      <DiagramZone
        zoneId={topZoneId}
        filterZone={filterZone}
        onFilterZone={onFilterZone}
        className={shouldShowBottom ? "" : styles.zoneFullHeight}
        labelOverride={shouldShowBottom ? undefined : collapsedLabel}
      />
      {shouldShowBottom && <DiagramZone zoneId={bottomZoneId} filterZone={filterZone} onFilterZone={onFilterZone} />}
    </div>
  );
};

type FixedRegionProps = {
  label: string;
  className: string;
  testId: string;
};

const FixedRegion = ({ label, className, testId }: FixedRegionProps): ReactElement => (
  <div className={`${styles.fixed} ${className}`} data-testid={testId} aria-label={`${label} (always visible)`}>
    <Text className={styles.fixedLabel}>{label}</Text>
  </div>
);

type DiagramZoneProps = {
  zoneId: ZoneId;
  filterZone: ZoneId | null;
  onFilterZone: (zone: ZoneId | null) => void;
  className?: string;
  labelOverride?: string;
};

const DiagramZone = ({
  zoneId,
  filterZone,
  onFilterZone,
  className,
  labelOverride,
}: DiagramZoneProps): ReactElement => {
  const panelIds = useAtomValue(panelsInZoneAtom(zoneId));
  const registry = useAtomValue(panelRegistryAtom);
  const { isOver, setNodeRef } = useDroppable({ id: zoneId });

  const isFiltered = filterZone === zoneId;
  const isEmpty = panelIds.length === 0;

  const classes = [
    styles.zone,
    isEmpty ? styles.zoneEmpty : "",
    isFiltered ? styles.zoneFiltered : "",
    isOver ? styles.zoneOver : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  const handleClick = (): void => {
    onFilterZone(isFiltered ? null : zoneId);
  };

  const handleKeyDown = (e: ReactKeyboardEvent): void => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      handleClick();
    }
  };

  return (
    <div
      ref={setNodeRef}
      role="button"
      tabIndex={0}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      className={classes}
      data-testid={`${ElementIds.SETTINGS_PANELS_DIAGRAM_ZONE}-${zoneId}`}
      aria-pressed={isFiltered}
    >
      <Text className={styles.zoneLabel}>{labelOverride ?? ZONE_DISPLAY_NAMES[zoneId]}</Text>
      <Flex gap="2" wrap="wrap">
        {panelIds.map((panelId) => {
          const panel = registry.find((p) => p.id === panelId);
          if (!panel) return null;
          return <DiagramPanelIcon key={panelId} panel={panel} />;
        })}
      </Flex>
    </div>
  );
};

const DiagramPanelIcon = ({ panel }: { panel: PanelDefinition }): ReactElement => {
  const { attributes, listeners, setNodeRef, transform } = useDraggable({ id: panel.id });
  const Icon = panel.icon;

  const style = transform ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` } : undefined;

  return (
    <span
      ref={setNodeRef}
      style={style}
      title={panel.displayName}
      className={styles.icon}
      data-testid={`${ElementIds.SETTINGS_PANELS_DIAGRAM_ICON}-${panel.id}`}
      onClick={(e) => e.stopPropagation()}
      {...listeners}
      {...attributes}
    >
      <Icon size={14} />
    </span>
  );
};
