import type { Atom, PrimitiveAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily, selectAtom } from "jotai/utils";
import isEqual from "lodash/isEqual";

import type {
  ArtifactType,
  AskUserQuestionData,
  ChatMessage,
  SubmittedQuestionAnswers,
  WorkflowTaskState,
} from "../../../api";
import type { ArtifactsMap } from "../../../pages/workspace/Types";

/**
 * Complete state for a single task's detail view.
 * This is accumulated from incremental TaskUpdate messages.
 */
export type TaskDetailState = {
  completedChatMessages: Array<ChatMessage>;
  inProgressChatMessage: ChatMessage | null;
  queuedChatMessages: Array<ChatMessage>;
  workingUserMessageId: string | null;
  artifacts: ArtifactsMap;
  pendingUserQuestion: AskUserQuestionData | null;
  submittedQuestionAnswers: Record<string, SubmittedQuestionAnswers>;
  isInPlanMode: boolean;
  // Background tasks whose ``task_started`` has arrived but whose
  // ``task_notification`` has not. Drives the alpha status pill's
  // "waiting for background task" label so it doesn't claim the agent is
  // thinking while the harness is actually idle (SCU-387).
  pendingBackgroundTaskIds: Array<string>;
  // Live/last-known state of Workflow-tool background tasks, keyed by the
  // launching tool_use_id. Drives the Workflow pill's executing state and
  // the workflow popover's phase/agent tree.
  workflowTaskStates: Record<string, WorkflowTaskState>;
  error?: string;
};

export const taskDetailAtomFamily = atomFamily<string, PrimitiveAtom<TaskDetailState | null>>(() =>
  atom<TaskDetailState | null>(null),
);

const EMPTY_WORKFLOW_TASK_STATES: Record<string, WorkflowTaskState> = {};

// Selected with deep equality so pill rows subscribed to workflow state don't
// re-render on every streaming partial — the backend ships the map as a fresh
// object on each TaskUpdate even when its contents are unchanged.
export const workflowTaskStatesAtomFamily = atomFamily<string, Atom<Record<string, WorkflowTaskState>>>((taskId) =>
  selectAtom(
    taskDetailAtomFamily(taskId),
    (detail) => detail?.workflowTaskStates ?? EMPTY_WORKFLOW_TASK_STATES,
    isEqual,
  ),
);

export const getEmptyTaskDetailState = (): TaskDetailState => {
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
    workflowTaskStates: {},
  };
};

export const updateTaskDetailAtom = atom(
  null,
  (
    getAtom,
    setAtom,
    update: { taskId: string; updater: (prev: TaskDetailState | null) => TaskDetailState | null },
  ): void => {
    const currentState = getAtom(taskDetailAtomFamily(update.taskId));
    const newState = update.updater(currentState);
    if (!isEqual(currentState, newState)) {
      setAtom(taskDetailAtomFamily(update.taskId), newState);
    }
  },
);

export const taskUpdatedArtifactsAtomFamily = atomFamily<string, PrimitiveAtom<Array<ArtifactType>>>(() =>
  atom<Array<ArtifactType>>([]),
);

export const updateTaskUpdatedArtifactsAtom = atom(
  null,
  (getAtom, setAtom, update: { taskId: string; artifactTypes: Array<ArtifactType> }): void => {
    const existing = getAtom(taskUpdatedArtifactsAtomFamily(update.taskId));
    if (existing.length === 0) {
      setAtom(taskUpdatedArtifactsAtomFamily(update.taskId), Array.from(new Set(update.artifactTypes)));
      return;
    }

    const mergedTypes = Array.from(new Set([...existing, ...update.artifactTypes]));
    setAtom(taskUpdatedArtifactsAtomFamily(update.taskId), mergedTypes);
  },
);

/**
 * Draft state for the AskUserQuestion form.
 *
 * Stored in a separate atom family (keyed by taskId) so that in-progress
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

export const clearTaskUpdatedArtifactsAtom = atom(
  null,
  (getAtom, setAtom, update: { taskId: string; artifactTypes: Array<ArtifactType> }): void => {
    const existing = getAtom(taskUpdatedArtifactsAtomFamily(update.taskId));
    if (existing.length === 0) {
      return;
    }

    const artifactsToClear = new Set(update.artifactTypes);
    const remaining = existing.filter((artifactType) => !artifactsToClear.has(artifactType));

    if (remaining.length !== existing.length) {
      setAtom(taskUpdatedArtifactsAtomFamily(update.taskId), remaining);
    }
  },
);
