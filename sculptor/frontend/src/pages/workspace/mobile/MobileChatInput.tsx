import { DropdownMenu, IconButton } from "@radix-ui/themes";
import { ArrowUp, AtSign, CirclePlus, Command } from "lucide-react";
import type { KeyboardEvent, ReactElement } from "react";
import { useCallback, useLayoutEffect, useRef } from "react";

import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { useTaskChatMessages } from "~/common/state/hooks/useTaskDetail.ts";
import { useTask } from "~/common/state/hooks/useTaskHelpers.ts";

import styles from "./MobileChatInput.module.scss";
import { useChatMessageSender } from "./useChatMessageSender.ts";

/**
 * MobileChatInput (I1-I4) — a rounded floating input that is purely a new
 * presentation over the shared submit/draft core (`useChatMessageSender`,
 * which composes `usePromptDraft`, the model/fast/effort atoms, the send API,
 * and `useInterruptAgent`). Bottom-left `+` opens an anchored Radix menu (M2);
 * the right shows send (idle/active) when not running and stop (square) when
 * the agent is busy (I4).
 */
export const MobileChatInput = ({ taskID }: { taskID: string }): ReactElement => {
  const { workspaceID } = useWorkspacePageParams();
  const task = useTask(taskID);
  const { chatMessages } = useTaskChatMessages(taskID);
  const { draft, setDraft, isAgentBusy, send, interrupt, canSend } = useChatMessageSender(workspaceID, taskID);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const agentName = task?.titleOrSomethingLikeIt?.trim() || "agent";
  const placeholder = chatMessages.length === 0 ? "Enter a prompt…" : `Reply to ${agentName}…`;

  // Auto-grow the textarea up to its CSS max-height.
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [draft]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>): void => {
      // Cmd/Ctrl+Enter sends (matches desktop); plain Enter inserts a newline,
      // which is the expected mobile behavior.
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        if (canSend) void send();
      }
    },
    [canSend, send],
  );

  const insertTrigger = useCallback(
    (char: string): void => {
      const current = draft ?? "";
      const shouldPrefixSpace = current.length > 0 && !/\s$/.test(current);
      setDraft(`${current}${shouldPrefixSpace ? " " : ""}${char}`);
      textareaRef.current?.focus();
    },
    [draft, setDraft],
  );

  return (
    <div className={styles.inputRegion}>
      <div className={styles.box}>
        <textarea
          ref={textareaRef}
          className={styles.textarea}
          value={draft ?? ""}
          placeholder={placeholder}
          rows={1}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          aria-label={placeholder}
        />
        <div className={styles.row}>
          <DropdownMenu.Root>
            <DropdownMenu.Trigger>
              <IconButton variant="ghost" color="gray" className={styles.plusButton} aria-label="Add context">
                <CirclePlus size={26} />
              </IconButton>
            </DropdownMenu.Trigger>
            <DropdownMenu.Content align="start" variant="soft">
              <DropdownMenu.Item onSelect={() => insertTrigger("@")}>
                <AtSign size={18} /> Mention
              </DropdownMenu.Item>
              <DropdownMenu.Item onSelect={() => insertTrigger("/")}>
                <Command size={18} /> Skills &amp; commands
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Root>

          <div className={styles.spacer} />

          {isAgentBusy ? (
            <IconButton
              variant="ghost"
              radius="full"
              className={styles.stopButton}
              aria-label="Stop agent"
              onClick={() => void interrupt()}
            >
              <span className={styles.stopSquare} />
            </IconButton>
          ) : (
            <IconButton
              variant="ghost"
              radius="full"
              className={`${styles.sendButton} ${canSend ? styles.sendActive : styles.sendIdle}`}
              aria-label="Send message"
              disabled={!canSend}
              onClick={() => void send()}
            >
              <ArrowUp size={20} />
            </IconButton>
          )}
        </div>
      </div>
    </div>
  );
};
