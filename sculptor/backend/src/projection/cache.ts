// The warm per-agent projection cache.
//
// Why this exists (architecture *Persistence* §2 / plan 04_04 "Why the warm
// cache"): building a snapshot per connect is cheap for indexed current-state
// reads, but folding the WHOLE agent_message log -> ChatMessage[] for active
// agents is the expensive part and would block the synchronous event loop. So
// we keep a warm in-memory per-agent projection the runner updates
// incrementally as messages arrive (Task 4.2 incremental fold + Task 4.3 view
// recompute), so connect serves folded chat from memory.
//
// CRITICAL property (plan 04_04 gotcha): the incremental result MUST equal a
// full re-fold (`foldMessages`), or reconnect shows different chat than live.
// cache.test.ts asserts this.
//
// Replaces the per-connection `completed_message_by_task_id` /
// `task_views_by_task_id` state in sculptor/sculptor/web/streams.py L566-567,
// hoisting it out of the per-connection generator into one process-wide cache.

import type { Orm } from "~/db/orm";
import type { AgentRow } from "~/db/schema/agent";
import { getAgent, listAgentMessages } from "~/db/repositories";
import type { ChatMessage } from "~/projection/chat_types";
import { computeAgentView } from "~/projection/derived";
import {
  applyMessage,
  createFoldState,
  type FoldState,
  foldStateToChatMessages,
} from "~/projection/message_conversion";
import type { RawMessage } from "~/projection/message_log";
import type { CodingAgentTaskView } from "~/projection/view_types";

// Bound on how many of the most-recent raw messages we retain per agent for the
// view recompute (the fold itself keeps its own bounded ChatMessage state). The
// derived view (Task 4.3) only ever inspects the tail of the log, so we cap the
// retained raw messages to keep memory flat for very long-running agents.
const DEFAULT_MAX_RAW_MESSAGES = 2000;

interface CacheEntry {
  agent: AgentRow;
  foldState: FoldState;
  chatMessages: ChatMessage[];
  view: CodingAgentTaskView;
  // The tail of the raw message log, used to recompute the derived view. The
  // fold consumes the full stream incrementally; this is only the view's input.
  rawMessages: RawMessage[];
}

export interface ProjectionCacheOptions {
  maxRawMessages?: number;
}

// Per-agent warm projection. Process-wide singleton (see `projectionCache`
// below); the runner pushes messages in, snapshot/delta reads them out.
export class ProjectionCache {
  private readonly entries = new Map<string, CacheEntry>();
  private readonly maxRawMessages: number;

  constructor(options: ProjectionCacheOptions = {}) {
    this.maxRawMessages = options.maxRawMessages ?? DEFAULT_MAX_RAW_MESSAGES;
  }

  // Lazily fold an agent's history from the DB on first need (bounded), then
  // serve all subsequent reads from memory. Mirrors the per-connection initial
  // fold in streams.py, but done once and shared.
  ensure(orm: Orm, agentId: string): CacheEntry | undefined {
    const existing = this.entries.get(agentId);
    if (existing !== undefined) {
      return existing;
    }
    const agent = getAgent(orm, agentId);
    if (agent === undefined) {
      return undefined;
    }
    const rows = listAgentMessages(orm, agentId, { includePartial: true });
    const rawMessages: RawMessage[] = rows.map((row) => row.message as RawMessage);
    const foldState = createFoldState();
    for (const message of rawMessages) {
      applyMessage(foldState, message);
    }
    const boundedRaw = this.boundRaw(rawMessages);
    const entry: CacheEntry = {
      agent,
      foldState,
      chatMessages: foldStateToChatMessages(foldState),
      view: computeAgentView(agent, boundedRaw),
      rawMessages: boundedRaw,
    };
    this.entries.set(agentId, entry);
    return entry;
  }

  // Apply a single new message incrementally (Task 4.2 incremental fold + Task
  // 4.3 view recompute). The runner calls this as each message is persisted, so
  // history is never re-folded on the hot path. Lazily fills from the DB first
  // if the agent is cold, so a message for an unseen agent still folds its prior
  // history exactly once.
  applyMessage(orm: Orm, agentId: string, message: RawMessage): CacheEntry | undefined {
    const entry = this.ensure(orm, agentId);
    if (entry === undefined) {
      return undefined;
    }
    applyMessage(entry.foldState, message);
    entry.chatMessages = foldStateToChatMessages(entry.foldState);
    entry.rawMessages = this.boundRaw([...entry.rawMessages, message]);
    entry.view = computeAgentView(entry.agent, entry.rawMessages);
    return entry;
  }

  // Refresh the cached agent row (run-state / title changed) and recompute the
  // view. Used by the agent_status delta path.
  refreshAgent(orm: Orm, agentId: string): CacheEntry | undefined {
    const entry = this.ensure(orm, agentId);
    if (entry === undefined) {
      return undefined;
    }
    const agent = getAgent(orm, agentId);
    if (agent === undefined) {
      // The agent was deleted; drop it from the warm set.
      this.entries.delete(agentId);
      return undefined;
    }
    entry.agent = agent;
    entry.view = computeAgentView(agent, entry.rawMessages);
    return entry;
  }

  getChatMessages(orm: Orm, agentId: string): ChatMessage[] {
    return this.ensure(orm, agentId)?.chatMessages ?? [];
  }

  getView(orm: Orm, agentId: string): CodingAgentTaskView | undefined {
    return this.ensure(orm, agentId)?.view;
  }

  // Drop a cold/closed agent so memory stays bounded by the active set. Called
  // when an agent is deleted or its workspace is closed.
  evict(agentId: string): void {
    this.entries.delete(agentId);
  }

  has(agentId: string): boolean {
    return this.entries.has(agentId);
  }

  clear(): void {
    this.entries.clear();
  }

  private boundRaw(messages: RawMessage[]): RawMessage[] {
    if (messages.length <= this.maxRawMessages) {
      return messages;
    }
    return messages.slice(messages.length - this.maxRawMessages);
  }
}

// Process-wide singleton, mirroring `eventBus` in src/events/index.ts.
export const projectionCache = new ProjectionCache();
