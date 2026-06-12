import type { DragEndEvent, Modifier } from "@dnd-kit/core";
import { DndContext, PointerSensor, useDraggable, useSensor, useSensors } from "@dnd-kit/core";
import { IconButton } from "@radix-ui/themes";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { PanelBottomClose, PanelBottomOpen, X } from "lucide-react";
import {
  lazy,
  type MouseEvent as ReactMouseEvent,
  type ReactElement,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import { ElementIds } from "~/api";

import { tanstackDevtoolsEnabledAtom, tanstackDevtoolsModeAtom } from "../../common/state/atoms/devPanel.ts";
import styles from "./TanstackDevtoolsMount.module.scss";

// Use the explicit `/production` entry: the package's default entry replaces
// `ReactQueryDevtoolsPanel` with `() => null` whenever
// `process.env.NODE_ENV !== "development"`, which leaves the floating chrome
// empty in any packaged build. We want the in-app devtools to ship.
const ReactQueryDevtoolsPanel = lazy(() =>
  import("@tanstack/react-query-devtools/production").then((mod) => ({ default: mod.ReactQueryDevtoolsPanel })),
);

const DEFAULT_WIDTH = 720;
const DEFAULT_HEIGHT = 440;
const DEFAULT_DOCK_HEIGHT = 320;
const MIN_WIDTH = 360;
const MIN_HEIGHT = 200;
const DEFAULT_INSET = 24;
const DRAGGABLE_ID = "tanstack-devtools-panel";
const DOCK_CSS_VAR = "--tsqd-bottom-dock-height";

type Position = { x: number; y: number };
type Size = { width: number; height: number };
type Edge = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";

const EDGE_CLASSES: Record<Edge, string> = {
  n: styles.edgeN,
  s: styles.edgeS,
  e: styles.edgeE,
  w: styles.edgeW,
  ne: styles.edgeNE,
  nw: styles.edgeNW,
  se: styles.edgeSE,
  sw: styles.edgeSW,
};

const clamp = (value: number, min: number, max: number): number => Math.min(Math.max(value, min), max);

const clampToViewport = (position: Position, size: Size): Position => ({
  x: clamp(position.x, 0, Math.max(0, window.innerWidth - size.width)),
  y: clamp(position.y, 0, Math.max(0, window.innerHeight - size.height)),
});

const clampSize = (size: Size): Size => ({
  width: clamp(size.width, MIN_WIDTH, window.innerWidth),
  height: clamp(size.height, MIN_HEIGHT, window.innerHeight),
});

const getInitialPosition = (size: Size): Position => ({
  x: Math.max(0, window.innerWidth - size.width - DEFAULT_INSET),
  y: Math.max(0, window.innerHeight - size.height - DEFAULT_INSET),
});

/**
 * Clamp the live drag transform using the panel's known position and size
 * instead of dnd-kit's measured rect. The measured rect can drift from the
 * visual position when the element uses both `position: fixed` and a CSS
 * `transform`, which left the panel resistant to dragging out of its
 * initial corner.
 */
const restrictDragToViewport = (panelPosition: Position, panelSize: Size): Modifier => {
  return ({ transform }) => ({
    ...transform,
    x: clamp(transform.x, -panelPosition.x, window.innerWidth - panelSize.width - panelPosition.x),
    y: clamp(transform.y, -panelPosition.y, window.innerHeight - panelSize.height - panelPosition.y),
  });
};

/**
 * Apply a resize delta from a given edge or corner, clamped so the panel
 * stays within the viewport and respects the minimum size. Resizing from
 * the top or left edges also shifts the position so the opposite edge
 * stays anchored.
 */
const computeResize = (
  edge: Edge,
  startPosition: Position,
  startSize: Size,
  dx: number,
  dy: number,
): { position: Position; size: Size } => {
  let { x, y } = startPosition;
  let { width, height } = startSize;

  if (edge.includes("e")) {
    const maxDx = window.innerWidth - startPosition.x - startSize.width;
    const minDx = MIN_WIDTH - startSize.width;
    const clamped = clamp(dx, minDx, maxDx);
    width = startSize.width + clamped;
  }

  if (edge.includes("w")) {
    const maxDx = startSize.width - MIN_WIDTH;
    const minDx = -startPosition.x;
    const clamped = clamp(dx, minDx, maxDx);
    width = startSize.width - clamped;
    x = startPosition.x + clamped;
  }

  if (edge.includes("s")) {
    const maxDy = window.innerHeight - startPosition.y - startSize.height;
    const minDy = MIN_HEIGHT - startSize.height;
    const clamped = clamp(dy, minDy, maxDy);
    height = startSize.height + clamped;
  }

  if (edge.includes("n")) {
    const maxDy = startSize.height - MIN_HEIGHT;
    const minDy = -startPosition.y;
    const clamped = clamp(dy, minDy, maxDy);
    height = startSize.height - clamped;
    y = startPosition.y + clamped;
  }

  return { position: { x, y }, size: { width, height } };
};

export const TanstackDevtoolsMount = (): ReactElement | null => {
  const isEnabled = useAtomValue(tanstackDevtoolsEnabledAtom);
  const [mode, setMode] = useAtom(tanstackDevtoolsModeAtom);

  const [floatingSize, setFloatingSize] = useState<Size>({ width: DEFAULT_WIDTH, height: DEFAULT_HEIGHT });
  const [floatingPosition, setFloatingPosition] = useState<Position>(() =>
    getInitialPosition({ width: DEFAULT_WIDTH, height: DEFAULT_HEIGHT }),
  );
  const [dockHeight, setDockHeight] = useState(DEFAULT_DOCK_HEIGHT);

  // Reclamp position and size whenever the viewport shrinks so the panel
  // never drifts (or stays parked) outside the visible area.
  useEffect(() => {
    const handleResize = (): void => {
      setFloatingSize((prev) => clampSize(prev));
      setFloatingPosition((prev) => clampToViewport(prev, floatingSize));
      setDockHeight((prev) => clamp(prev, MIN_HEIGHT, window.innerHeight));
    };
    window.addEventListener("resize", handleResize);
    return (): void => window.removeEventListener("resize", handleResize);
  }, [floatingSize]);

  // Push the app's #root upward when docked by setting a CSS variable that
  // index.css subtracts from #root's height. Cleaned up when unmounted or
  // when switching back to floating mode.
  useEffect(() => {
    if (!isEnabled || mode !== "docked-bottom") {
      document.documentElement.style.removeProperty(DOCK_CSS_VAR);
      return;
    }
    document.documentElement.style.setProperty(DOCK_CSS_VAR, `${dockHeight}px`);
    return (): void => {
      document.documentElement.style.removeProperty(DOCK_CSS_VAR);
    };
  }, [isEnabled, mode, dockHeight]);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));

  const handleDragEnd = useCallback((event: DragEndEvent): void => {
    setFloatingPosition((prev) => ({
      x: prev.x + event.delta.x,
      y: prev.y + event.delta.y,
    }));
  }, []);

  const dragModifier = useMemo(
    () => restrictDragToViewport(floatingPosition, floatingSize),
    [floatingPosition, floatingSize],
  );

  if (!isEnabled) {
    return null;
  }

  if (mode === "docked-bottom") {
    return <DockedPanel height={dockHeight} onHeightChange={setDockHeight} onModeChange={setMode} />;
  }

  return (
    <DndContext sensors={sensors} modifiers={[dragModifier]} onDragEnd={handleDragEnd}>
      <FloatingPanel
        position={floatingPosition}
        size={floatingSize}
        onPositionChange={setFloatingPosition}
        onSizeChange={setFloatingSize}
        onModeChange={setMode}
      />
    </DndContext>
  );
};

