// The session-id state files Sculptor writes under the agent's state directory.
// `session_id` is the latest id the CLI reported; `validated_session_id` is the
// last id that passed validation — the resume fallback when the primary pointer
// is stale (ports `harness.py` state-file names + the rollback in
// `process_manager.py:_process_single_message`, also read by
// `btw_process_manager.py`).

import path from "node:path";

import {
  SESSION_ID_STATE_FILE_NAME,
  VALIDATED_SESSION_ID_STATE_FILE_NAME,
} from "~/harness/claude/constants";

// The state-store surface used here; `LocalEnvironment` satisfies it structurally.
export interface SessionStateStore {
  getStatePath(agentId: string): string;
  readTextFile(p: string): Promise<string>;
  writeFile(p: string, content: string): Promise<void>;
}

async function readStateFile(
  store: SessionStateStore,
  agentId: string,
  fileName: string,
): Promise<string | null> {
  try {
    const content = (
      await store.readTextFile(path.join(store.getStatePath(agentId), fileName))
    ).trim();
    return content || null;
  } catch {
    return null;
  }
}

export function readSessionIdState(
  store: SessionStateStore,
  agentId: string,
): Promise<string | null> {
  return readStateFile(store, agentId, SESSION_ID_STATE_FILE_NAME);
}

export function readValidatedSessionIdState(
  store: SessionStateStore,
  agentId: string,
): Promise<string | null> {
  return readStateFile(store, agentId, VALIDATED_SESSION_ID_STATE_FILE_NAME);
}

export function writeSessionIdState(
  store: SessionStateStore,
  agentId: string,
  sessionId: string,
): Promise<void> {
  return store.writeFile(
    path.join(store.getStatePath(agentId), SESSION_ID_STATE_FILE_NAME),
    sessionId,
  );
}

export function writeValidatedSessionIdState(
  store: SessionStateStore,
  agentId: string,
  sessionId: string,
): Promise<void> {
  return store.writeFile(
    path.join(
      store.getStatePath(agentId),
      VALIDATED_SESSION_ID_STATE_FILE_NAME,
    ),
    sessionId,
  );
}
