// Opaque string identifiers used across the state layer. `AgentID` identifies
// one coding-agent run — the wire still calls it a task (`taskId` on generated
// types), but that vocabulary stays at the API seam.
export type RequestID = string;
export type AgentID = string;
export type ProjectID = string;
