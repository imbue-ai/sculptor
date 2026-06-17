import { FileDiff, FolderTree, GitCommitHorizontal, Globe, Layers, NotebookPen, SquareSlash, Zap } from "lucide-react";

import type { DefaultPanelLayout, PanelDefinition } from "~/components/panels/types.ts";

import { ActionsPanel } from "./ActionsPanel.tsx";
import { BrowserPanel } from "./BrowserPanel.tsx";
import { ChangesPanel } from "./ChangesPanel.tsx";
import { CommitsPanel } from "./CommitsPanel.tsx";
import { FilesPanel } from "./FilesPanel.tsx";
import { NotesPanel } from "./NotesPanel.tsx";
import { ReviewAllPanel } from "./ReviewAllPanel.tsx";
import { SkillsPanel } from "./SkillsPanel.tsx";

// Static panels. The file browser is split into Files / Changes / Commits plus
// Review All (REQ-PANEL-1, REQ-CENTER-5). Agents and terminals are NOT here —
// they are dynamic, per-workspace panels (see dynamicPanels.tsx) added to the
// registry at runtime (REQ-AGENT-1 / REQ-TERM-2).
export const workspacePanels: ReadonlyArray<PanelDefinition> = [
  {
    id: "files",
    displayName: "Files",
    description: "Browse repo files",
    icon: FolderTree,
    defaultZone: "top-left",
    defaultShortcut: "",
    component: FilesPanel,
  },
  {
    id: "changes",
    displayName: "Changes",
    description: "View uncommitted and branch changes",
    icon: FileDiff,
    defaultZone: "top-left",
    defaultShortcut: "",
    component: ChangesPanel,
  },
  {
    id: "commits",
    displayName: "Commits",
    description: "Browse the commit history",
    icon: GitCommitHorizontal,
    defaultZone: "top-left",
    defaultShortcut: "",
    component: CommitsPanel,
  },
  {
    id: "review-all",
    displayName: "Review All",
    description: "Review the combined multi-file diff",
    icon: Layers,
    defaultZone: "top-right",
    defaultShortcut: "",
    component: ReviewAllPanel,
  },
  {
    id: "actions",
    displayName: "Actions",
    description: "Run saved commands against the workspace",
    icon: Zap,
    defaultZone: "top-right",
    defaultShortcut: "",
    component: ActionsPanel,
  },
  {
    id: "skills",
    displayName: "Skills",
    description: "Browse and manage skills available in the workspace",
    icon: SquareSlash,
    defaultZone: "top-right",
    defaultShortcut: "",
    component: SkillsPanel,
  },
  {
    id: "browser",
    displayName: "Browser",
    description: "Open a browser inside the workspace",
    icon: Globe,
    defaultZone: "top-right",
    defaultShortcut: "",
    component: BrowserPanel,
  },
  {
    id: "notes",
    displayName: "Notes",
    description: "Take notes alongside your workspace",
    icon: NotebookPen,
    defaultZone: "top-right",
    defaultShortcut: "",
    component: NotesPanel,
  },
];

/**
 * Default first-load layout (REQ-DEFAULT-1):
 *   - Left section (top-left) collapsed, pre-seeded with Files, Changes, Commits
 *     (Files active) — so a clean first launch is just Chat, and toggling the
 *     Left section reveals the file panels immediately.
 *   - Center section visible: the default agent (placed at runtime — its panel
 *     id is a task id, unknown at static-config time).
 *   - Right section (top-right) empty and collapsed.
 *   - Bottom section collapsed, starting with the Terminal (also placed at
 *     runtime). Agent/terminal bootstrap lives in `useWorkspaceLayoutBootstrap`.
 */
export const workspaceDefaultLayout: DefaultPanelLayout = {
  zoneAssignments: {
    files: "top-left",
    changes: "top-left",
    commits: "top-left",
  },
  activePanelPerZone: {
    "top-left": "files",
  },
  zoneVisibility: {
    "top-left": false,
    center: true,
    "top-right": false,
    bottom: false,
  },
  zoneOrder: {
    "top-left": ["files", "changes", "commits"],
  },
};
