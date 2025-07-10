# Request ID Tracking Implementation Plan

## Overview
This plan outlines the implementation of a request ID tracking system to solve frontend state consistency issues. The system ensures that API request promises only resolve after the server has completed processing and all relevant event sources have acknowledged the request completion.

## Problem Statement
- API requests resolve immediately after HTTP response, but server-side processing continues
- State updates arrive through event sources after the API promise has already resolved
- This causes UI inconsistencies where the frontend shows incomplete or stale data

## Solution Architecture

### Core Concept
1. Every API request generates a unique request ID
2. The request ID is tracked in a Jotai atom
3. API requests return promises that wait for event source acknowledgment
4. Event sources update the tracking atom when they receive finished request IDs
5. Promises resolve only when all active event sources have acknowledged the request

### Event Source Architecture
Three event sources provide finished request IDs:
1. **Tasks Event Source** (`/api/v1/projects/{projectId}/tasks/stream`)
   - Returns `TaskListUpdate` with `finishedRequestIds: Array<RequestID>`
   - Active on all pages
2. **Task Event Source** (`/api/v1/projects/{projectId}/tasks/{taskId}/stream`)
   - Returns `TaskUpdate` with `finished_request_ids: Array<RequestID>`
   - Active only on chat pages
3. **Notifications Event Source** (`/api/v1/projects/{projectId}/notifications/stream`)
   - Returns `UserUpdate` with `finishedRequestIds: Array<RequestID>`
   - Active on all pages

## Implementation Details

### 1. Jotai State Structure

```typescript
// common/state/atoms/requests.ts

import { atom } from "jotai";
import type { RequestID } from "../../../Types";

// Existing atom for tracking pending requests
export const pendingRequestsAtom = atom<Set<RequestID>>(new Set<RequestID>());

// New atom for tracking request acknowledgments
export type RequestAcknowledgment = {
  requestId: RequestID;
  sources: {
    tasksList: boolean;      // From tasks event source
    taskDetail: boolean;     // From task event source (chat page only)
    notifications: boolean;  // From notifications event source
  };
  resolver?: (value: any) => void;
  rejecter?: (reason: any) => void;
  timeout?: NodeJS.Timeout;
  timestamp: number;
};

export const requestAcknowledgmentsAtom = atom<Map<RequestID, RequestAcknowledgment>>(
  new Map<RequestID, RequestAcknowledgment>()
);

// Atom to track which event sources are currently active
export type ActiveEventSources = {
  tasksList: boolean;
  taskDetail: boolean;
  notifications: boolean;
};

export const activeEventSourcesAtom = atom<ActiveEventSources>({
  tasksList: false,
  taskDetail: false,
  notifications: false,
});
```

### 2. Custom Jotai Store

```typescript
// common/state/requestStore.ts

import { createStore } from "jotai";
import { 
  pendingRequestsAtom, 
  requestAcknowledgmentsAtom,
  activeEventSourcesAtom 
} from "./atoms/requests";

// Create a custom store for request tracking
export const requestStore = createStore();

// Initialize atoms in the store
requestStore.set(pendingRequestsAtom, new Set());
requestStore.set(requestAcknowledgmentsAtom, new Map());
requestStore.set(activeEventSourcesAtom, {
  tasksList: false,
  taskDetail: false,
  notifications: false,
});
```

### 3. Event-Driven Request Tracking with Jotai Subscriptions

The key to making this system event-driven is using Jotai's store subscription mechanism. When event sources update the atom with acknowledgments, it automatically triggers resolution of the waiting promises.

#### How Jotai Store Subscriptions Work

Jotai's `createStore()` provides three core methods that enable event-driven behavior outside of React:

1. **`store.get(atom)`**: Read the current value of an atom
2. **`store.set(atom, newValue)`**: Update an atom's value (triggers subscriptions)
3. **`store.sub(atom, callback)`**: Subscribe to atom changes

