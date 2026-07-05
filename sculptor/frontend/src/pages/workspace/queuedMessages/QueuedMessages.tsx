import { useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useState } from "react";

import type { ChatMessage } from "../../../api";
import { LlmModel, sendWorkspaceAgentMessages } from "../../../api";
import { attachedFilesAtomFamily } from "../../../common/state/atoms/attachedFiles.ts";
import { promptDraftAtomFamily } from "../../../common/state/atoms/promptDrafts.ts";
import { useAgentModel } from "../../../common/state/hooks/useAgentHelpers.ts";
import { useChatAgent } from "../chatAlpha/ChatAgentContext.tsx";
import { type EditConflictData, QueuedMessageBar } from "./QueuedMessageBar.tsx";
import { UndoQueuedMessageDialog } from "./UndoQueuedMessageDialog.tsx";

type QueuedMessagesProps = {
  messages: ReadonlyArray<ChatMessage>;
};

// Renders queued message bars and the undo-edit dialog. The dialog lives here
// (not in QueuedMessageBar) so it survives when a QueuedMessageBar unmounts
// after its message is deleted.
//
// Currently the UI only allows one queued message at a time, but the backend
// supports multiple so we accept an array for forward-compatibility.
export const QueuedMessages = ({ messages }: QueuedMessagesProps): ReactElement => {
  // The owning chat panel's agent — the queued message ids being edited or
  // re-sent belong to it, not to the route's agent.
  const { workspaceId: workspaceID, agentId } = useChatAgent();
  const agentModel = useAgentModel(agentId);
  const [undoDialogData, setUndoDialogData] = useState<EditConflictData | null>(null);

  // Write-only — avoids subscribing to value changes that would cause
  // unnecessary re-renders of the parent component tree.
  const setPromptDraft = useSetAtom(promptDraftAtomFamily(agentId));
  const setAttachedFiles = useSetAtom(attachedFilesAtomFamily(agentId));

  const handleEditConflict = useCallback((data: EditConflictData): void => {
    setUndoDialogData(data);
  }, []);

  const handleUndoOverwrite = useCallback((): void => {
    if (!undoDialogData) return;
    setPromptDraft(undoDialogData.rawTextContent);
    if (undoDialogData.fileSources.length > 0) {
      setAttachedFiles(undoDialogData.fileSources);
    }
    setUndoDialogData(null);
  }, [undoDialogData, setPromptDraft, setAttachedFiles]);

  const handleUndoRemove = useCallback((): void => {
    if (!undoDialogData) return;
    setUndoDialogData(null);
  }, [undoDialogData]);

  const handleUndoCancel = useCallback((): void => {
    if (!undoDialogData) return;
    void sendWorkspaceAgentMessages({
      path: { workspace_id: workspaceID, agent_id: agentId },
      body: {
        message: undoDialogData.rawTextContent,
        model: (agentModel as LlmModel) || LlmModel.CLAUDE_4_OPUS_200K,
        files: undoDialogData.fileSources,
      },
    });
    setUndoDialogData(null);
  }, [undoDialogData, agentId, workspaceID, agentModel]);

  return (
    <>
      {messages.map((queuedChatMessage: ChatMessage) => (
        <QueuedMessageBar key={queuedChatMessage.id} message={queuedChatMessage} onEditConflict={handleEditConflict} />
      ))}
      <UndoQueuedMessageDialog
        isOpen={!!undoDialogData}
        queuedMessageText={undoDialogData?.plainTextContent ?? ""}
        onOpenChange={(open) => !open && setUndoDialogData(null)}
        onOverwrite={handleUndoOverwrite}
        onRemove={handleUndoRemove}
        onKeepQueued={handleUndoCancel}
      />
    </>
  );
};
