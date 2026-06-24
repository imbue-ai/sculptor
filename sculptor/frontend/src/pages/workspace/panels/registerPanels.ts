// Side-effect barrel that registers each panel's component with the registry at app
// load. Every panel module self-registers on import (registerPanelComponent /
// registerAgentPanelComponent / registerTerminalPanelComponent); importing them here
// once — from the workspace shell — wires the registry so SectionBody can resolve a
// panel's component. Later panel tasks add their modules to this barrel.

import "./AgentPanel.tsx";