The subscription mechanism works as follows:
```typescript
// Create a store instance
const store = createStore();

// Subscribe to an atom
const unsubscribe = store.sub(myAtom, () => {
  // This callback runs whenever store.set(myAtom, newValue) is called
  const currentValue = store.get(myAtom);
  console.log('Atom changed:', currentValue);
});

// Later: trigger the subscription
store.set(myAtom, newValue); // This triggers all active subscriptions

// Clean up when done
unsubscribe();
```

This creates a pure event-driven system where:
- Event sources call `store.set()` to update atoms
- Active subscriptions are immediately notified
- No polling or manual checking required
- Works completely outside React components

#### 3.1 Subscription-Based Request Tracker

```typescript
// common/state/utils/requestTracking.ts

import { requestStore } from "../requestStore";
import { 
  pendingRequestsAtom, 
  requestAcknowledgmentsAtom,
  activeEventSourcesAtom,
  type RequestAcknowledgment 
} from "../atoms/requests";
import type { RequestID } from "../../../Types";

const REQUEST_TIMEOUT_MS = 10000; // 10 seconds

export function createRequestTracker(requestId: RequestID): Promise<void> {
  return new Promise((resolve, reject) => {
    let unsubscribe: (() => void) | null = null;
    let timeout: NodeJS.Timeout | null = null;
    
    // Helper to clean up and resolve/reject
    const cleanup = (shouldResolve: boolean, error?: Error) => {
      if (unsubscribe) {
        unsubscribe();
        unsubscribe = null;
      }
      if (timeout) {
        clearTimeout(timeout);
        timeout = null;
      }
      cleanupRequest(requestId);
      
      if (shouldResolve) {
        resolve();
      } else if (error) {
        reject(error);
      }
    };
    
    // Set up timeout
    timeout = setTimeout(() => {
      cleanup(false, new Error(`Request ${requestId} timed out after ${REQUEST_TIMEOUT_MS}ms`));
    }, REQUEST_TIMEOUT_MS);
    
    // Get current active sources to determine what we're waiting for
    const activeSources = requestStore.get(activeEventSourcesAtom);
    const requiredSources = {
      tasksList: activeSources.tasksList,
      taskDetail: activeSources.taskDetail,
      notifications: activeSources.notifications,
    };
    
    // Create initial acknowledgment entry
    const acknowledgment: RequestAcknowledgment = {
      requestId,
      sources: {
        tasksList: !requiredSources.tasksList,      // Pre-mark as true if not required
        taskDetail: !requiredSources.taskDetail,
        notifications: !requiredSources.notifications,
      },
      resolver: resolve,
      rejecter: reject,
      timestamp: Date.now(),
    };
    
    // Add to tracking atoms
    const acknowledgments = requestStore.get(requestAcknowledgmentsAtom);
    const newAcknowledgments = new Map(acknowledgments);
    newAcknowledgments.set(requestId, acknowledgment);
    requestStore.set(requestAcknowledgmentsAtom, newAcknowledgments);
    
    const pending = requestStore.get(pendingRequestsAtom);
    const newPending = new Set(pending);
    newPending.add(requestId);
    requestStore.set(pendingRequestsAtom, newPending);
    
    // CRITICAL: Subscribe to acknowledgment atom changes
    // This subscription callback fires whenever ANY request's acknowledgment changes
    // We must filter for our specific requestId inside the callback
    unsubscribe = requestStore.sub(requestAcknowledgmentsAtom, () => {
      // Note: This callback runs for ALL updates to the acknowledgments atom
      // It's triggered by any store.set(requestAcknowledgmentsAtom, newValue) call
      
      const currentAcks = requestStore.get(requestAcknowledgmentsAtom);
      const currentAck = currentAcks.get(requestId); // Check our specific request
      
      if (!currentAck) {
        // Request was cleaned up elsewhere (shouldn't happen)
        cleanup(false, new Error('Request acknowledgment disappeared'));
        return;
      }
      
      // Check if all required sources have acknowledged THIS request
      const allAcknowledged = 
        currentAck.sources.tasksList && 
        currentAck.sources.taskDetail && 
        currentAck.sources.notifications;
      
      if (allAcknowledged) {
        // All required sources have acknowledged - resolve the promise!
        cleanup(true);
      }
      // If not all acknowledged yet, this callback does nothing
      // It will be called again on the next atom update
    });
  });
}

export function acknowledgeRequestFromSource(
  requestIds: Array<RequestID>, 
  source: 'tasksList' | 'taskDetail' | 'notifications'
): void {
  const acknowledgments = requestStore.get(requestAcknowledgmentsAtom);
  const newAcknowledgments = new Map(acknowledgments);
  let hasChanges = false;
  
  requestIds.forEach(requestId => {
    const ack = newAcknowledgments.get(requestId);
    if (!ack) return;
    
    // Mark this source as acknowledged
    if (!ack.sources[source]) {
      ack.sources[source] = true;
      hasChanges = true;
    }
  });
  
  // CRITICAL: Only update the atom if we actually made changes
  // This triggers subscriptions and causes promise resolution
  if (hasChanges) {
    requestStore.set(requestAcknowledgmentsAtom, newAcknowledgments);
  }
}

function cleanupRequest(requestId: RequestID): void {
  // Remove from acknowledgments
  const acknowledgments = requestStore.get(requestAcknowledgmentsAtom);
  const newAcknowledgments = new Map(acknowledgments);
  newAcknowledgments.delete(requestId);
  requestStore.set(requestAcknowledgmentsAtom, newAcknowledgments);
  
  // Remove from pending
  const pending = requestStore.get(pendingRequestsAtom);
  const newPending = new Set(pending);
  newPending.delete(requestId);
  requestStore.set(pendingRequestsAtom, newPending);
}

export function updateActiveEventSource(source: keyof ActiveEventSources, active: boolean): void {
  const activeSources = requestStore.get(activeEventSourcesAtom);
  requestStore.set(activeEventSourcesAtom, {
    ...activeSources,
    [source]: active,
  });
}
```

