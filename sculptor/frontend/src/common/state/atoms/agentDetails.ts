import type { PrimitiveAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily } from "jotai/utils";
import isEqual from "lodash/isEqual";

import type {
  ArtifactType,
  AskUserQuestionData,
  ChatMessage,
  SubmittedQuestionAnswers,
  TaskListArtifact,
} from "../../../api";

// The artifacts accumulated for an agent, keyed by artifact type. Lives here beside the
// state that owns it (`AgentDetailState.artifacts`); artifact-sync and the panel data
// hooks import it from this module.
export type ArtifactsMap = {
  [ArtifactType.PLAN]?: TaskListArtifact;
};

/**
 * Complete state for a single agent's detail view.
 * This is accumulated from incremental TaskUpdate messages.
 */
export type AgentDetailState = {
  completedChatMessages: Array<ChatMessage>;
  inProgressChatMessage: ChatMessage | null;
  queuedChatMessages: Array<ChatMessage>;
  workingUserMessageId: string | null;
  artifacts: ArtifactsMap;
  pendingUserQuestion: AskUserQuestionData | null;
  submittedQuestionAnswers: Record<string, SubmittedQuestionAnswers>;
  isInPlanMode: boolean;
  // Background tasks whose ``task_started`` has arrived but whose
  // ``task_notification`` has not. Drives the status pill's
  // "waiting for background task" label so it doesn't claim the agent is
  // thinking while the harness is actually idle (SCU-387).
  pendingBackgroundTaskIds: Array<string>;
  error?: string;
};

export const agentDetailStateAtomFamily = atomFamily<string, PrimitiveAtom<AgentDetailState | null>>(() =>
  atom<AgentDetailState | null>(null),
);

export const getEmptyAgentDetailState = (): AgentDetailState => {
  return {
    completedChatMessages: [],
    inProgressChatMessage: null,
    queuedChatMessages: [],
    workingUserMessageId: null,
    artifacts: {},
    pendingUserQuestion: null,
    submittedQuestionAnswers: {},
    isInPlanMode: false,
    pendingBackgroundTaskIds: [],
  };
};

export const updateAgentDetailStateAtom = atom(
  null,
  (
    getAtom,
    setAtom,
    update: { agentId: string; updater: (prev: AgentDetailState | null) => AgentDetailState | null },
  ): void => {
    const currentState = getAtom(agentDetailStateAtomFamily(update.agentId));
    const newState = update.updater(currentState);
    if (!isEqual(currentState, newState)) {
      setAtom(agentDetailStateAtomFamily(update.agentId), newState);
    }
  },
);

export const agentUpdatedArtifactsAtomFamily = atomFamily<string, PrimitiveAtom<Array<ArtifactType>>>(() =>
  atom<Array<ArtifactType>>([]),
);

export const updateAgentUpdatedArtifactsAtom = atom(
  null,
  (getAtom, setAtom, update: { agentId: string; artifactTypes: Array<ArtifactType> }): void => {
    const existing = getAtom(agentUpdatedArtifactsAtomFamily(update.agentId));
    if (existing.length === 0) {
      setAtom(agentUpdatedArtifactsAtomFamily(update.agentId), Array.from(new Set(update.artifactTypes)));
      return;
    }

    const mergedTypes = Array.from(new Set([...existing, ...update.artifactTypes]));
    setAtom(agentUpdatedArtifactsAtomFamily(update.agentId), mergedTypes);
  },
);

/**
 * Draft state for the AskUserQuestion form.
 *
 * Stored in a separate atom family (keyed by agentId) so that in-progress
 * selections and typed text survive component unmounts caused by navigation.
 */
export type DraftQuestionState = {
  toolUseId: string;
  currentIndex: number;
  answers: Record<string, string>;
  otherTexts: Record<string, string>;
  otherSelected: Record<string, boolean>;
  multiSelections: Record<string, Array<string>>;
};

export const EMPTY_DRAFT_QUESTION_STATE: DraftQuestionState = {
  toolUseId: "",
  currentIndex: 0,
  answers: {},
  otherTexts: {},
  otherSelected: {},
  multiSelections: {},
};

export const draftQuestionStateAtomFamily = atomFamily<string, PrimitiveAtom<DraftQuestionState>>(() =>
  atom<DraftQuestionState>(EMPTY_DRAFT_QUESTION_STATE),
);

export const clearAgentUpdatedArtifactsAtom = atom(
  null,
  (getAtom, setAtom, update: { agentId: string; artifactTypes: Array<ArtifactType> }): void => {
    const existing = getAtom(agentUpdatedArtifactsAtomFamily(update.agentId));
    if (existing.length === 0) {
      return;
    }

    const artifactsToClear = new Set(update.artifactTypes);
    const remaining = existing.filter((artifactType) => !artifactsToClear.has(artifactType));

    if (remaining.length !== existing.length) {
      setAtom(agentUpdatedArtifactsAtomFamily(update.agentId), remaining);
    }
  },
);
