import {
  FileDiff,
  FolderTree,
  GitCommitHorizontal,
  Globe,
  Layers,
  NotebookPen,
  SquareSlash,
  Terminal,
  Zap,
} from "lucide-react";

import type { DefaultPanelLayout, PanelDefinition } from "~/components/panels/types.ts";

import { ActionsPanel } from "./ActionsPanel.tsx";
import { BrowserPanel } from "./BrowserPanel.tsx";
import { ChangesPanel } from "./ChangesPanel.tsx";
import { CommitsPanel } from "./CommitsPanel.tsx";
import { FilesPanel } from "./FilesPanel.tsx";
import { NotesPanel } from "./NotesPanel.tsx";
import { ReviewAllPanel } from "./ReviewAllPanel.tsx";
import { SkillsPanel } from "./SkillsPanel.tsx";
import { TerminalPanelWrapper } from "./TerminalPanel.tsx";

// Compact layout: the file browser is split into three separate panels — Files,
// Changes, Commits — plus Review All as its own panel (REQ-PANEL-1, REQ-CENTER-5).
// Every section panel is addable via a section's "+" dropdown; the terminal is
// special-cased to the Bottom zone only (REQ-ZONE-3).
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
    id: "terminal",
    displayName: "Terminal",
    description: "Open a terminal in the workspace container",
    icon: Terminal,
    defaultZone: "bottom",
    defaultShortcut: "",
    component: TerminalPanelWrapper,
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
 *   - Left section (top-left) visible: Files, Changes, Commits (Files active).
 *   - Right section (top-right) empty and collapsed — Review All / Browser /
 *     Actions / Skills / Notes start unplaced and are added via the "+" dropdown.
 *   - Bottom terminal collapsed.
 */
export const workspaceDefaultLayout: DefaultPanelLayout = {
  zoneAssignments: {
    files: "top-left",
    changes: "top-left",
    commits: "top-left",
    terminal: "bottom",
  },
  activePanelPerZone: {
    "top-left": "files",
    bottom: "terminal",
  },
  zoneVisibility: {
    "top-left": true,
    "top-right": false,
    bottom: false,
  },
  zoneOrder: {
    "top-left": ["files", "changes", "commits"],
    bottom: ["terminal"],
  },
};
