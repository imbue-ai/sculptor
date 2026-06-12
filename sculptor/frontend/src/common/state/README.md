# Sculptor Frontend Architecture

## Overview and Design Philosophy

The core idea behind the frontend architecture is simple: the frontend is reactive to backend state.

The backend continuously streams the full UI-relevant state to the frontend. The frontend treats this state as the source of truth and reacts to changes, rather than actively fetching, coordinating, or deriving complex state during rendering.

As a result:
- Most UI components do not fetch data
- Most UI components do not coordinate useEffects
- Most UI components simply read from global state via helper hooks

Because the backend sends a full snapshot on connect and incremental updates afterward, the data a component needs is already present in the global state cache by the time the component renders.

This greatly simplifies the mental model for building UI:
- If you need backend data, use the provided hook
- If the hook exists, the data will already be there

### Backend-for-Frontend (BFF)

We intentionally derive as much UI state as possible on the backend (a backend-for-frontend model).

This lets us:
- Derive UI state in a single-threaded Python context
- Avoid complex, error-prone state derivation during React renders
- Generate TypeScript types directly from backend models
- Avoid redundant or divergent type definitions on the frontend
- Hide backend domain concepts (e.g. AgentMessage) behind UI-focused data types

The frontend primarily consumes already-shaped UI data, rather than raw domain objects.

### Frontend-only state

Some state still lives purely on the frontend, mainly:
- Transient UI state (hover, focus, local form state)
- Interactive state tied to user actions

We synchronize this state with backend-driven state using request tracking, which is described later.

### Roadmap

At a high level, the rest of this document covers:
	1.	How global state is structured (Jotai patterns)
	2.	How backend updates arrive via the websocket
	3.	How request tracking keeps interactive UI consistent
	4.	How the generated API client fits into this model

⸻

## Global State

We use Jotai for global state management. There are two main patterns.

1. Atom families for backend-owned state

For most backend-owned entities, we define atom families, usually keyed by taskID or projectID.

Examples include:
- `CodingAgentTaskView`
- `TaskDetail`
- `Project`

These atoms are populated and updated exclusively via the websocket. Incoming updates from the backend are merged into existing atom values using per-field merge strategies.

Important: You should never write to these atoms directly. Instead, use the provided hooks (e.g. useTaskDetail, useProject), which read from the atoms and expose a more ergonomic interface.

This keeps the frontend consistent with backend state and avoids subtle bugs.

2. Standalone atoms with derived read-only atoms

For some frontend-owned or bootstrapped state, we define a single atom with composite state, plus derived read-only atoms that select specific fields.

Example:
- `userConfigAtom` is fetched once when the app loads
-  derived atoms like `appTheme` or `sendMessageShortcut` read from it

In this pattern, components usually read directly from atoms rather than through hooks. These atoms should still be treated as read-only in practice—avoid writing to them outside of well-defined initialization logic.

⸻

## Websocket Architecture

The backend aggregates updates from many sources and multiplexes them through a single websocket connection to the frontend.

Event sources include:
- Task updates (e.g. assistant responses, task status changes)
-  Database updates (e.g. new tasks, project path changes)
-  Repository updates (e.g. new commits or branches)

On connection, the backend sends a full snapshot of all UI-relevant state. This is used to initialize global atoms. After that, updates are sent as deltas, which are merged into existing state.

The payload shape looks like this:

```python
class StreamingUpdate(SerializableModel):
    task_update_by_task_id: dict[TaskID, TaskUpdate] = Field(default_factory=dict)
    task_views_by_task_id: dict[TaskID, CodingAgentTaskView] = Field(default_factory=dict)
    user_update: UserUpdate = Field(default_factory=UserUpdate)
    local_repo_info_by_project_id: dict[ProjectID, LocalRepoInfo | None] = Field(default_factory=dict)
    finished_request_ids: tuple[RequestID, ...] = ()
```

Each field has its own internal structure. See the corresponding model definitions for details.

On the frontend, `useUnifiedStream.ts` processes these updates field-by-field. For more complex state, merge logic is split into reducer files (e.g. `taskDetailReducers.ts`) to keep things manageable.

⸻

## Request Tracking

Some UI bugs come from brief mismatches between interactive components like buttons or forms, which have state stored on the frontend, and pure components, which depend only on backend state.

Pure components follow this flow:

```
websocket → global atom → component
```

Interactive components, however, may trigger REST API calls and temporarily depend on their results.

### The problem

Example: a “delete task” button.
- The button calls a REST endpoint
- Task list is driven by websocket state
- API call may return before the websocket update arrives
- So the button may resolve before the task is actualy gone from the task list, which may be confusing

### The solution

We use request tracking to align REST responses with websocket state.
- Every API call gets a unique requestID
-  The backend includes that requestID in the websocket update that reflects the result
-  The API client does not resolve the promise until the matching requestID appears in a websocket update

This guarantees that interactive components only update after global state is consistent.

Implementation details:
- A dedicated Jotai store tracks in-flight and completed request IDs
- The API client subscribes to this store and waits for acknowledgment
- Default timeout is 10 seconds; after that, the request fails

Relevant files:
	•	`requestStore.ts`
	•	`requestTracking.ts`
	•	`apiClient.ts`

⸻

## API Client

We use HeyAPI to generate a TypeScript API client from our FastAPI backend.

This gives us:
- Typed request and response models
- One callable function per backend endpoint

Whenever backend endpoints change, regenerate the client:

```bash
just generate-api
# or
npm run generate-api
```

The generated client also injects middleware for:
- Authentication headers
- Request tracking (described above)

The client generation config is in `openapi-ts.config.ts`.

### Calling an endpoint

Typical usage looks like this:

```typescript
try {
	await sendMessage({
		path: { project_id: projectID, task_id: taskID },
		body: { message: promptDraft, model: localModel, files: attachedFiles },
	});
} catch (e) {
	console.error('Error sending message:', e);
}
```

### Request tracking options

All API calls support optional meta arguments:
- `skipWsAck`: do not wait for websocket acknowledgment
- `wsTimeout`: override the default timeout

If request tracking is enabled, the backend must wrap the endpoint logic in a transaction so the requestID is emitted via post-commit hooks:

```python
with user_session.open_transaction(services) as transaction:
	# do something
```

If this is missing, the frontend will wait until timeout.

For endpoints that don’t affect websocket-visible state, you can opt out:

```typescript
try {
	await sendMessage({
		path: { project_id: projectID, task_id: taskID },
		body: { message: promptDraft, model: localModel, files: attachedFiles },
		meta: { skipWsAck: true },
	});
} catch (e) {
	console.error('Error sending message:', e);
}
```
