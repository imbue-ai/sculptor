import { RequestTimeoutError } from "~/common/Errors.ts";

import type { RequestID } from "../Types.ts";
import {
  isSingletonWebsocketActiveAtom,
  type RequestAcknowledgment,
  requestAcknowledgmentsAtom,
} from "./atoms/requests.ts";
import { requestStore } from "./requestStore.ts";

const DEFAULT_REQUEST_TIMEOUT_MS = 10000;

type TrackedRequest = {
  /** Promise that resolves when all required WebSocket sources acknowledge the request */
  wait: Promise<void>;
  /** Function to cancel the tracker and clean up resources */
  cancel: () => void;
};

type TrackerState = {
  unsubscribeFromStore: (() => void) | null;
  timeoutHandle: number | null;
  isCancelled: boolean;
  isFinalized: boolean;
  resolvePromise: () => void;
  rejectPromise: (error: Error) => void;
};

/**
 * Creates a request tracker that waits for WebSocket acknowledgment
 *
 * This function creates a tracker that:
 * 1. Confirms the unified stream is active for acknowledgments
 * 2. Sets up a timeout that rejects if acknowledgment takes too long
 * 3. Watches acknowledgment updates from the stream
 * 4. Resolves when the stream confirms completion
 * 5. Provides a cancel function for early cleanup
 */
export const createRequestTracker = (
  requestId: RequestID,
  url: string,
  _method: string = "GET",
  customTimeoutMs?: number,
): TrackedRequest => {
  const state: TrackerState = {
    unsubscribeFromStore: null,
    timeoutHandle: null,
    isCancelled: false,
    isFinalized: false,
    resolvePromise: () => {},
    rejectPromise: () => {},
  };

  const waitPromise = new Promise<void>((resolve, reject) => {
    state.resolvePromise = resolve;
    state.rejectPromise = reject;
  });

  const finalizeTracker = (shouldResolve: boolean, error?: Error): void => {
    cleanupTracker(state, requestId);

    if (shouldResolve) {
      state.resolvePromise();
    } else if (error) {
      state.rejectPromise(error);
    }
  };

  const cancel = (): void => {
    state.isCancelled = true;
    // Resolve (don't reject) on cancel to avoid breaking calling code
    finalizeTracker(true);
  };

  const doesRequireAcknowledgement = shouldWaitForAcknowledgment();

  if (!doesRequireAcknowledgement) {
    finalizeTracker(true);
    return { wait: waitPromise, cancel };
  }

  const timeoutDuration = customTimeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS;
  state.timeoutHandle = window.setTimeout(() => {
    const errorMessage = `Request ${requestId}, url: ${url} timed out after ${timeoutDuration}ms`;
    finalizeTracker(false, new RequestTimeoutError(errorMessage));
  }, timeoutDuration);

  const acknowledgment = createAcknowledgmentEntry(
    requestId,
    doesRequireAcknowledgement,
    state.resolvePromise,
    state.rejectPromise,
  );
  registerAcknowledgment(acknowledgment);

  state.unsubscribeFromStore = requestStore.sub(requestAcknowledgmentsAtom, () => {
    const currentAcknowledgments = requestStore.get(requestAcknowledgmentsAtom);
    const currentAck = currentAcknowledgments.get(requestId);

    if (!currentAck) {
      if (state.isCancelled) {
        finalizeTracker(true);
      } else {
        // Unexpected removal is an error
        finalizeTracker(false, new Error("Request acknowledgment disappeared unexpectedly"));
      }
      return;
    }

    if (currentAck.isAcknowledged) {
      finalizeTracker(true);
    }
  });

  return { wait: waitPromise, cancel };
};

/**
 * Called by the unified stream handler when it receives finished_request_ids
 * Updates the acknowledgment status for the specified requests
 */
export const acknowledgeRequests = (requestIds: Array<RequestID>): void => {
  const currentAcknowledgments = requestStore.get(requestAcknowledgmentsAtom);
  const updatedAcknowledgments = new Map(currentAcknowledgments);
  let hasChanges = false;

  for (const requestId of requestIds) {
    const acknowledgment = updatedAcknowledgments.get(requestId);

    if (acknowledgment && !acknowledgment.isAcknowledged) {
      updatedAcknowledgments.set(requestId, {
        ...acknowledgment,
        isAcknowledged: true,
      });
      hasChanges = true;
    }
  }

  if (hasChanges) {
    requestStore.set(requestAcknowledgmentsAtom, updatedAcknowledgments);
  }
};

/**
 * Updates whether the unified stream is active
 * Called by the stream hook when the connection opens or closes
 */
export const updateActiveWebsockets = (isActive: boolean): void => {
  requestStore.set(isSingletonWebsocketActiveAtom, isActive);
};

const cleanupRequest = (requestId: RequestID): void => {
  const currentAcknowledgments = requestStore.get(requestAcknowledgmentsAtom);
  const updatedAcknowledgments = new Map(currentAcknowledgments);
  updatedAcknowledgments.delete(requestId);
  requestStore.set(requestAcknowledgmentsAtom, updatedAcknowledgments);
};

const createAcknowledgmentEntry = (
  requestId: RequestID,
  requiresAcknowledgment: boolean,
  resolvePromise: () => void,
  rejectPromise: (error: Error) => void,
): RequestAcknowledgment => {
  return {
    requestId,
    isAcknowledged: !requiresAcknowledgment,
    resolver: resolvePromise,
    rejecter: rejectPromise,
    timestamp: Date.now(),
  };
};

const registerAcknowledgment = (acknowledgment: RequestAcknowledgment): void => {
  const currentAcknowledgments = requestStore.get(requestAcknowledgmentsAtom);
  const updatedAcknowledgments = new Map(currentAcknowledgments);
  updatedAcknowledgments.set(acknowledgment.requestId, acknowledgment);
  requestStore.set(requestAcknowledgmentsAtom, updatedAcknowledgments);
};

const cleanupTracker = (state: TrackerState, requestId: RequestID): void => {
  if (state.isFinalized) {
    return;
  }

  state.isFinalized = true;

  if (state.unsubscribeFromStore) {
    state.unsubscribeFromStore();
    state.unsubscribeFromStore = null;
  }

  if (state.timeoutHandle !== null) {
    clearTimeout(state.timeoutHandle);
    state.timeoutHandle = null;
  }

  cleanupRequest(requestId);
};

const shouldWaitForAcknowledgment = (): boolean => {
  return requestStore.get(isSingletonWebsocketActiveAtom);
};
