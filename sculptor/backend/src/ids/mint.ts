import { typeid } from "typeid-js";

import {
  type AgentId,
  type AgentMessageId,
  ID_PREFIXES,
  type NotificationId,
  type RepoId,
  type UserSettingsId,
  type WorkspaceId,
} from "~/ids/types";

function mint(prefix: string): string {
  return typeid(prefix).toString();
}

export function newRepoId(): RepoId {
  return mint(ID_PREFIXES.repo) as RepoId;
}

export function newWorkspaceId(): WorkspaceId {
  return mint(ID_PREFIXES.workspace) as WorkspaceId;
}

// New agents always mint `agt_…`; legacy `tsk_…` ids are never minted, only
// preserved.
export function newAgentId(): AgentId {
  return mint(ID_PREFIXES.agent) as AgentId;
}

export function newAgentMessageId(): AgentMessageId {
  return mint(ID_PREFIXES.agentMessage) as AgentMessageId;
}

export function newNotificationId(): NotificationId {
  return mint(ID_PREFIXES.notification) as NotificationId;
}

export function newUserSettingsId(): UserSettingsId {
  return mint(ID_PREFIXES.userSettings) as UserSettingsId;
}
