import { createStore } from "jotai";

import { isSingletonWebsocketActiveAtom, requestAcknowledgmentsAtom } from "./atoms/requests.ts";

export const requestStore = createStore();

requestStore.set(requestAcknowledgmentsAtom, new Map());
requestStore.set(isSingletonWebsocketActiveAtom, false);
