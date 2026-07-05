# SCU-1746 structure pass — decisions made autonomously (for Bryden's review)

Working log of judgment calls made while executing the agreed plan without you.
Nothing here changes the agreed principles; these are placements/namings the
principles didn't fully determine. Flip any of them and I'll rework.

## Made (flag if you disagree)

1. **`apiClient.ts` → `common/apiClient.ts`.** Root keeps only build/bootstrap
   entries (`Main.tsx`, `instrument.ts`, `preload.ts`, css/env types). The
   configured API client is shared non-UI glue → `common/`.
2. **`sectionTypes.ts` → `layout/types/section.ts`.** It's mostly types +
   guards; the guards ride with their types rather than splitting into utils/.
3. **`diffPanel/` and `diffViewer/` stay separate features** under
   `pages/workspace/` for now (pure moves only). They look like one `diff/`
   feature with two subfeatures — flagged as a candidate follow-up rather than
   mixing a merge into the rename commits.
4. **`CommandPalette/` → `commandPalette/`** per the camelCase-dirs rule (it
   was the one PascalCase directory).
5. **`sections/persistence/types.ts` → `persistence/snapshot.ts`** (generic
   basename ban applies inside subfeatures too; the file is the snapshot
   schema).
6. **`useWorkspaceTabActions` (SCU-1748) → `common/state/hooks/`.**
   (Superseded my earlier `app/hooks/` call: commandPalette imports it, and
   components/ must not import app/ — the hook fronts tab state, so the state
   mirror is its home. See execution-plan.md ruling 2.)
7. **`NewWorkspaceModal` → `NewWorkspaceDialog`** executed as part of the
   suffix-glossary cleanup (Modal suffix retired), per the approved glossary.
8. **Stories mirror is realigned in PR1** (cheap renames) even though PR3
   colocates stories — PR1 must be self-consistent with its own docs; PR3
   updates the docs and moves stories beside components.

## Blocked / needs you

- **Linear is unreachable from this workspace** (`LINEAR_API_KEY` vanished when
  the harness restarted mid-session; all calls 401). Child-ticket state
  updates and the two new follow-up tickets (chat rename, stories colocation)
  are pending — the work itself proceeded. A workspace restart or env re-sync
  should fix it.

9. **Layout state stayed feature-side (ruling 4 fallback).** Global and
   per-workspace layout snapshots share one persistence adapter (one debounce
   map, one flush path); splitting the global slice into `common/state` would
   mean carving that adapter in half or moving it wholesale to `common/`. So
   all layout state lives in `pages/workspace/layout/atoms/`, and the Stage H
   boundaries lint carries explicit exceptions for its commandPalette/app/
   common readers. The real fix is a follow-up: either promote the whole
   layout-state module to `common/state`, or invert the palette's workspace
   commands into a registration pattern (features register commands, like
   panels register components).

## Follow-up candidates surfaced during the work (not executed)

- Merge `diffPanel/` + `diffViewer/` into one `diff/` feature (see 3).
- Four delete-confirmation components coexist (`DeleteConfirmationDialog`,
  `WorkspaceDeleteConfirmation`, `AgentDeleteConfirmation`, plus a
  sidebar-local dialog) — consolidation candidate found by the baseline
  inferability test.
- Backend rename of wire `task` vocabulary (would let the frontend drop the
  last `task_id` field names at the API seam).
