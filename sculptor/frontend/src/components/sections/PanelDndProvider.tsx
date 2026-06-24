// The single app-level drag-and-drop context that wraps the whole section grid
// (component_hierarchy.md → "Drag-and-drop architecture"). This is a pass-through
// stub for now so the shell tree compiles and renders; the real dnd-kit context,
// drag preview, and drop targets land in Task 4.1.

import type { ReactElement, ReactNode } from "react";

// Task 4.1: real dnd-kit context (drag preview + per-section drop targets).
export const PanelDndProvider = ({ children }: { children: ReactNode }): ReactElement => <>{children}</>;
