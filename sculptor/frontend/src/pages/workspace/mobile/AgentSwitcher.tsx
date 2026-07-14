import { useAtomValue } from "jotai";
import { ChevronDown } from "lucide-react";
import type { PointerEvent as ReactPointerEvent, ReactElement } from "react";
import { useCallback, useMemo, useRef } from "react";

import { ElementIds } from "~/api";
import { useImbueNavigate, useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";

import styles from "./AgentSwitcher.module.scss";

type AgentSwitcherProps = {
  onOpenSheet: () => void;
};

const SWIPE_THRESHOLD = 36; // px of horizontal drag before it counts as a swipe
const DRAG_CAP = 40; // px the name is allowed to follow the finger

/**
 * AgentSwitcher (Variant D) — replaces the old dot pager. A minimal pill showing
 * the active agent's name + a caret, sharing the status row under the header with
 * the changes pill (the switcher sits on the left). It adopts the same indicator
 * chrome as the changes pill / StatusPill. The name truncates when long. Swipe
 * the pill left/right to move to the next/previous agent in the workspace; tap it
 * to open the AgentSheet (full list + New agent). Per-agent status and
 * last-activity live in the sheet, so the pill itself stays minimal.
 */
export const AgentSwitcher = ({ onOpenSheet }: AgentSwitcherProps): ReactElement | null => {
  const { workspaceID, agentID } = useWorkspacePageParams();
  const { navigateToAgent } = useImbueNavigate();
  const tasks = useAtomValue(tasksArrayAtom);

  const nameRef = useRef<HTMLSpanElement>(null);
  const startXRef = useRef<number | null>(null);
  const swipedRef = useRef(false);

  const agents = useMemo(
    () =>
      (tasks ?? [])
        .filter((t) => t.workspaceId === workspaceID && !t.isDeleted)
        .sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime()),
    [tasks, workspaceID],
  );

  const index = agents.findIndex((a) => a.id === agentID);
  const active = index >= 0 ? agents[index] : agents[0];

  const goTo = useCallback(
    (i: number): void => {
      const target = agents[i];
      if (target && target.id !== agentID) navigateToAgent(workspaceID, target.id);
    },
    [agents, agentID, workspaceID, navigateToAgent],
  );

  const onPointerDown = (e: ReactPointerEvent<HTMLButtonElement>): void => {
    startXRef.current = e.clientX;
    swipedRef.current = false;
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      // setPointerCapture can throw if the pointer is already gone; harmless.
    }
  };

  const onPointerMove = (e: ReactPointerEvent<HTMLButtonElement>): void => {
    if (startXRef.current === null) return;
    const dx = Math.max(-DRAG_CAP, Math.min(DRAG_CAP, e.clientX - startXRef.current));
    if (nameRef.current) nameRef.current.style.transform = `translateX(${dx}px)`;
  };

  const endDrag = (clientX: number | null): void => {
    if (startXRef.current === null) return;
    const dx = clientX === null ? 0 : clientX - startXRef.current;
    startXRef.current = null;
    if (nameRef.current) nameRef.current.style.transform = "";
    if (dx <= -SWIPE_THRESHOLD) {
      swipedRef.current = true;
      goTo(index + 1);
    } else if (dx >= SWIPE_THRESHOLD) {
      swipedRef.current = true;
      goTo(index - 1);
    }
  };

  // Tap opens the sheet; a tap that followed a swipe is suppressed. Using click
  // (not pointerup) keeps keyboard activation working.
  const onClick = (): void => {
    if (swipedRef.current) {
      swipedRef.current = false;
      return;
    }
    onOpenSheet();
  };

  if (!active) return null;
  const name = active.titleOrSomethingLikeIt?.trim() || "Agent";

  return (
    <div className={styles.switcher}>
      <button
        type="button"
        className={styles.pill}
        aria-haspopup="dialog"
        aria-label={`Current agent: ${name}. Tap to switch agents.`}
        data-testid={ElementIds.MOBILE_AGENT_SWITCHER_PILL}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={(e) => endDrag(e.clientX)}
        onPointerCancel={() => endDrag(null)}
        onClick={onClick}
      >
        <span ref={nameRef} className={styles.name}>
          {name}
        </span>
        <ChevronDown size={14} className={styles.caret} />
      </button>
    </div>
  );
};
