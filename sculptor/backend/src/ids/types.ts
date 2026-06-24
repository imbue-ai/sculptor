// typeid prefixes, mirroring sculptor/sculptor/primitives/ids.py exactly —
// mismatched prefixes would break wire compatibility and on-disk paths.
// The `repo` table is serialized as `project` on the wire, so its id prefix is
// the Python ProjectID tag `prj`. Agents have a DUAL prefix: existing agents
// keep the legacy `tsk` (the migration preserves them; they appear in URLs,
// on-disk paths, and SCULPTOR_AGENT_ID), while new agents mint `agt`.
export const ID_PREFIXES = {
  repo: "prj",
  workspace: "ws",
  agent: "agt",
  agentLegacy: "tsk",
  agentMessage: "agm",
  notification: "ntf",
  userSettings: "usr",
} as const;

// Both prefixes are accepted for an agent id, indefinitely.
export const AGENT_ID_PREFIXES = [ID_PREFIXES.agent, ID_PREFIXES.agentLegacy] as const;

type Brand<B extends string> = string & { readonly __idBrand: B };

export type RepoId = Brand<"prj">;
export type WorkspaceId = Brand<"ws">;
export type AgentId = Brand<"agt">;
export type AgentMessageId = Brand<"agm">;
export type NotificationId = Brand<"ntf">;
export type UserSettingsId = Brand<"usr">;
