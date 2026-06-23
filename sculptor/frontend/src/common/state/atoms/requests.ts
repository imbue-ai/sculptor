import { atom } from "jotai";

import type { RequestID } from "../../Types.ts";

export type RequestAcknowledgment = {
  requestId: RequestID;
  isAcknowledged: boolean;
};

export const requestAcknowledgmentsAtom = atom<Map<RequestID, RequestAcknowledgment>>(
  new Map<RequestID, RequestAcknowledgment>(),
);

export const isSingletonWebsocketActiveAtom = atom<boolean>(false);
