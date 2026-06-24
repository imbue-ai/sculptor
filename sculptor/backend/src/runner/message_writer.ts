import { appendAgentMessage, isPartialMessage } from "~/db/repositories";
import type { Orm } from "~/db/orm";
import { ProjectionCache, projectionCache } from "~/projection/cache";

// Coalesces high-frequency partial-chunk writes so the synchronous SQLite
// writer isn't flooded with one row per token (architecture *Persistence
// engine* mitigation #1). Two rates are decoupled:
//   - the stream/render rate: every message is pushed to the warm cache + bus
//     immediately, so live updates stay smooth (REQ-NFR-001) — never throttled.
//   - the DB write rate: partial rows are persisted only at a bounded cadence
//     (every N chunks or after T ms), with the latest buffered partial always
//     flushed before a non-partial message and a finalized message written
//     exactly once. is_partial stays correct so a cold re-fold (Task 4.2) still
//     folds sensibly.

const MAX_BUFFERED_PARTIAL_CHUNKS = 20;
const MAX_PARTIAL_FLUSH_INTERVAL_MS = 250;

export interface MessageWriterDeps {
  orm: Orm;
  agentId: string;
  // Pushes a stream delta out (bus publish) for every message — the live path.
  onStream: (message: Record<string, unknown>) => void;
  cache?: ProjectionCache;
  now?: () => number;
}

export class MessageWriter {
  private pendingPartial: Record<string, unknown> | undefined;
  private chunksSinceFlush = 0;
  private lastFlushAt: number;

  constructor(private readonly deps: MessageWriterDeps) {
    this.lastFlushAt = (deps.now ?? Date.now)();
  }

  private get cache(): ProjectionCache {
    return this.deps.cache ?? projectionCache;
  }

  private now(): number {
    return (this.deps.now ?? Date.now)();
  }

  write(message: Record<string, unknown>): void {
    // Stream (always): the warm cache folds every chunk and the bus delivers it.
    this.cache.applyMessage(this.deps.orm, this.deps.agentId, message);
    this.deps.onStream(message);

    // Persist (coalesced).
    if (isPartialMessage(message)) {
      this.pendingPartial = message;
      this.chunksSinceFlush += 1;
      if (
        this.chunksSinceFlush >= MAX_BUFFERED_PARTIAL_CHUNKS ||
        this.now() - this.lastFlushAt >= MAX_PARTIAL_FLUSH_INTERVAL_MS
      ) {
        this.flush();
      }
      return;
    }
    // A non-partial message: make the last buffered partial durable, then write
    // the finalized/other message exactly once.
    this.flush();
    this.persist(message);
  }

  // Persist any buffered partial (called on segment completion / supervisor exit
  // so the latest streamed content is durable).
  flush(): void {
    if (this.pendingPartial !== undefined) {
      this.persist(this.pendingPartial);
      this.pendingPartial = undefined;
    }
    this.chunksSinceFlush = 0;
    this.lastFlushAt = this.now();
  }

  private persist(message: Record<string, unknown>): void {
    try {
      appendAgentMessage(this.deps.orm, this.deps.agentId, message);
    } catch {
      // A malformed message that fails the append invariants is not persisted;
      // never let it crash the writer.
    }
  }
}
