// localStorage implementation of LayoutPersistenceAdapter. Reads are synchronous
// and total (a corrupt entry must never break startup); writes are debounced and
// coalesced per key so rapid drag/resize updates collapse to a single setItem, with
// a beforeunload flush so pending writes are not lost on quit. Consolidated keys
// only — no prototype/legacy keys are read or written.

import type { LayoutPersistenceAdapter } from "./LayoutPersistenceAdapter.ts";
import type { LayoutScope, LayoutSnapshotFor } from "./types.ts";

const WORKSPACE_KEY_PREFIX = "sculptor-layout-ws-";
const GLOBAL_KEY = "sculptor-layout-global";
const WRITE_DEBOUNCE_MS = 250;

function keyFor(scope: LayoutScope): string {
  return scope.kind === "global" ? GLOBAL_KEY : `${WORKSPACE_KEY_PREFIX}${scope.workspaceId}`;
}

export class LocalStorageLayoutAdapter implements LayoutPersistenceAdapter {
  private readonly pending = new Map<string, unknown>();
  private flushTimer: ReturnType<typeof setTimeout> | null = null;

  constructor() {
    if (typeof window !== "undefined") {
      window.addEventListener("beforeunload", this.flush);
    }
  }

  read<TScope extends LayoutScope>(scope: TScope): LayoutSnapshotFor<TScope> | undefined {
    try {
      const raw = localStorage.getItem(keyFor(scope));
      if (raw === null) {
        return undefined;
      }
      return JSON.parse(raw) as LayoutSnapshotFor<TScope>;
    } catch {
      // Missing localStorage or corrupt JSON must not break startup.
      return undefined;
    }
  }

  write<TScope extends LayoutScope>(scope: TScope, snapshot: LayoutSnapshotFor<TScope>): void {
    this.pending.set(keyFor(scope), snapshot);
    this.scheduleFlush();
  }

  remove(scope: LayoutScope): void {
    const key = keyFor(scope);
    this.pending.delete(key);
    try {
      localStorage.removeItem(key);
    } catch {
      // Ignore: nothing to clean up if storage is unavailable.
    }
  }

  prefetch(): void {
    // No-op: localStorage reads are already synchronous.
  }

  private scheduleFlush(): void {
    if (this.flushTimer !== null) {
      return;
    }
    this.flushTimer = setTimeout(this.flush, WRITE_DEBOUNCE_MS);
  }

  // Arrow so it can be used directly as the beforeunload handler and setTimeout
  // callback without losing `this`.
  flush = (): void => {
    if (this.flushTimer !== null) {
      clearTimeout(this.flushTimer);
      this.flushTimer = null;
    }

    for (const [key, snapshot] of this.pending) {
      try {
        localStorage.setItem(key, JSON.stringify(snapshot));
      } catch {
        // Drop the write if storage is unavailable or full.
      }
    }
    this.pending.clear();
  };
}

// The installed adapter the layout atoms import. Swapping to a backend later is
// changing this one export.
export const layoutPersistenceAdapter: LayoutPersistenceAdapter = new LocalStorageLayoutAdapter();
