import { Flex, IconButton, Tooltip } from "@radix-ui/themes";
import type { Editor as TipTapEditor } from "@tiptap/react";
import { useAtom, useAtomValue, useSetAtom, useStore } from "jotai";
import { ListChecks, Plus } from "lucide-react";
import { posthog } from "posthog-js";
import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { HTTPException } from "~/common/Errors.ts";
import { isTextBlock } from "~/common/Guards.ts";
import { useTimedLatch } from "~/common/Hooks.ts";
import { useKeybinding, useKeybindingDisplayText } from "~/common/keybindings/hooks.ts";
import { getModelCapabilities } from "~/common/modelCapabilities.ts";
import { type ParsedPseudoSkillCommand, parsePseudoSkillCommand } from "~/common/pseudoSkills.ts";
import { mergeClasses, optional } from "~/common/Utils.ts";
import { CapabilityGate } from "~/components/CapabilityGate.tsx";
import { EffortSelector } from "~/components/EffortSelector.tsx";
import { FastModeToggle } from "~/components/FastModeToggle.tsx";
import { FilePreviewList } from "~/components/FilePreviewList.tsx";
import { processAndValidateFiles, saveFiles } from "~/components/FileUploadUtils.ts";
import { KeyboardHint } from "~/components/KeyboardHint.tsx";
import { ModelSelector } from "~/components/ModelSelector.tsx";
import { SendButton } from "~/components/SendButton.tsx";
import { CAPABILITY_UNSUPPORTED_COPY } from "~/components/useCapabilityGate.ts";

import {
  btwAgent,
  type ChatMessage,
  ChatMessageRole,
  clearWorkspaceAgentContext,
  EffortLevel,
  ElementIds,
  interruptWorkspaceAgent,
  LlmModel,
  type ModelOption,
  sendWorkspaceAgentMessages,
  setWorkspaceAgentModel,
} from "../../../api";
import { CHAT_INPUT_ELEMENT_ID } from "../../../common/Constants.ts";
import { useImbueNavigate, useWorkspacePageParams } from "../../../common/NavigateUtils.ts";
import { shouldHandleKeybinding, useModifiedEnter } from "../../../common/ShortcutUtils.ts";
import { closeBtwPopupAtom, openBtwPopupAtom } from "../../../common/state/atoms/btwPopup.ts";
import type { InsertSkillArg } from "../../../common/state/atoms/chatActions.ts";
import {
  effortAtomFamily,
  fastModeAtomFamily,
  modelAtomFamily,
} from "../../../common/state/atoms/draftAgentSettings.ts";
import { isCancellableAtomFamily } from "../../../common/state/atoms/interruptState.ts";
import { promptDraftAtomFamily } from "../../../common/state/atoms/promptDrafts.ts";
import {
  defaultEffortLevelAtom,
  isAlwaysInterruptAndSendAtom,
  isDefaultFastModeAtom,
  lastUsedModelAtom,
  userConfigAtom,
} from "../../../common/state/atoms/userConfig.ts";
import { useDraftAttachedFiles } from "../../../common/state/hooks/useDraftAttachedFiles.ts";
import { useInterruptAgent } from "../../../common/state/hooks/useInterruptAgent.ts";
import { useTaskDetailWithDefaults } from "../../../common/state/hooks/useTaskDetail";
import {
  useTaskAvailableModels,
  useTaskModel,
  useTaskSelectedModelId,
  useTaskSourcesBackendModels,
  useTaskSupportsContextReset,
  useTaskSupportsFastMode,
  useTaskSupportsFileAttachments,
  useTaskSupportsImageInput,
  useTaskSupportsInteractiveBackchannel,
  useTaskSupportsInterruption,
  useTaskSupportsModelSelection,
} from "../../../common/state/hooks/useTaskHelpers.ts";
import { Editor } from "../../../components/Editor.tsx";
import type { FileUploadHandle } from "../../../components/FileUpload.tsx";
import { FileUpload } from "../../../components/FileUpload.tsx";
import { Toast, type ToastContent, ToastType } from "../../../components/Toast.tsx";
import { TooltipIconButton } from "../../../components/TooltipIconButton.tsx";
import { SettingsSection } from "../../settings/sections.ts";
import { stripHtml } from "../utils/utils.ts";
import styles from "./ChatInput.module.scss";

// Allow extra time for the context-reset round trip, which discards the session.
const CLEAR_CONTEXT_TIMEOUT_MS = 30_000;
// HTTP 409 from `/btw` means there's no live session to fork from yet.
const HTTP_STATUS_CONFLICT = 409;
// Delay before the mention-picker tooltip appears, to avoid flicker on hover.
const MENTION_TOOLTIP_DELAY_MS = 500;