#### 3.2 Event-Driven Flow Explanation

Here's how the subscription-based event flow works:

1. **API Request Initiated**:
   - `makeAPIRequest` generates a request ID
   - Calls `createRequestTracker(requestId)` which:
     - Creates a Promise
     - Sets up a Jotai subscription using `requestStore.sub(requestAcknowledgmentsAtom, callback)`
     - The subscription callback is called whenever the atom value changes
     - Stores the promise resolver in the acknowledgment entry

2. **Event Source Updates**:
   - Task event source receives `finished_request_ids: ["rqst_abc123", ...]`
   - Calls `acknowledgeRequestFromSource(requestIds, 'taskDetail')`
   - This updates the `requestAcknowledgmentsAtom` with `sources.taskDetail = true`

3. **Subscription Triggered**:
   - The atom update triggers all active subscriptions
   - The subscription callback for "rqst_abc123" checks if all required sources have acknowledged
   - If not all sources have acknowledged yet, it does nothing and waits

4. **Final Acknowledgment**:
   - When the last required event source acknowledges the request
   - The subscription callback detects all sources are complete
   - Calls the stored promise resolver
   - Cleans up the subscription and tracking data

5. **Promise Resolution**:
   - The `await trackingPromise` in `makeAPIRequest` finally resolves
   - The API response is returned to the caller

This event-driven approach ensures:
- No polling or busy waiting
- Efficient reactive updates
- Automatic cleanup via unsubscribe
- Memory-efficient tracking

#### 3.3 Concrete Example of Event Flow

Here's a step-by-step example of how a request flows through the system:

