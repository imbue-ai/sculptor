import type { ReactElement, ReactNode } from "react";
import { createContext, useContext, useMemo } from "react";

/**
 * The agent + workspace identity a chat panel renders. Provided at the
 * chat panel root and read by every component inside the chat surface.
 *
 * Components inside a chat panel must NOT read the agent from the route
 * (`useWorkspacePageParams`): activating a different center tab does not
 * navigate, and two chat panels can render two different agents at once
 * (e.g. one in the center section and one in the right), so the route's
 * agent routinely differs from the agent a given panel is showing. Reading
 * the route would aim actions (interrupt, queued-message edit/delete) and
 * lookups (PLAN artifact, capability gates) at the wrong agent.
 */
export type ChatAgentIdentity = {
  workspaceId: string;
  agentId: string;
};

const ChatAgentContext = createContext<ChatAgentIdentity | null>(null);

type ChatAgentProviderProps = ChatAgentIdentity & { children: ReactNode };

export const ChatAgentProvider = ({ workspaceId, agentId, children }: ChatAgentProviderProps): ReactElement => {
  const identity = useMemo(() => ({ workspaceId, agentId }), [workspaceId, agentId]);
  return <ChatAgentContext.Provider value={identity}>{children}</ChatAgentContext.Provider>;
};

/**
 * The identity of the chat panel this component renders inside. Throws when no
 * provider is mounted — chat-surface components have no meaningful fallback
 * (falling back to the route is exactly the wrong-agent bug the context
 * exists to prevent).
 */
// eslint-disable-next-line react-refresh/only-export-components -- the hook must live alongside the provider
export const useChatAgent = (): ChatAgentIdentity => {
  const identity = useContext(ChatAgentContext);
  if (identity === null) {
    throw new Error("useChatAgent requires a ChatAgentProvider ancestor (mounted at the chat panel root)");
  }
  return identity;
};