// A normal send resolves in well under a second, so a spinner on every send is
// just noise. Lock the input immediately but only reveal the spinner once a send
// has stayed in flight this long (a slow backend). No trailing min-hold: the
// backend echoes the message over the WebSocket just before the POST resolves,
// so once it's in the chat and the agent is streaming, a lingering spinner only
// distracts — drop it the instant the send completes.
const SEND_SPINNER_START_DELAY_MS = 1_000;

/**
 * Cheap predicate used to decide whether the SendButton / handleSend should
 * bypass the main-busy lock for a `/btw` draft. The authoritative parsing
 * lives in `parsePseudoSkillCommand` but that needs a TipTap editor handle;
 * this string-only version is enough for gating.
 */
function draftIsBypassCommand(draft: string | null | undefined): boolean {
  const trimmed = (draft ?? "").trim();
  if (!trimmed.startsWith("/btw")) {
    return false;
  }
  const rest = trimmed.slice("/btw".length);
  return rest === "" || /^\s/.test(rest);
}

/** The only draft-derived facts the toolbar render needs: whether the send
 *  button is enabled (`hasContent`) and whether the draft is a /btw bypass
 *  command (which can send even while the agent is busy). Tracking these as a
 *  bailout state lets ChatInput avoid re-rendering on every keystroke. */
type DraftFlags = { hasContent: boolean; isBypass: boolean };
const deriveDraftFlags = (draft: string | null): DraftFlags => ({
  hasContent: Boolean(draft?.trim()),
  isBypass: draftIsBypassCommand(draft),
});

type ChatInputProps = {
  isDisabled: boolean;
  isAgentBusy: boolean;
  chatMessages?: Array<ChatMessage>;
  appendTextRef?: React.MutableRefObject<((text: string) => void) | null>;
  insertSkillRef?: React.MutableRefObject<((skill: InsertSkillArg) => void) | null>;
  editorRef?: React.MutableRefObject<TipTapEditor | null>;
  showPromptNavHint?: boolean;
  // The agent + workspace this input drives. Supplied by the owning panel so the
  // input keys its per-agent draft state (model / fast-mode / effort / prompt
  // draft) on the PANEL's agent, not the route's agent. In the section shell the
  // active center tab can differ from the route (switching tabs activates a panel
  // without navigating), so reading the route here would bind the wrong agent and
  // leak one agent's settings into another (effort/fast-mode/model isolation).
  // Falls back to the route params when omitted to keep older callers working.
  taskId?: string;
  workspaceId?: string;
};