type FloatingPanelProps = {
  position: Position;
  size: Size;
  onPositionChange: (position: Position) => void;
  onSizeChange: (size: Size) => void;
  onModeChange: (mode: "floating" | "docked-bottom") => void;
};

const FloatingPanel = ({
  position,
  size,
  onPositionChange,
  onSizeChange,
  onModeChange,
}: FloatingPanelProps): ReactElement => {
  const setIsEnabled = useSetAtom(tanstackDevtoolsEnabledAtom);
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: DRAGGABLE_ID });

  const handleClose = useCallback((): void => {
    setIsEnabled(false);
  }, [setIsEnabled]);

  const handleResizeStart = useCallback(
    (edge: Edge) =>
      (event: ReactMouseEvent<HTMLDivElement>): void => {
        if (event.button !== 0) return;
        event.preventDefault();
        event.stopPropagation();

        const startX = event.clientX;
        const startY = event.clientY;
        const startPosition = position;
        const startSize = size;

        const handleMove = (e: MouseEvent): void => {
          const next = computeResize(edge, startPosition, startSize, e.clientX - startX, e.clientY - startY);
          onPositionChange(next.position);
          onSizeChange(next.size);
        };

        const handleUp = (): void => {
          document.removeEventListener("mousemove", handleMove);
          document.removeEventListener("mouseup", handleUp);
        };

        document.addEventListener("mousemove", handleMove);
        document.addEventListener("mouseup", handleUp);
      },
    [position, size, onPositionChange, onSizeChange],
  );

  const liveX = position.x + (transform?.x ?? 0);
  const liveY = position.y + (transform?.y ?? 0);

  return (
    <div
      ref={setNodeRef}
      className={`${styles.container} ${styles.floating} ${isDragging ? styles.dragging : ""}`}
      style={{
        transform: `translate3d(${liveX}px, ${liveY}px, 0)`,
        width: size.width,
        height: size.height,
      }}
    >
      <PanelHeader
        mode="floating"
        onModeChange={onModeChange}
        onClose={handleClose}
        dragListeners={listeners}
        dragAttributes={attributes}
      />
      <div className={styles.panel} data-testid={ElementIds.TANSTACK_DEVTOOLS_PANEL_HOST}>
        <Suspense fallback={null}>
          <ReactQueryDevtoolsPanel style={{ height: "100%" }} onClose={handleClose} />
        </Suspense>
      </div>
      {(Object.keys(EDGE_CLASSES) as Array<Edge>).map((edge) => (
        <div
          key={edge}
          className={`${styles.resizeHandle} ${EDGE_CLASSES[edge]}`}
          onMouseDown={handleResizeStart(edge)}
          aria-label={`Resize TanStack devtools panel from ${edge}`}
          role="separator"
        />
      ))}
    </div>
  );
};

