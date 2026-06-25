import { atom } from "jotai";

export type BtwPopupPosition = { x: number; y: number };

export type BtwPopupState =
  | { kind: "closed" }
  | {
      kind: "open";
      // Identifies the agent this popup was forked from. The chat-panel
      // wrapper closes the popup whenever the active agent no longer matches
      // this id, so a popup never bleeds across agent/workspace switches.
      agentId: string;
      question: string;
      answer: string;
      streaming: boolean;
      error?: string;
      requestId: string;
      position?: BtwPopupPosition;
    };

export const btwPopupAtom = atom<BtwPopupState>({ kind: "closed" });

// Derived selector so consumers can subscribe to open/closed transitions
// without re-rendering on every streamed answer-text update.
export const isBtwPopupOpenAtom = atom((get) => get(btwPopupAtom).kind === "open");

export const openBtwPopupAtom = atom(
  null,
  (get, set, payload: { agentId: string; question: string; requestId: string }): void => {
    // Preserve the dragged position when replacing the popup in place.
    const current = get(btwPopupAtom);
    const position = current.kind === "open" ? current.position : undefined;
    set(btwPopupAtom, {
      kind: "open",
      agentId: payload.agentId,
      question: payload.question,
      answer: "",
      streaming: true,
      requestId: payload.requestId,
      position,
    });
  },
);

// Closes the popup if its `agentId` doesn't match the supplied current agent.
// No-op when the popup is closed or already belongs to the active agent.
export const closeBtwPopupIfNotForAgentAtom = atom(null, (get, set, currentAgentId: string | null): void => {
  const current = get(btwPopupAtom);
  if (current.kind !== "open") {
    return;
  }

  if (currentAgentId !== null && current.agentId === currentAgentId) {
    return;
  }
  set(btwPopupAtom, { kind: "closed" });
});

export type BtwUpdatePayload = {
  requestId: string;
  state: "running" | "done" | "error" | "aborted";
  answer: string;
  errorMessage?: string | null;
};

export const handleBtwUpdateAtom = atom(null, (get, set, payload: BtwUpdatePayload): void => {
  const current = get(btwPopupAtom);
  // Ignore stale events from a replaced subprocess or events received after close.
  if (current.kind !== "open" || current.requestId !== payload.requestId) {
    return;
  }
  const isTerminal = payload.state !== "running";
  set(btwPopupAtom, {
    ...current,
    answer: payload.answer,
    streaming: !isTerminal,
    error: payload.state === "error" ? (payload.errorMessage ?? "Unknown error") : undefined,
  });
});

export const closeBtwPopupAtom = atom(null, (_get, set): void => {
  set(btwPopupAtom, { kind: "closed" });
});

export const setBtwPopupPositionAtom = atom(null, (get, set, position: BtwPopupPosition): void => {
  const current = get(btwPopupAtom);
  if (current.kind !== "open") {
    return;
  }
  set(btwPopupAtom, { ...current, position });
});