export const ChatInput = ({
  isDisabled,
  isAgentBusy,
  chatMessages,
  appendTextRef,
  insertSkillRef,
  editorRef: externalEditorRef,
  showPromptNavHint = false,
  taskId: taskIdProp,
  workspaceId: workspaceIdProp,
}: ChatInputProps): ReactElement => {
  const internalEditorRef = useRef<TipTapEditor | null>(null);
  const editorRef = externalEditorRef ?? internalEditorRef;
  const dragCounterRef = useRef<number>(0);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const { workspaceID: workspaceIDFromRoute, agentID: agentIDFromRoute } = useWorkspacePageParams();
  const taskID = taskIdProp ?? agentIDFromRoute;
  const workspaceID = workspaceIdProp ?? workspaceIDFromRoute;
  const { navigateToGlobalSettings } = useImbueNavigate();
  const taskModel = useTaskModel(taskID ?? "");
  // Harness-supplied model list + selection (pi). hasBackendModelSource
  // distinguishes a pi task from Claude, which falls back to its built-in list
  // and localModel.
  const backendModels = useTaskAvailableModels(taskID ?? "");
  const selectedModelId = useTaskSelectedModelId(taskID ?? "");
  const hasBackendModelSource = useTaskSourcesBackendModels(taskID ?? "");
  const isDefaultFastMode = useAtomValue(isDefaultFastModeAtom);
  const defaultEffortLevel = useAtomValue(defaultEffortLevelAtom);
  const userConfig = useAtomValue(userConfigAtom);
  const [storedModel, setStoredModel] = useAtom(modelAtomFamily(taskID ?? ""));
  const setLastUsedModel = useSetAtom(lastUsedModelAtom);
  const localModel = storedModel ?? (taskModel as LlmModel) ?? LlmModel.CLAUDE_4_OPUS_200K;
  const [isPlanFirst, setIsPlanFirst] = useState<boolean>(false);

  // Per-task fast-mode and effort preference, persisted in localStorage,
  // seeded lazily from the user default once userConfig loads.
  const [isStoredFastMode, setStoredFastMode] = useAtom(fastModeAtomFamily(taskID ?? ""));
  const [storedEffort, setStoredEffort] = useAtom(effortAtomFamily(taskID ?? ""));

  const isFastMode = isStoredFastMode ?? isDefaultFastMode;
  const effort = storedEffort ?? (defaultEffortLevel as EffortLevel) ?? EffortLevel.XHIGH;

  const setIsFastMode = useCallback((value: boolean) => setStoredFastMode(value), [setStoredFastMode]);
  const setEffort = useCallback((value: EffortLevel) => setStoredEffort(value), [setStoredEffort]);

  // Switching the model both updates this task's preference and records the
  // model as the user's most recently used. The MRU value is what new
  // workspaces default to when the "Default model" setting is "Most Recently
  // Used"; without recording it here the MRU default would never reflect the
  // model the user is actually using and would fall back to Fable (SCU-1457).
  const handleModelChange = useCallback(
    (value: LlmModel) => {
      setStoredModel(value);
      setLastUsedModel(value);
    },
    [setStoredModel, setLastUsedModel],
  );

  const [toast, setToast] = useState<ToastContent | null>(null);
  // Mirrored onto the send button as `data-last-send-error` so callers can
  // observe send failures without depending on the toast lifecycle.
  const [lastSendError, setLastSendError] = useState<string | null>(null);
  // True while a message POST is in flight. Drives the send-button spinner and
  // the read-only editor so a slow backend gives visible feedback. The ref is
  // the actual re-entrancy guard: setState is async, so a fast second Enter
  // (or click) would slip past a state-only check and double-queue the message;
  // the ref flips synchronously and is read before any new send proceeds.
  const [isSending, setIsSending] = useState(false);
  const isSendingRef = useRef(false);
  // The lock/read-only state tracks `isSending` directly (instant), but the
  // spinner is gated through a start-delay latch so only slow sends ever show
  // it; the 0 min-hold drops the spinner as soon as the send completes.
  const shouldShowSendSpinner = useTimedLatch(isSending, 0, SEND_SPINNER_START_DELAY_MS);
  const isAlwaysInterruptAndSend = useAtomValue(isAlwaysInterruptAndSendAtom);
  const sendMessageBinding = useKeybinding("send_message");
  const sendHint = useKeybindingDisplayText("send_message");
  const interruptBinding = useKeybinding("interrupt_agent");
  const isCancellable = useAtomValue(isCancellableAtomFamily(taskID ?? ""));
  const {
    interrupt: handleInterrupt,
    toast: interruptToast,
    setToast: setInterruptToast,
  } = useInterruptAgent(workspaceID, taskID);
  // Decoupled from per-keystroke re-render: ChatInput WRITES the draft atom but
  // does not SUBSCRIBE to it (useSetAtom + store reads), so typing the prompt
  // does not re-render this whole toolbar. The send button reads `draftFlags`, a
  // derived state that only changes on empty<->non-empty / bypass-command flips —
  // so a render happens on those flips, not on every keystroke. Reads of the live
  // draft (send, append) go through `getDraft()`.
  const draftAtom = useMemo(() => promptDraftAtomFamily(taskID ?? ""), [taskID]);
  const writeDraftAtom = useSetAtom(draftAtom);
  const draftStore = useStore();
  // Reads the LIVE editor content — authoritative even if a host coalesces
  // onChange; falls back to the persisted atom before the editor mounts.
  const getDraft = useCallback((): string | null => {
    const editor = editorRef.current;
    if (editor) {
      const md = editor.getMarkdown();
      return md === "​" ? "" : md;
    }
    return draftStore.get(draftAtom);
  }, [editorRef, draftStore, draftAtom]);
  // Stable per-task initial content for the editor. The editor is uncontrolled after
  // mount (its value prop doesn't track the atom — that would fight typing);
  // external draft writes reach it via the store subscription below.
  const initialDraft = useMemo(() => draftStore.get(draftAtom) ?? "", [draftStore, draftAtom]);
  const [draftFlags, setDraftFlags] = useState<DraftFlags>(() => deriveDraftFlags(draftStore.get(draftAtom)));
  // The last draft value THIS editor wrote — lets the external-write subscription
  // below tell our own keystrokes apart from EXTERNAL writes without serializing
  // the editor on every keystroke.
  const lastEditorEmitRef = useRef<string | null>(draftStore.get(draftAtom));
  const setPromptDraft = useCallback(
    (value: string | null): void => {
      lastEditorEmitRef.current = value;
      writeDraftAtom(value);
      setDraftFlags((prev) => {
        const next = deriveDraftFlags(value);
        return prev.hasContent === next.hasContent && prev.isBypass === next.isBypass ? prev : next;
      });
    },
    [writeDraftAtom],
  );
  // ChatInput no longer subscribes to the draft atom for renders, so an EXTERNAL
  // write (e.g. QueuedMessages restoring an overwritten draft) would never reach
  // the editor. Subscribe manually and push external writes into the editor
  // imperatively; our own writes (typing) are skipped via lastEditorEmitRef, so a
  // keystroke never triggers a re-serialize or setContent here.
  useEffect(() => {
    return draftStore.sub(draftAtom, () => {
      const next = draftStore.get(draftAtom);
      if (next === lastEditorEmitRef.current) return; // our own write — already in the editor
      lastEditorEmitRef.current = next;
      const editor = editorRef.current;
      if (editor) {
        if (next) {
          editor.commands.setContent(next, { contentType: "markdown" });
        } else {
          editor.commands.clearContent();
        }
      }
      setDraftFlags(deriveDraftFlags(next));
    });
  }, [draftStore, draftAtom, editorRef]);
  // Re-sync the emit ref + bailout flags when the active task (and its persisted
  // draft) changes; this component doesn't subscribe to the atom for renders.
  useEffect(() => {
    lastEditorEmitRef.current = draftStore.get(draftAtom);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- sync flags to the new task's persisted draft on task switch; not derivable during render without subscribing
    setDraftFlags(deriveDraftFlags(draftStore.get(draftAtom)));
  }, [draftAtom, draftStore]);

  // Stable callbacks so the memoized <Toast> instances below bail out instead
  // of re-rendering on every unrelated parent render. (SCU-1455)
  const handleToastOpenChange = useCallback((open: boolean) => {
    if (!open) setToast(null);
  }, []);
  const handleInterruptToastOpenChange = useCallback(
    (open: boolean) => {
      if (!open) setInterruptToast(null);
    },
    [setInterruptToast],
  );
  const [attachedFiles, setAttachedFiles] = useDraftAttachedFiles(taskID ?? "");
  const { isInPlanMode } = useTaskDetailWithDefaults(taskID ?? "");
  // Each gate subscribes only to its own narrow atom so the component
  // re-renders only when that capability changes.
  // `?? true` keeps each affordance visible until the task loads — Claude
  // reports true, pi reports false.
  const canEnterPlanMode = useTaskSupportsInteractiveBackchannel(taskID ?? "") ?? true;
  // Mirrors the StatusPill Stop button: a harness that can't honor a mid-turn
  // interrupt (pi) gets no Ctrl+C keybinding either, rather than a binding that
  // silently no-ops. `?? true` keeps it armed until the task loads.
  const canInterrupt = useTaskSupportsInterruption(taskID ?? "") ?? true;
  const canUseFastMode = useTaskSupportsFastMode(taskID ?? "") ?? true;
  // `/clear` discards the session (context reset). A harness without it refuses
  // the pseudo-skill at execution time instead of calling the endpoint.
  // `?? true` keeps it available until the task loads.
  const canResetContext = useTaskSupportsContextReset(taskID ?? "") ?? true;
  const canHarnessAttachFiles = useTaskSupportsFileAttachments(taskID ?? "") ?? true;
  const canUseImageInput = useTaskSupportsImageInput(taskID ?? "") ?? true;
  // Claude and pi both switch models; harnesses that can't (hello/terminal) get
  // the disabled-with-tooltip switcher. `?? true` keeps it live until the task loads.
  const canSelectModel = useTaskSupportsModelSelection(taskID ?? "") ?? true;
  // The `+` prefilter popover's "Images" category opens the same file
  // picker the toolbar's image button uses. Owning the ref here lets us
  // route both paths through one validated upload pipeline.
  const fileUploadRef = useRef<FileUploadHandle | null>(null);
  const handleTriggerImageUpload = useCallback((): void => {
    if (!canUseImageInput) return;
    fileUploadRef.current?.triggerUpload();
  }, [canUseImageInput]);

  const modelCapabilities = getModelCapabilities(localModel);
  // File attachments are AND-of-both: the model must accept attachments AND
  // the harness must be able to forward them. Image input is independently
  // gated for the +menu's image entry / paste handler.
  const canAttachFiles = modelCapabilities.supportsFileAttachments && canHarnessAttachFiles;

  const clearEditor = useCallback((): void => {
    editorRef.current?.commands.clearContent();
    setPromptDraft(null);
    setAttachedFiles([]);
  }, [editorRef, setPromptDraft, setAttachedFiles]);

  const openBtwPopup = useSetAtom(openBtwPopupAtom);
  const closeBtwPopup = useSetAtom(closeBtwPopupAtom);

  const executePseudoSkill = useCallback(
    async (parsed: ParsedPseudoSkillCommand): Promise<void> => {
      clearEditor();

      switch (parsed.name) {
        case "clear":
          // A harness without context reset (see `canResetContext`) shows the
          // standard copy and does not call the endpoint.
          if (!canResetContext) {
            setToast({ title: CAPABILITY_UNSUPPORTED_COPY, type: ToastType.DEFAULT });
            break;
          }

          try {
            await clearWorkspaceAgentContext({
              path: { workspace_id: workspaceID, agent_id: taskID! },
              meta: { wsTimeout: CLEAR_CONTEXT_TIMEOUT_MS },
            });
          } catch {
            setToast({ title: "Failed to clear context", type: ToastType.ERROR });
          }
          break;

        case "copy": {
          const messages = chatMessages ?? [];
          const assistantMessages = messages.filter((m: ChatMessage) => m.role === ChatMessageRole.ASSISTANT);
          // Find the last assistant message that has text content (skip system-only
          // messages like ContextCleared/ContextSummary blocks).
          let lastAssistantWithText: ChatMessage | undefined;
          for (let i = assistantMessages.length - 1; i >= 0; i--) {
            if (assistantMessages[i].content.some((block) => isTextBlock(block))) {
              lastAssistantWithText = assistantMessages[i];
              break;
            }
          }

          if (!lastAssistantWithText) {
            setToast({ title: "No assistant message to copy", type: ToastType.ERROR });
            return;
          }
          const textBlocks = lastAssistantWithText.content.filter(isTextBlock);
          const text = textBlocks.map((block) => stripHtml(block.text)).join("");
          if (!text) {
            setToast({ title: "No text content to copy", type: ToastType.ERROR });
            return;
          }

          try {
            await navigator.clipboard.writeText(text);
            setToast({ title: "Message copied to clipboard", type: ToastType.SUCCESS });
          } catch {
            setToast({ title: "Failed to copy to clipboard", type: ToastType.ERROR });
          }
          break;
        }

        case "btw": {
          const question = parsed.args.trim();
          if (!question) {
            setToast({ title: "Type a question after /btw", type: ToastType.DEFAULT });
            return;
          }
          const requestId = crypto.randomUUID();
          openBtwPopup({ agentId: taskID!, question, requestId });
          try {
            await btwAgent({
              path: { workspace_id: workspaceID, agent_id: taskID! },
              body: { question, requestId },
            });
          } catch (error) {
            closeBtwPopup();
            const isNoSession =
              typeof error === "object" &&
              error !== null &&
              "status" in error &&
              (error as { status?: number }).status === HTTP_STATUS_CONFLICT;
            setToast({
              title: isNoSession ? "/btw is unavailable until you've sent a message" : "Failed to run /btw",
              type: ToastType.ERROR,
            });
          }
          break;
        }
      }
    },
    [clearEditor, chatMessages, workspaceID, taskID, openBtwPopup, closeBtwPopup, canResetContext],
  );

  const sendMessage = useCallback(async (): Promise<void> => {
    const draft = getDraft();
    if (!draft?.trim() || !taskID) {
      return;
    }

    // Ignore re-entrant sends while a POST is already in flight (e.g. a second
    // Enter on a slow backend) so the same draft can't be queued twice.
    if (isSendingRef.current) {
      return;
    }

    if (editorRef.current) {
      const parsed = parsePseudoSkillCommand(editorRef.current, draft ?? "");
      if (parsed !== null) {
        executePseudoSkill(parsed);
        return;
      }
    }

    isSendingRef.current = true;
    setIsSending(true);
    setLastSendError(null);
    try {
      await sendWorkspaceAgentMessages({
        path: { workspace_id: workspaceID, agent_id: taskID },
        body: {
          message: draft?.replace(/\u200B/g, "\u00A0").replace(/(\n\n\u00A0)+$/, ""),
          model: localModel,
          files: attachedFiles,
          // The plan-mode toggle is gated (disabled-with-tooltip) for harnesses
          // without the interactive backchannel, so `isPlanFirst`/`isInPlanMode`
          // stay false there and these fields are inert; harnesses that support
          // it (Claude, pi) drive plan mode through them.
          enter_plan_mode: isPlanFirst,
          exit_plan_mode: !isPlanFirst && isInPlanMode,
          fast_mode: modelCapabilities.supportsFastMode && isFastMode,
          effort: effort,
        },
      });
      posthog.capture("agent.message_sent", {
        model: localModel,
        is_fast_mode: modelCapabilities.supportsFastMode && isFastMode,
        effort,
        has_attached_files: attachedFiles.length > 0,
        is_plan_first: isPlanFirst,
      });
      // The editor is uncontrolled (stable value prop), so clearing the draft atom
      // alone no longer empties it — clearEditor() also clears the editor content.
      clearEditor();
    } catch (error) {
      console.error("Failed to send message:", error);
      // Editor is intentionally left populated so the user does not lose
      // their typed prompt; the toast tells them why the send failed.
      setLastSendError(error instanceof Error ? error.message : String(error));
      setToast({
        title: "",
        description: (
          <div>
            <b>Failed to send message</b>
            <br />
            <pre>{String(error)}</pre>
          </div>
        ),
        type: ToastType.ERROR,
      });
    } finally {
      isSendingRef.current = false;
      setIsSending(false);
    }
  }, [
    getDraft,
    workspaceID,
    taskID,
    localModel,
    attachedFiles,
    isPlanFirst,
    isInPlanMode,
    isFastMode,
    modelCapabilities,
    effort,
    clearEditor,
    executePseudoSkill,
    setLastSendError,
    editorRef,
  ]);

  const handleSend = useCallback(async (): Promise<void> => {
    // A send is already in flight; ignore the trigger entirely so we neither
    // re-send nor fire the trailing interrupt below for a send that no-ops.
    if (isSendingRef.current) return;
    const isBtwDraft = draftIsBypassCommand(getDraft());
    if (isDisabled && !isBtwDraft) return;
    await sendMessage();

    // Interrupt is a separate call because it's an ephemeral control signal
    // (InterruptProcessUserMessage), not part of the persistent chat message.
    // /btw must never trigger the interrupt — it is dispatched to a forked
    // side-chat subprocess and must not disturb main's flow.
    // Other pseudo-skills (/clear, /copy) keep their existing interrupt
    // behavior on purpose.
    if (!isBtwDraft && isAlwaysInterruptAndSend && isAgentBusy && taskID) {
      await interruptWorkspaceAgent({ path: { workspace_id: workspaceID, agent_id: taskID } });
    }
  }, [isDisabled, getDraft, sendMessage, isAlwaysInterruptAndSend, isAgentBusy, taskID, workspaceID]);

  const handleInterruptAndSend = useCallback(async (): Promise<void> => {
    if (isSendingRef.current) return;
    if (!getDraft()?.trim() || !taskID) return;
    await sendMessage();
    if (isAgentBusy) {
      await interruptWorkspaceAgent({ path: { workspace_id: workspaceID, agent_id: taskID } });
    }
  }, [getDraft, taskID, sendMessage, isAgentBusy, workspaceID]);

  // Out-of-band model switch for a harness with a backend model list (pi). The
  // value stays server-driven (selectedModelId), so on success the persisted
  // current model propagates and the Select updates; on failure the endpoint
  // surfaces pi's error (e.g. "Model not found") and we toast, leaving the
  // selection on the actual current model. The Claude path uses setStoredModel
  // (per-turn) instead and never reaches here.
  const handleBackendModelChange = useCallback(
    async (option: ModelOption): Promise<void> => {
      if (!taskID) return;
      try {
        await setWorkspaceAgentModel({
          path: { workspace_id: workspaceID, agent_id: taskID },
          body: { provider: option.provider, modelId: option.modelId },
        });
      } catch (error) {
        // The endpoint returns a 400 carrying the harness's rejection message
        // (e.g. pi's "Model not found"); surface it so the failure is actionable.
        const detail = error instanceof HTTPException ? error.detail : undefined;
        setToast({ title: `Failed to switch to ${option.displayName}`, description: detail, type: ToastType.ERROR });
      }
    },
    [taskID, workspaceID],
  );

  // The no-providers prompt sends the user to pi settings to authenticate a provider.
  const handleAuthenticate = useCallback((): void => {
    navigateToGlobalSettings(SettingsSection.PI);
  }, [navigateToGlobalSettings]);

  const handleMentionPicker = useCallback((): void => {
    if (!editorRef.current) return;
    const editor = editorRef.current;
    const { from } = editor.state.selection;
    // MentionPickerSuggestion's `allowedPrefixes: [" "]` keeps `1+1`-style
    // math from triggering the popover, but it also means a bare `+` insert
    // at mid-word does nothing. Prepend a space when the char before the
    // cursor isn't whitespace so the click reliably opens the menu.
    const charBefore = from > 1 ? editor.state.doc.textBetween(from - 1, from) : "";
    const isLeadingSpaceNeeded = charBefore !== "" && !/\s/.test(charBefore);
    editor
      .chain()
      .focus()
      .insertContent(isLeadingSpaceNeeded ? " +" : "+")
      .run();
  }, [editorRef]);

  // Scoped to the chat input's focus subtree: a window-level listener that
  // checks document.activeElement so we only consume the key (and only call
  // the API) when the user is actually focused in the chat input. Using the
  // editor's onKeyDown directly was unreliable because TipTap/ProseMirror
  // does not surface every key (notably Escape with no selection) through
  // editorProps.handleKeyDown.
  //
  // The `isCancellable` gate mirrors the alpha StatusPill's Stop button — it
  // fires under exactly the same conditions that render the clickable Stop
  // (broader than `isAgentBusy`, which can lag while `isStreaming` /
  // `promotedMessages.length > 0` are already true).
  useEffect(() => {
    if (interruptBinding == null) return;
    const listener = (e: KeyboardEvent): void => {
      if (!shouldHandleKeybinding(e, interruptBinding)) return;
      if (!canInterrupt || !isCancellable || !taskID) return;
      const chatInputEl = document.getElementById(CHAT_INPUT_ELEMENT_ID);
      if (!chatInputEl?.contains(document.activeElement)) return;
      e.preventDefault();
      e.stopPropagation();
      handleInterrupt();
    };
    window.addEventListener("keydown", listener);
    return (): void => window.removeEventListener("keydown", listener);
  }, [interruptBinding, canInterrupt, isCancellable, taskID, handleInterrupt]);

  const handleKeyPress = useModifiedEnter({
    onConfirm: handleSend,
    onInterruptAndSend: handleInterruptAndSend,
    sendMessageBinding,
  });

  const handleDragEnter = useCallback(
    (event: React.DragEvent): void => {
      event.preventDefault();
      event.stopPropagation();
      if (!canAttachFiles) return;
      dragCounterRef.current += 1;
      if (dragCounterRef.current === 1) {
        setIsDragging(true);
      }
    },
    [canAttachFiles],
  );

  const handleDragOver = useCallback((event: React.DragEvent): void => {
    event.preventDefault();
    event.stopPropagation();
  }, []);

  const handleDragLeave = useCallback((event: React.DragEvent): void => {
    event.preventDefault();
    event.stopPropagation();
    dragCounterRef.current -= 1;
    if (dragCounterRef.current === 0) {
      setIsDragging(false);
    }
  }, []);

  const handleDrop = useCallback(
    async (event: React.DragEvent): Promise<void> => {
      event.preventDefault();
      event.stopPropagation();
      dragCounterRef.current = 0;
      setIsDragging(false);

      if (!canAttachFiles) return;

      const droppedFiles = Array.from(event.dataTransfer.files);
      if (droppedFiles.length === 0) return;

      const { validFiles, errors } = await processAndValidateFiles(droppedFiles);

      if (errors.length > 0) {
        setToast({
          title: "Drop Error",
          description: errors.join("\n"),
          type: ToastType.ERROR,
        });
      }

      if (validFiles.length > 0) {
        const savedFilePaths = await saveFiles(validFiles);
        if (savedFilePaths.length > 0) {
          setAttachedFiles((prev) => [...prev, ...savedFilePaths]);
        } else {
          setToast({ title: "Failed to save dropped files", type: ToastType.ERROR });
        }
      }
    },
    [canAttachFiles, setAttachedFiles],
  );

  useEffect(() => {
    if (!appendTextRef) {
      return;
    }

    appendTextRef.current = (text: string): void => {
      const currentDraft = getDraft() || "";
      const newDraft = currentDraft ? `${currentDraft}\n${text}\n` : `${text}\n`;
      // ChatInput no longer re-renders on draft changes, so push the new content
      // into the editor imperatively (the value prop won't carry it), then mirror
      // it to the draft atom + flags.
      editorRef.current?.commands.setContent(newDraft, { contentType: "markdown" });
      setPromptDraft(newDraft);
      editorRef.current?.commands.focus("end");
    };
  }, [appendTextRef, getDraft, setPromptDraft, editorRef]);

  useEffect(() => {
    if (!insertSkillRef) return;
    insertSkillRef.current = (skill: InsertSkillArg): void => {
      const editor = editorRef.current;
      if (!editor) return;
      editor
        .chain()
        .focus()
        .insertContent([
          {
            type: "mention",
            attrs: {
              id: `/${skill.name}`,
              label: skill.name,
              mentionSuggestionChar: "/",
              skillDescription: skill.description,
              skillType: skill.type,
            },
          },
          { type: "text", text: " " },
        ])
        .run();
    };

    return (): void => {
      insertSkillRef.current = null;
    };
  }, [insertSkillRef, editorRef]);

  // Seed the per-task stored preferences from the user default the first
  // time this task is seen after userConfig has loaded. Once set, user
  // default changes do not retroactively affect tasks that already have a
  // stored value.
  useEffect(() => {
    if (!taskID || userConfig === null) return;

    if (isStoredFastMode === null) {
      setStoredFastMode(isDefaultFastMode);
    }

    if (storedEffort === null) {
      setStoredEffort(defaultEffortLevel as EffortLevel);
    }
  }, [
    taskID,
    userConfig,
    isStoredFastMode,
    storedEffort,
    isDefaultFastMode,
    defaultEffortLevel,
    setStoredFastMode,
    setStoredEffort,
  ]);

  if (!taskID) {
    return <></>;
  }

  return (
    <>
      <div className={styles.container} id={CHAT_INPUT_ELEMENT_ID}>
        <div
          className={mergeClasses(styles.unifiedContainer, optional(isDragging, styles.dragging))}
          onDragEnter={handleDragEnter}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <Editor
            wrapperClassName={styles.editorInner}
            placeholder="Enter a prompt..."
            // Stable initial content (uncontrolled after mount — see initialDraft).
            value={initialDraft}
            // Read-only while a send is in flight: prevents edits from being
            // wiped by the on-success clear, and visually signals "sending".
            disabled={isSending}
            onChange={setPromptDraft}
            onKeyDown={handleKeyPress}
            tagName="CHAT_INPUT"
            editorRef={editorRef}
            onFilesChange={
              canAttachFiles ? (newFiles): void => setAttachedFiles((prev) => [...prev, ...newFiles]) : undefined
            }
            onError={canAttachFiles ? setToast : undefined}
            onTriggerImageUpload={canAttachFiles && canUseImageInput ? handleTriggerImageUpload : undefined}
            key={`chat-input-${taskID}`}
            footer={
              attachedFiles.length > 0 ? (
                <FilePreviewList
                  files={attachedFiles}
                  onRemoveFile={(path) => setAttachedFiles((prev) => prev.filter((curr) => curr !== path))}
                />
              ) : undefined
            }
          />
          <Flex align="center" justify="between" className={styles.toolbar}>
            <Flex align="center" gapX="3">
              <FileUpload
                ref={fileUploadRef}
                files={attachedFiles}
                onFilesChange={setAttachedFiles}
                onError={setToast}
                disabled={!canAttachFiles}
              />
              <TooltipIconButton
                tooltipText="Add a file, skill, or more"
                variant="ghost"
                size="3"
                onClick={handleMentionPicker}
                aria-label="Open mention menu"
                data-testid={ElementIds.MENTION_PICKER_TOOLBAR_BUTTON}
                style={{ color: "var(--accent-10)" }}
                delayDuration={MENTION_TOOLTIP_DELAY_MS}
              >
                <Plus size={16} />
              </TooltipIconButton>
            </Flex>
            {/* Parallel copy of AgentSettingsControls' toolbar block, extended with
                capability-gated disabled states and a backend-model selector this live
                chat needs. Keep the shared tooltip strings, aria-labels, testids, and
                styling in sync with AgentSettingsControls. */}
            <Flex align="center" flexShrink="0">
              <CapabilityGate
                capabilityValue={canEnterPlanMode}
                elementId={ElementIds.CAPABILITY_DISABLED_PLAN_MODE}
                disabledIcon={<ListChecks size={16} />}
                size="3"
                style={{ margin: 0 }}
              >
                <Tooltip content={isPlanFirst || isInPlanMode ? "Leave plan mode" : "Enter plan mode"}>
                  <IconButton
                    variant="ghost"
                    size="3"
                    onClick={() => setIsPlanFirst(!isPlanFirst)}
                    aria-label="Toggle plan first mode"
                    data-testid={ElementIds.PLAN_MODE_TOGGLE}
                    data-active={isPlanFirst || isInPlanMode}
                    style={
                      isPlanFirst || isInPlanMode ? { color: "var(--button-primary-bg)", margin: 0 } : { margin: 0 }
                    }
                  >
                    <ListChecks size={16} />
                  </IconButton>
                </Tooltip>
              </CapabilityGate>
              {modelCapabilities.supportsFastMode && canUseFastMode && (
                <FastModeToggle isActive={isFastMode} onToggle={() => setIsFastMode(!isFastMode)} />
              )}
              <EffortSelector effort={effort} onEffortChange={setEffort} />
              <Flex pr="1">
                <ModelSelector
                  model={localModel}
                  onModelChange={handleModelChange}
                  capabilityValue={canSelectModel}
                  backendModels={backendModels}
                  selectedModelId={selectedModelId}
                  onBackendModelChange={handleBackendModelChange}
                  sourcesBackendModels={hasBackendModelSource}
                  onAuthenticate={handleAuthenticate}
                />
              </Flex>
              <SendButton
                onClick={handleSend}
                disabled={isSending || (isDisabled && !draftFlags.isBypass) || !draftFlags.hasContent}
                loading={shouldShowSendSpinner}
                tooltip={`${sendHint} to send message`}
                ariaLabel="Send message"
                testId={ElementIds.SEND_BUTTON}
                lastSendError={lastSendError}
              />
            </Flex>
          </Flex>
          {isDragging && (
            <div className={styles.dragOverlay}>
              <span className={styles.dragOverlayText}>
                {attachedFiles.length > 0 ? "Drop to attach more images" : "Drop to attach images"}
              </span>
            </div>
          )}
        </div>
        <Flex justify="between" mt="2" gap="3">
          <Flex gap="3" align="center">
            {showPromptNavHint && <KeyboardHint keys="↑↓" label="navigate prompts" />}
          </Flex>
          <KeyboardHint keys={sendHint} label="to send message" />
        </Flex>
      </div>
      <Toast
        open={!!toast}
        onOpenChange={handleToastOpenChange}
        title={toast?.title}
        description={toast?.description}
        type={toast?.type}
      />
      <Toast
        open={!!interruptToast}
        onOpenChange={handleInterruptToastOpenChange}
        title={interruptToast?.title}
        type={interruptToast?.type}
      />
    </>
  );
};