```typescript
// 1. User calls createTask() which internally calls makeAPIRequest
const task = await createTask(projectId, { description: "Build feature X" });

// 2. Inside makeAPIRequest:
const requestID = makeRequestId(); // "rqst_abc123"
const trackingPromise = createRequestTracker(requestID);

// 3. createRequestTracker sets up subscription:
// - Adds entry to requestAcknowledgmentsAtom with all sources false
// - Creates: store.sub(requestAcknowledgmentsAtom, callback)
// - Promise is now waiting...

// 4. HTTP request completes, but trackingPromise still waiting

// 5. Tasks event source receives update:
// { finishedRequestIds: ["rqst_abc123", "rqst_xyz789"] }
acknowledgeRequestFromSource(["rqst_abc123", "rqst_xyz789"], 'tasksList');
// This calls: store.set(requestAcknowledgmentsAtom, updatedMap)
// TRIGGERS all subscriptions! Each checks their specific request

// 6. Subscription callback for "rqst_abc123" runs:
// - Checks: tasksList=true, taskDetail=false, notifications=false
// - Not all complete, so waits...

// 7. Task detail event source receives update:
acknowledgeRequestFromSource(["rqst_abc123"], 'taskDetail');
// TRIGGERS subscriptions again!

// 8. Subscription callback runs again:
// - Checks: tasksList=true, taskDetail=true, notifications=false
// - Still waiting...

// 9. Notifications event source receives update:
acknowledgeRequestFromSource(["rqst_abc123"], 'notifications');
// TRIGGERS subscriptions!

// 10. Subscription callback runs final time:
// - Checks: tasksList=true, taskDetail=true, notifications=true
// - All complete! Calls resolve()
// - Cleans up subscription

// 11. trackingPromise resolves, makeAPIRequest returns the task data
```

### 4. Updated makeAPIRequest Function

```typescript
// Endpoints.ts

import { makeRequestId } from "./common/Utils";
import { authErrorDialogAtom, authStore, getAccessToken } from "./common/Auth";
import { createRequestTracker } from "./common/state/utils/requestTracking";
import type { TelemetryInfo, UserInfo, ProjectInfo } from "./generated-schema.d.ts";

export const makeAPIRequest = async <TRequest, TResponse>(
  url: string,
  method: string,
  requestData?: TRequest,
): Promise<TResponse> => {
  const requestID = makeRequestId();
  
  // Create the tracking promise BEFORE making the request
  const trackingPromise = createRequestTracker(requestID);
  
  const body = requestData ? requestData : {};
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Request-ID": requestID,
  };
  const token: string | null = getAccessToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  
  try {
    const response = await fetch(url, {
      method,
      headers: headers,
      body: method.toUpperCase() !== "GET" ? JSON.stringify({ ...body }) : undefined,
    });

    if (response.status === 401 || response.status === 403) {
      authStore.set(authErrorDialogAtom, true);
    }

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    
    // Wait for event source acknowledgment
    await trackingPromise;
    
    return data as TResponse;
  } catch (error) {
    // If the HTTP request fails, we should cancel the tracking
    // The tracking promise will handle its own timeout/cleanup
    throw error;
  }
};
```

### 5. Event Source Updates

#### 5.1 Tasks Event Source Hook Update

