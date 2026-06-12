import { Flex } from "@radix-ui/themes";
import { useAtom } from "jotai";
import { CopyIcon, TextCursorInput } from "lucide-react";
import type { ReactElement } from "react";
import { useState } from "react";

import { ElementIds } from "~/api";
import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { notesDraftAtomFamily } from "~/common/state/atoms/notesDrafts.ts";
import { usePromptDraft } from "~/common/state/hooks/usePromptDraft.ts";
import { Editor } from "~/components/Editor.tsx";
import { PanelHeader } from "~/components/panels/PanelHeader.tsx";
import { TooltipIconButton } from "~/components/TooltipIconButton.tsx";

import { UndoQueuedMessageDialog } from "../components/UndoQueuedMessageDialog.tsx";
import styles from "./NotesPanel.module.scss";

export const NotesPanel = (): ReactElement => {
  const { workspaceID, agentID: taskID } = useWorkspacePageParams();
  const [notes, setNotes] = useAtom(notesDraftAtomFamily(workspaceID));
  const [promptDraft, setPromptDraft] = usePromptDraft(taskID ?? "");
  const [isConflictOpen, setIsConflictOpen] = useState(false);

  const handleAddToPrompt = (): void => {
    // Mirrors QueuedMessageBar.handleEdit: TipTap serialises empty paragraphs
    // as ZWSP, which String.trim() does not remove.
    const hasRealDraft = !!promptDraft?.replace(/\u200B/g, "").trim();
    if (hasRealDraft) {
      setIsConflictOpen(true);
    } else {
      setPromptDraft(notes);
    }
  };

  const handleCopy = (): void => {
    void navigator.clipboard.writeText(notes);
  };

  return (
    <Flex direction="column" className={styles.panelRoot} data-testid={ElementIds.NOTES_PANEL}>
      <PanelHeader
        title="Notes"
        actions={
          <>
            <TooltipIconButton
              tooltipText="Add notes to prompt"
              onClick={handleAddToPrompt}
              disabled={!notes || !taskID}
            >
              <TextCursorInput size={14} />
            </TooltipIconButton>
            <TooltipIconButton tooltipText="Copy to clipboard" onClick={handleCopy} disabled={!notes}>
              <CopyIcon size={14} />
            </TooltipIconButton>
          </>
        }
      />
      <Editor
        tagName={ElementIds.NOTES_PANEL_EDITOR}
        placeholder="Jot down notes..."
        value={notes}
        onChange={setNotes}
        autoFocus={false}
        wrapperClassName={styles.editorWrapper}
        scrollAreaClassName={styles.scrollArea}
      />
      <UndoQueuedMessageDialog
        isOpen={isConflictOpen}
        title="Add notes to prompt"
        queuedMessageText={notes}
        onOpenChange={setIsConflictOpen}
        onOverwrite={() => {
          setPromptDraft(notes);
          setIsConflictOpen(false);
        }}
        onRemove={() => setIsConflictOpen(false)}
        onKeepQueued={() => setIsConflictOpen(false)}
        removeLabel="Cancel"
        showKeepQueued={false}
      />
    </Flex>
  );
};
