// The single point where panel components are bound to the registry SectionBody
// resolves against. Each panel module exports its component; this module imports them
// and calls the matching register function with the panel id spelled out at the call
// site, so the id → component mapping is auditable in one place rather than scattered
// across module-scope side effects. Static panels map id → component; the agent and
// terminal base components have no static id (their ids are derived per instance in
// dynamicPanels). Registration runs when WorkspaceLayoutShell imports this module at
// app load. A new panel registers here — add its import and register call below.

import {
  registerAgentPanelComponent,
  registerTerminalPanelComponent,
} from "~/components/sections/registry/dynamicPanels.tsx";
import { registerPanelComponent } from "~/components/sections/registry/panelRegistry.ts";

import { ActionsPanelForShell } from "./ActionsPanel.tsx";
import { AgentPanel } from "./AgentPanel.tsx";
import { BrowserPanelForShell } from "./BrowserPanel.tsx";
import { ChangesPanel } from "./ChangesPanel.tsx";
import { CommitsPanel } from "./CommitsPanel.tsx";
import { FilesPanel } from "./FilesPanel.tsx";
import { NotesPanelForShell } from "./NotesPanel.tsx";
import { ReviewAllPanel } from "./ReviewAllPanel.tsx";
import { SkillsPanelForShell } from "./SkillsPanel.tsx";
import { TerminalPanelView } from "./TerminalPanelView.tsx";

registerPanelComponent("files", FilesPanel);
registerPanelComponent("changes", ChangesPanel);
registerPanelComponent("commits", CommitsPanel);
registerPanelComponent("review-all", ReviewAllPanel);
registerPanelComponent("actions", ActionsPanelForShell);
registerPanelComponent("skills", SkillsPanelForShell);
registerPanelComponent("browser", BrowserPanelForShell);
registerPanelComponent("notes", NotesPanelForShell);

// Agent and terminal are multi-instance: their per-instance panel ids are derived in
// dynamicPanels, so they register a base component rather than an id → component pair.
registerAgentPanelComponent(AgentPanel);
registerTerminalPanelComponent(TerminalPanelView);