```typescript
// common/state/hooks/useTasksEventSource.ts

import { useSetAtom } from "jotai";
import { useEffect } from "react";
import { useEventSource, type EventSourceHookReturn } from "./useEventSource";
import { updateTasksAtom } from "../atoms/tasks";
import type { TaskListUpdate } from "../../../Types";
import { useImbueParams } from "../../NavigateUtils";
import { acknowledgeRequestFromSource, updateActiveEventSource } from "../utils/requestTracking";

const API_BASE_URL = "/api/v1";

export const useTasksEventSource = (): EventSourceHookReturn => {
  const { projectID } = useImbueParams();
  const updateTasks = useSetAtom(updateTasksAtom);

  if (!projectID) {
    throw new Error("Expected projectID to be defined");
  }

  // Update active source status
  useEffect(() => {
    updateActiveEventSource('tasksList', true);
    return () => {
      updateActiveEventSource('tasksList', false);
    };
  }, []);

  const tasksEventSource = useEventSource({
    url: `${API_BASE_URL}/projects/${projectID}/tasks/stream`,
    onMessage: (data: TaskListUpdate) => {
      // Handle task updates
      if (data.taskByTaskId && Object.keys(data.taskByTaskId).length > 0) {
        updateTasks(data.taskByTaskId);
      }
      
      // Handle finished request IDs
      if (data.finishedRequestIds && data.finishedRequestIds.length > 0) {
        acknowledgeRequestFromSource(data.finishedRequestIds, 'tasksList');
      }
    },
  });

  return tasksEventSource;
};
```

#### 5.2 Task Event Source Hook Update

```typescript
// pages/chat/hooks/useTaskEventSource.ts

import { useState, useRef, useCallback, useEffect } from "react";
import { processArtifactData, processMessages } from "../utils/messageProcessing";
import type { Message, ArtifactMap, ArtifactType, ChatMessage, TaskID, TaskUpdate } from "../../../Types";
import { getTaskArtifact } from "../../../Endpoints";
import { useEventSource } from "../../../common/state/hooks/useEventSource";
import { acknowledgeRequestFromSource, updateActiveEventSource } from "../../../common/state/utils/requestTracking";

// ... existing code ...

export function useTaskEventSource({ projectId, taskId }: UseTaskEventSourceOptions): UseTaskEventSourceReturn {
  // ... existing state ...
  
  // Update active source status
  useEffect(() => {
    if (taskId && projectId) {
      updateActiveEventSource('taskDetail', true);
      return () => {
        updateActiveEventSource('taskDetail', false);
      };
    }
  }, [taskId, projectId]);

  const handleTaskUpdate = useCallback(
    async (update: TaskUpdate): Promise<void> => {
      // ... existing artifact and message handling ...
      
      // Handle finished request IDs
      if (update.finished_request_ids && update.finished_request_ids.length > 0) {
        acknowledgeRequestFromSource(update.finished_request_ids, 'taskDetail');
      }
    },
    [fetchArtifact],
  );

  // ... rest of the hook ...
}
```

#### 5.3 Notifications Event Source Hook Update

```typescript
// common/state/hooks/useNotificationsEventSource.ts

import { useSetAtom } from "jotai";
import { useEffect } from "react";
import { useEventSource, type EventSourceHookReturn } from "./useEventSource";
import { notificationsAtom } from "../atoms/notifications";
import type { UserUpdate } from "../../../Types";
import { useImbueParams } from "../../NavigateUtils";
import { acknowledgeRequestFromSource, updateActiveEventSource } from "../utils/requestTracking";

const API_BASE_URL = "/api/v1";

export const useNotificationsEventSource = (): EventSourceHookReturn => {
  const { projectID } = useImbueParams();
  const setNotifications = useSetAtom(notificationsAtom);

  if (!projectID) {
    throw new Error("Expected projectID to be defined");
  }

  // Update active source status
  useEffect(() => {
    updateActiveEventSource('notifications', true);
    return () => {
      updateActiveEventSource('notifications', false);
    };
  }, []);

  return useEventSource({
    url: `${API_BASE_URL}/projects/${projectID}/notifications/stream`,
    onMessage: (data: UserUpdate) => {
      // Handle notifications
      if (data.notifications && data.notifications.length > 0) {
        setNotifications(data.notifications);
      }
      
      // Handle finished request IDs
      if (data.finishedRequestIds && data.finishedRequestIds.length > 0) {
        acknowledgeRequestFromSource(data.finishedRequestIds, 'notifications');
      }
    },
  });
};
```

### 6. Error Handling and Edge Cases