type DockedPanelProps = {
  height: number;
  onHeightChange: (height: number) => void;
  onModeChange: (mode: "floating" | "docked-bottom") => void;
};

const DockedPanel = ({ height, onHeightChange, onModeChange }: DockedPanelProps): ReactElement => {
  const setIsEnabled = useSetAtom(tanstackDevtoolsEnabledAtom);

  const handleClose = useCallback((): void => {
    setIsEnabled(false);
  }, [setIsEnabled]);

  const handleResizeStart = useCallback(
    (event: ReactMouseEvent<HTMLDivElement>): void => {
      if (event.button !== 0) return;
      event.preventDefault();

      const startY = event.clientY;
      const startHeight = height;

      const handleMove = (e: MouseEvent): void => {
        // Dragging the top edge up grows the dock; down shrinks it. Clamp
        // to MIN_HEIGHT and the current viewport height.
        const delta = startY - e.clientY;
        onHeightChange(clamp(startHeight + delta, MIN_HEIGHT, window.innerHeight));
      };

      const handleUp = (): void => {
        document.removeEventListener("mousemove", handleMove);
        document.removeEventListener("mouseup", handleUp);
      };

      document.addEventListener("mousemove", handleMove);
      document.addEventListener("mouseup", handleUp);
    },
    [height, onHeightChange],
  );

  return (
    <div className={`${styles.container} ${styles.docked}`} style={{ height }}>
      <div
        className={`${styles.resizeHandle} ${styles.edgeN} ${styles.dockResize}`}
        onMouseDown={handleResizeStart}
        aria-label="Resize TanStack devtools dock height"
        role="separator"
      />
      <PanelHeader mode="docked-bottom" onModeChange={onModeChange} onClose={handleClose} />
      <div className={styles.panel} data-testid={ElementIds.TANSTACK_DEVTOOLS_PANEL_HOST}>
        <Suspense fallback={null}>
          <ReactQueryDevtoolsPanel style={{ height: "100%" }} onClose={handleClose} />
        </Suspense>
      </div>
    </div>
  );
};

type PanelHeaderProps = {
  mode: "floating" | "docked-bottom";
  onModeChange: (mode: "floating" | "docked-bottom") => void;
  onClose: () => void;
  dragListeners?: ReturnType<typeof useDraggable>["listeners"];
  dragAttributes?: ReturnType<typeof useDraggable>["attributes"];
};

const PanelHeader = ({
  mode,
  onModeChange,
  onClose,
  dragListeners,
  dragAttributes,
}: PanelHeaderProps): ReactElement => {
  // Icon shows the current state: an open bottom panel when docked, a closed
  // one when floating. Click flips that state.
  const ToggleIcon = mode === "docked-bottom" ? PanelBottomOpen : PanelBottomClose;
  const nextMode = mode === "floating" ? "docked-bottom" : "floating";
  const toggleLabel = mode === "floating" ? "Dock to bottom" : "Float";

  return (
    <div className={styles.header} {...dragListeners} {...dragAttributes}>
      <span className={styles.headerTitle}>TanStack Query Devtools</span>
      <IconButton
        size="1"
        variant="ghost"
        color="gray"
        aria-label={toggleLabel}
        title={toggleLabel}
        // Don't let mousedown on the toggle initiate a drag.
        onMouseDown={(event) => event.stopPropagation()}
        onClick={() => onModeChange(nextMode)}
      >
        <ToggleIcon size={14} />
      </IconButton>
      <IconButton
        size="1"
        variant="ghost"
        color="gray"
        aria-label="Close TanStack devtools"
        title="Close"
        onMouseDown={(event) => event.stopPropagation()}
        onClick={onClose}
      >
        <X size={14} />
      </IconButton>
    </div>
  );
};
