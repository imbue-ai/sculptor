import { FolderOpen, Globe, NotebookPen, SquareSlash, Terminal, Zap } from "lucide-react";

import type { DefaultPanelLayout, PanelDefinition } from "~/components/panels/types.ts";

import { ActionsPanel } from "./ActionsPanel.tsx";
import { BrowserPanel } from "./BrowserPanel.tsx";
import { FileBrowserPanel } from "./FileBrowserPanel.tsx";
import { NotesPanel } from "./NotesPanel.tsx";
import { SkillsPanel } from "./SkillsPanel.tsx";
import { TerminalPanelWrapper } from "./TerminalPanel.tsx";

export const workspacePanels: ReadonlyArray<PanelDefinition> = [
  {
    id: "files",
    displayName: "File browser",
    description: "Browse repo files and diffs",
    icon: FolderOpen,
    defaultZone: "top-left",
    defaultShortcut: "",
    component: FileBrowserPanel,
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
    id: "notes",
    displayName: "Notes",
    description: "Take notes alongside your workspace",
    icon: NotebookPen,
    defaultZone: "bottom-right",
    defaultShortcut: "",
    component: NotesPanel,
    defaultEnabled: false,
  },
  {
    id: "browser",
    displayName: "Browser",
    description: "Open a browser inside the workspace",
    icon: Globe,
    defaultZone: "top-right",
    defaultShortcut: "",
    component: BrowserPanel,
    defaultEnabled: false,
  },
];

/** Default layout: Files (top-left) and Terminal (bottom) expanded; Actions collapsed. */
export const workspaceDefaultLayout: DefaultPanelLayout = {
  zoneAssignments: {
    files: "top-left",
    actions: "top-right",
    skills: "top-right",
    browser: "top-right",
    notes: "bottom-right",
    terminal: "bottom",
  },
  activePanelPerZone: {
    "top-left": "files",
    "top-right": "actions",
    bottom: "terminal",
    "bottom-right": "notes",
  },
  zoneVisibility: {
    "top-left": true,
    "top-right": false,
    bottom: true,
    "bottom-right": false,
  },
  zoneOrder: {
    "top-left": ["files"],
    "top-right": ["actions", "skills", "browser"],
    bottom: ["terminal"],
    "bottom-right": ["notes"],
  },
};
