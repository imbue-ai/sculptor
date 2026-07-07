// The single boundary between the Jotai layout atoms and storage. The state model
// talks ONLY to this interface — never to localStorage or any backend client
// directly — so swapping the backend (localStorage today → backend API later) is a
// one-line change of which adapter is installed.

import type { LayoutScope, LayoutSnapshotFor } from "./types.ts";

export type LayoutPersistenceAdapter = {
  /**
   * Synchronously return the cached snapshot for a scope, or undefined if it is
   * not (yet) hydrated. MUST be synchronous and total (never throw) — it is the
   * source for the pre-paint layout restore.
   *
   * A returned snapshot may predate fields that were added to its shape later
   * (additive schema growth is deliberately not a version bump), so callers must
   * spread it over the scope's defaults rather than trusting every field to be
   * present — see globalBaseAtom.
   */
  read<TScope extends LayoutScope>(scope: TScope): LayoutSnapshotFor<TScope> | undefined;

  /** Persist a scope's snapshot. Debounced/coalesced; fire-and-forget. */
  write<TScope extends LayoutScope>(scope: TScope, snapshot: LayoutSnapshotFor<TScope>): void;

  /** Drop a scope (workspace deleted). */
  remove(scope: LayoutScope): void;

  /**
   * Begin async hydration of a scope into the cache that `read` serves. No-op for
   * localStorage (already synchronous); for a backend, a GET that fills the cache.
   */
  prefetch?(scope: LayoutScope): void;
};
