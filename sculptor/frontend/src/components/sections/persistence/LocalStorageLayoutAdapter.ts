// localStorage implementation of LayoutPersistenceAdapter. Reads are synchronous
// and total (a corrupt entry must never break startup); writes are debounced and
// coalesced per key so rapid drag/resize updates collapse to a single setItem, with
// a beforeunload flush so pending writes are not lost on quit. Consolidated keys
// only — no prototype/legacy keys are read or written.

import type { LayoutPersistenceAdapter } from "./LayoutPersistenceAdapter.ts";
import type { LayoutScope, LayoutSnapshotFor, SidebarOrderState } from "./types.ts";
import { DEFAULT_GLOBAL_LAYOUT, EMPTY_WORKSPACE_LAYOUT, LAYOUT_SNAPSHOT_VERSION } from "./types.ts";

// Exported for the orphaned-key sweep (orphanedLayoutGc.ts), which scans raw
// localStorage keys for per-workspace snapshots.
export const WORKSPACE_KEY_PREFIX = "sculptor-layout-ws-";
const GLOBAL_KEY = "sculptor-layout-global";
const WRITE_DEBOUNCE_MS = 250;

function keyFor(scope: LayoutScope): string {
  return scope.kind === "global" ? GLOBAL_KEY : `${WORKSPACE_KEY_PREFIX}${scope.workspaceId}`;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// Structural guard so a valid-JSON-but-wrong-shape snapshot (e.g. a stale schema
// or a hand-edited entry) is treated as "nothing stored" rather than hydrated and
// crashing the layout atoms downstream. Intentionally shallow: it checks the
// presence/kind of the top-level fields each scope's atoms rely on, not every nested value.
function isValidSnapshot(scope: LayoutScope, value: unknown): boolean {
  if (!isObject(value)) {
    return false;
  }

  // A snapshot without a version stamp predates the stamp and parses as the
  // current version; anything else was written by a newer schema, so reject it
  // (the caller falls back to the default layout) rather than misreading it.
  if (value.version !== undefined && value.version !== LAYOUT_SNAPSHOT_VERSION) {
    return false;
  }

  if (scope.kind === "workspace") {
    return (
      isObject(value.placement) &&
      isObject(value.order) &&
      isObject(value.activePanel) &&
      isObject(value.expanded) &&
      isObject(value.splits) &&
      "activeSubSection" in value
    );
  }
  const sectionSizes = value.sectionSizes;
  // sidebarOrder is deliberately absent here: it may be missing (snapshots written
  // before the field existed) or corrupt without invalidating the user's other
  // settings — normalizeSnapshot handles it field-level on read.
  return (
    isObject(sectionSizes) &&
    typeof sectionSizes.left === "number" &&
    typeof sectionSizes.right === "number" &&
    typeof sectionSizes.bottom === "number" &&
    typeof value.sidebarWidthPx === "number" &&
    typeof value.sidebarCollapsed === "boolean" &&
    typeof value.explorerListWidthPx === "number"
  );
}

// The ordering atoms iterate sidebarOrder's lists, so a wrong-kind member (a
// hand-edited or corrupt entry) must never reach them. groupMembers is optional
// (snapshots persisted before workspace groups existed lack it), so it is
// validated only when present.
function isValidSidebarOrder(value: unknown): value is SidebarOrderState {
  return (
    isObject(value) &&
    Array.isArray(value.repos) &&
    isObject(value.workspaces) &&
    Object.values(value.workspaces).every((ids) => Array.isArray(ids)) &&
    (value.groupMembers === undefined ||
      (isObject(value.groupMembers) && Object.values(value.groupMembers).every((ids) => Array.isArray(ids))))
  );
}

// Fill fields a stored snapshot lacks from the scope's defaults, so additive
// schema growth never needs a version bump and read() always returns the full
// declared shape. A missing or corrupt sidebarOrder degrades to the default
// order on its own instead of invalidating the user's other settings.
function normalizeSnapshot<TScope extends LayoutScope>(
  scope: TScope,
  snapshot: Record<string, unknown>,
): LayoutSnapshotFor<TScope> {
  if (scope.kind === "workspace") {
    return { ...EMPTY_WORKSPACE_LAYOUT, ...snapshot } as LayoutSnapshotFor<TScope>;
  }
  const sidebarOrder = isValidSidebarOrder(snapshot.sidebarOrder)
    ? snapshot.sidebarOrder
    : DEFAULT_GLOBAL_LAYOUT.sidebarOrder;
  return { ...DEFAULT_GLOBAL_LAYOUT, ...snapshot, sidebarOrder } as LayoutSnapshotFor<TScope>;
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
    const key = keyFor(scope);
    // A debounced write parks the newest snapshot in `pending` until it flushes;
    // return it (minus the storage-only version stamp) so a read inside the
    // debounce window sees that snapshot rather than the previous flushed value.
    const pending = this.pending.get(key);
    if (pending !== undefined) {
      const snapshot = { ...(pending as Record<string, unknown>) };
      delete snapshot.version;
      return normalizeSnapshot(scope, snapshot);
    }

    try {
      const raw = localStorage.getItem(key);
      if (raw === null) {
        return undefined;
      }
      const parsed: unknown = JSON.parse(raw);
      if (!isValidSnapshot(scope, parsed)) {
        // Wrong-shape or future-version snapshot (e.g. stale schema or a
        // hand-edited entry): treat as "nothing stored" so the atoms fall
        // back to their safe defaults.
        return undefined;
      }
      // The version stamp is storage metadata; strip it so it never leaks into
      // the in-memory layout state (writes re-stamp it).
      const snapshot = { ...(parsed as Record<string, unknown>) };
      delete snapshot.version;
      return normalizeSnapshot(scope, snapshot);
    } catch {
      // Missing localStorage or corrupt JSON must not break startup.
      return undefined;
    }
  }

  write<TScope extends LayoutScope>(scope: TScope, snapshot: LayoutSnapshotFor<TScope>): void {
    this.pending.set(keyFor(scope), { ...snapshot, version: LAYOUT_SNAPSHOT_VERSION });
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

  // Removes the beforeunload listener and cancels any pending flush. The exported
  // singleton lives for the page lifetime, so this exists mainly so short-lived
  // instances (e.g. in tests) don't leak a listener.
  dispose(): void {
    if (typeof window !== "undefined") {
      window.removeEventListener("beforeunload", this.flush);
    }

    if (this.flushTimer !== null) {
      clearTimeout(this.flushTimer);
      this.flushTimer = null;
    }
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
