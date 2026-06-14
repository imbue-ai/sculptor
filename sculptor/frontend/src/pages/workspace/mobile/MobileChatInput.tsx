import { DropdownMenu, IconButton } from "@radix-ui/themes";
import { ArrowUp, AtSign, Bot, CirclePlus, Command, Gauge, Image as ImageIcon, Paperclip, Zap } from "lucide-react";
import type { KeyboardEvent, ReactElement } from "react";
import { useCallback, useLayoutEffect, useRef } from "react";

import type { EffortLevel, LlmModel } from "~/api";
import { getModelShortName, PRODUCTION_MODELS } from "~/common/modelConstants.ts";
import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { useDraftAttachedFiles } from "~/common/state/hooks/useDraftAttachedFiles.ts";
import { useTaskChatMessages } from "~/common/state/hooks/useTaskDetail.ts";
import { useTaskSupportsFileAttachments, useTaskSupportsImageInput } from "~/common/state/hooks/useTaskHelpers.ts";
import { useTask } from "~/common/state/hooks/useTaskHelpers.ts";
import { EFFORT_DISPLAY_NAMES, EFFORT_OPTIONS } from "~/components/effortConstants.ts";
import { FileUpload, type FileUploadHandle } from "~/components/FileUpload.tsx";

import styles from "./MobileChatInput.module.scss";
import { useChatMessageSender } from "./useChatMessageSender.ts";

/**
 * MobileChatInput (I1-I4) — a rounded floating input that is purely a new
 * presentation over the shared submit/draft core (`useChatMessageSender`).
 * Bottom-left `+` opens an anchored Radix menu (M2) that also hosts the model
 * and effort selectors (I3 — they live behind the `+`, not as always-visible
 * toolbar controls); the right shows send (idle/active) when not running and
 * stop (square) when the agent is busy (I4).
 */
export const MobileChatInput = ({ taskID }: { taskID: string }): ReactElement => {
  const { workspaceID } = useWorkspacePageParams();
  const task = useTask(taskID);
  const { chatMessages } = useTaskChatMessages(taskID);
  const sender = useChatMessageSender(workspaceID, taskID);
  const { draft, setDraft, isAgentBusy, send, interrupt, canSend } = sender;
  const [attachedFiles, setAttachedFiles] = useDraftAttachedFiles(taskID);
  const canAttachFiles = useTaskSupportsFileAttachments(taskID) ?? true;
  const canUseImageInput = useTaskSupportsImageInput(taskID) ?? true;
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileUploadRef = useRef<FileUploadHandle | null>(null);

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
      <FileUpload
        ref={fileUploadRef}
        files={attachedFiles}
        onFilesChange={setAttachedFiles}
        onError={(toast) => console.error("File attach error:", toast.title, toast.description)}
      />
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
            {/* Radix portals the menu to <body>, outside the shell's .sandTheme
                subtree, so re-apply the sand class on the portaled content. */}
            <DropdownMenu.Content align="start" variant="soft" className="sandTheme">
              {/* Model & effort live behind the + (I3). */}
              <DropdownMenu.Sub>
                <DropdownMenu.SubTrigger>
                  <Bot size={18} /> Model
                  <span className={styles.menuValue}>{getModelShortName(sender.model)}</span>
                </DropdownMenu.SubTrigger>
                <DropdownMenu.SubContent className="sandTheme">
                  <DropdownMenu.RadioGroup
                    value={sender.model}
                    onValueChange={(value) => sender.setModel(value as LlmModel)}
                  >
                    {PRODUCTION_MODELS.map((modelValue) => (
                      <DropdownMenu.RadioItem key={modelValue} value={modelValue}>
                        {getModelShortName(modelValue)}
                      </DropdownMenu.RadioItem>
                    ))}
                  </DropdownMenu.RadioGroup>
                </DropdownMenu.SubContent>
              </DropdownMenu.Sub>

              <DropdownMenu.Sub>
                <DropdownMenu.SubTrigger>
                  <Gauge size={18} /> Effort
                  <span className={styles.menuValue}>{EFFORT_DISPLAY_NAMES[sender.effort]}</span>
                </DropdownMenu.SubTrigger>
                <DropdownMenu.SubContent className="sandTheme">
                  <DropdownMenu.RadioGroup
                    value={sender.effort}
                    onValueChange={(value) => sender.setEffort(value as EffortLevel)}
                  >
                    {EFFORT_OPTIONS.map((level) => (
                      <DropdownMenu.RadioItem key={level} value={level}>
                        {EFFORT_DISPLAY_NAMES[level]}
                      </DropdownMenu.RadioItem>
                    ))}
                  </DropdownMenu.RadioGroup>
                </DropdownMenu.SubContent>
              </DropdownMenu.Sub>

              {sender.supportsFastMode && (
                <DropdownMenu.CheckboxItem
                  checked={sender.isFastMode}
                  onCheckedChange={(checked) => sender.setIsFastMode(checked === true)}
                >
                  <Zap size={18} /> Fast mode
                </DropdownMenu.CheckboxItem>
              )}

              <DropdownMenu.Separator />

              <DropdownMenu.Item onSelect={() => insertTrigger("@")}>
                <AtSign size={18} /> Mention
              </DropdownMenu.Item>
              <DropdownMenu.Item onSelect={() => insertTrigger("/")}>
                <Command size={18} /> Skills &amp; commands
              </DropdownMenu.Item>
              {canAttachFiles && (
                <DropdownMenu.Item onSelect={() => fileUploadRef.current?.triggerUpload()}>
                  <Paperclip size={18} /> Attach files
                </DropdownMenu.Item>
              )}
              {canUseImageInput && (
                <DropdownMenu.Item onSelect={() => fileUploadRef.current?.triggerUpload()}>
                  <ImageIcon size={18} /> Add image
                </DropdownMenu.Item>
              )}
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
