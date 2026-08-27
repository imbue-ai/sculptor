import { atom } from "jotai";

// Count of in-flight sidebar drags. A count, not a boolean, because the sidebar
// hosts many independent drag contexts (one per repo group's rows plus the group
// list) and a parked keyboard drag in one can coexist with a drag in another —
// a boolean cleared by whichever context finishes first would drop the other
// drag's suppression. Transient (never persisted).
const sidebarActiveDragCountAtom = atom(0);

// True while any sidebar row or repo group is being dragged. The workspace peek
// overlay reads it to stay closed mid-drag (the pointer sweeps across rows while
// sorting), and the sidebar root stamps it as a data flag so the stylesheet can
// suppress hover chrome rail-wide.
export const isSidebarDragActiveAtom = atom((get) => get(sidebarActiveDragCountAtom) > 0);

// Adjust the in-flight drag count, clamped at zero so a stray release can never
// underflow it. Each drag context pairs +1 on drag start with exactly one -1
// (drag end, cancel, or its unmount cleanup), guarded by an ownership ref.
export const adjustSidebarDragCountAtom = atom(null, (get, set, delta: 1 | -1) => {
  set(sidebarActiveDragCountAtom, Math.max(0, get(sidebarActiveDragCountAtom) + delta));
});
