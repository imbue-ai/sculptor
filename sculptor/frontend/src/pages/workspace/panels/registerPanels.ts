// Side-effect barrel that registers each panel's component with the registry at app
// load. Every panel module self-registers on import (registerPanelComponent /
// registerAgentPanelComponent / registerTerminalPanelComponent); importing them here
// once — from the workspace shell — wires the registry so SectionBody can resolve a
// panel's component. Later panel tasks add their modules to this barrel.

import "./ActionsPanel.tsx";
import "./AgentPanel.tsx";
import "./BrowserPanel.tsx";
import "./ChangesPanel.tsx";
import "./CommitsPanel.tsx";
import "./FilesPanel.tsx";
import "./NotesPanel.tsx";
import "./ReviewAllPanel.tsx";
import "./SkillsPanel.tsx";
import "./TerminalPanelView.tsx";