#### 6.1 Timeout Handling
- Requests automatically fail after 10 seconds if not acknowledged
- Failed promises include the request ID in the error message
- Timeout duration is configurable via `REQUEST_TIMEOUT_MS`

#### 6.2 Event Source Disconnection
- If an event source disconnects, requests continue waiting for other sources
- System gracefully handles partial acknowledgments
- Active source tracking ensures only required sources are waited for

#### 6.3 Page Navigation
- When navigating away from chat page, task detail source is marked inactive
- Pending requests automatically adjust their requirements
- No requests are left hanging due to navigation

#### 6.4 Cleanup
- All timeouts are cleared when requests complete or fail
- Memory leaks prevented by proper Map/Set cleanup
- Stale requests are removed from tracking

## Visual Flow Diagram

```
┌─────────────────┐
│ makeAPIRequest  │
└────────┬────────┘
         │ 1. Generate request ID
         │ 2. Create tracking promise with Jotai subscription
         ▼
┌─────────────────────────────────────────────────┐
│ createRequestTracker(requestId)                 │
│ - Creates Promise                               │
│ - Sets up: requestStore.sub(atom, callback)    │
│ - Subscription listens for atom changes        │
└────────┬────────────────────────────────────────┘
         │ 3. Make HTTP request
         ▼
┌─────────────────┐
│   API Server    │
└────────┬────────┘
         │ 4. Response + continues processing
         ▼
┌─────────────────────────────────────────────────┐
│          Event Sources (SSE)                    │
│ ┌─────────────┐ ┌──────────────┐ ┌───────────┐│
│ │Tasks Source │ │ Task Source  │ │Notif Source││
│ └──────┬──────┘ └──────┬───────┘ └─────┬─────┘│
└────────┼───────────────┼───────────────┼───────┘
         │               │               │
         │ 5. Receive finishedRequestIds │
         ▼               ▼               ▼
┌────────────────────────────────────────────────┐
│ acknowledgeRequestFromSource(ids, source)      │
│ - Updates requestAcknowledgmentsAtom          │
│ - Atom change triggers all subscriptions      │
└───────────────────────────┬────────────────────┘
                           │ 6. Subscription callback fires
                           ▼
┌────────────────────────────────────────────────┐
│ Subscription Callback (for each request)       │
│ - Checks if all required sources acknowledged  │
│ - If yes: resolve() promise                   │
│ - If no: wait for next atom update           │
└───────────────────────────┬────────────────────┘
                           │ 7. Promise resolves
                           ▼
┌─────────────────┐
│ Request returns │
│ to caller       │
└─────────────────┘
```

## Key Subscription Details

The Jotai subscription mechanism (`requestStore.sub`) is the core of the event-driven architecture:

1. **Subscription Setup**: 
   ```typescript
   unsubscribe = requestStore.sub(requestAcknowledgmentsAtom, () => {
     // This callback runs whenever the atom value changes
   });
   ```

2. **Atom Updates Trigger Callbacks**:
   - Any call to `requestStore.set(requestAcknowledgmentsAtom, newValue)` triggers all active subscriptions
   - Each subscription callback can check its specific request ID

3. **No Polling Required**:
   - The system is purely reactive
   - Updates flow: Event Source → Atom Update → Subscription Callback → Promise Resolution

4. **Cleanup**:
   - Each subscription returns an unsubscribe function
   - Called when request completes or times out
   - Prevents memory leaks

## Summary

This implementation ensures that API requests only resolve after the server has fully processed them and all relevant event sources have been updated. The solution is:
- **Event-Driven**: Uses Jotai subscriptions for reactive updates
- **Transparent**: No changes to API call sites
- **Robust**: Handles timeouts, disconnections, and navigation
- **Performant**: No polling, minimal overhead
- **Maintainable**: Clear separation of concerns, testable

The architecture leverages Jotai's store subscriptions to create a reliable, reactive system that solves the state consistency issues while maintaining a clean developer experience.
