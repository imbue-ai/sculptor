import { Flex } from "@radix-ui/themes";
import type { Editor as TipTapEditor } from "@tiptap/react";
import { useAtomValue, useSetAtom } from "jotai";
import { posthog } from "posthog-js";
import type { ReactElement } from "react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";

import {
  answerWorkspaceAgentQuestion,
  ChatMessageRole,
  ElementIds,
  interruptWorkspaceAgent,
  LlmModel,
  sendWorkspaceAgentMessages,
  TaskStatus,
} from "~/api";
import { useIsMobile } from "~/common/hooks/useLayoutMode.ts";
import type { InsertSkillArg } from "~/common/state/atoms/chatActions.ts";
import { chatSearchVisibleAtom } from "~/common/state/atoms/chatSearch.ts";
import { AgentLightboxProvider } from "~/components/AgentLightboxContext.tsx";
import { useRegisterCommandAction } from "~/components/CommandPalette/commandActions.ts";
import { Toast, type ToastContent, ToastType } from "~/components/Toast.tsx";
import { VerticalOverlayScrollbar } from "~/components/VerticalOverlayScrollbar.tsx";
import { isModifierPressed } from "~/electron/utils.ts";
import { buildSubagentMetadataMap, buildSubagentTree } from "~/pages/workspace/utils/subagentTree.ts";

import { AskUserQuestion } from "../AskUserQuestion";
import { ChatInput } from "../ChatInput";
import { openDiffTabAtom } from "../diffPanel/atoms.ts";
import { ErrorInput } from "../ErrorInput.tsx";
import { QueuedMessages } from "../QueuedMessages.tsx";
import type { ChatData } from "../useChatData.ts";
import styles from "./AlphaChatInterface.module.scss";
import { AlphaChatIntro } from "./AlphaChatIntro.tsx";
import { AlphaMessageNode } from "./AlphaChatView.tsx";
import {
  buildToolResultMap,
  filterRenderableNodes,
  mergeChatAndQueuedMessages,
  omitMessagesAlreadyInChat,
} from "./alphaMessageUtils.ts";
import { AlphaPromptNavigator } from "./AlphaPromptNavigator.tsx";
import { AlphaSearchBar } from "./AlphaSearchBar.tsx";
import { chatToolDensityAtom } from "./atoms.ts";
import { ChatContextMenu } from "./ChatContextMenu.tsx";
import { useChatTask } from "./ChatTaskContext.tsx";
import { useAlphaActivePromptIndex } from "./hooks/useAlphaActivePromptIndex.ts";
import { useAlphaAutoScroll } from "./hooks/useAlphaAutoScroll.ts";
import { useAlphaPromptNav } from "./hooks/useAlphaPromptNav.ts";
import { useAlphaScrollPersistence } from "./hooks/useAlphaScrollPersistence.ts";
import { useAlphaSearch } from "./hooks/useAlphaSearch.ts";
import { useAlphaVirtualizer } from "./hooks/useAlphaVirtualizer.ts";
import { ChatScrollProvider } from "./hooks/useChatScroll.tsx";
import { useJumpToBottom } from "./hooks/useJumpToBottom.ts";
import { JumpToBottomButton } from "./JumpToBottomButton.tsx";
import { useScrollStateMachine } from "./scroll/useScrollStateMachine.ts";
import { StatusPill } from "./StatusPill.tsx";

type AlphaChatInterfaceProps = ChatData & {
  appendTextRef?: React.MutableRefObject<((text: string) => void) | null>;
  insertSkillRef?: React.MutableRefObject<((skill: InsertSkillArg) => void) | null>;
  editorRef?: React.MutableRefObject<TipTapEditor | null>;
};

export const AlphaChatInterface = ({
  appendTextRef,
  insertSkillRef,
  editorRef,
  chatMessages,
  smoothInProgressChatMessage,
  isStreaming,
  workingUserMessageId,
  queuedChatMessages,
  taskStatus,
  taskModel,
  isAutoCompacting,
  pendingUserQuestion,
  pendingBackgroundTaskCount,
  bottomSentinelRef,
}: AlphaChatInterfaceProps): ReactElement => {
  // The PANEL's agent identity, seeded by ChatPanelContent — never the route's.
  const { workspaceId: workspaceID, taskId: taskID } = useChatTask();
  const [toast, setToast] = useState<ToastContent | null>(null);
  // Stable callback so the memoized <Toast> below bails out instead of
  // re-rendering on every unrelated parent render. (SCU-1455)
  const handleToastOpenChange = useCallback((open: boolean) => {
    if (!open) setToast(null);
  }, []);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Queued message promotion logic. The agent holds queued messages whenever
  // it is mid-turn — either actively running, or paused on an AskUserQuestion /
  // ExitPlanMode panel waiting for the user (`pendingUserQuestion`). A pending
  // question flips the derived task status to WAITING (see
  // web/derived.py:_ready_or_waiting) with `workingUserMessageId` no longer
  // tracking a live turn, so without the `pendingUserQuestion` arm a message
  // queued while the agent was running would be flushed into the transcript as
  // an already-sent message the moment the question panel appeared (SCU-1319).
  // This arm cannot change ChatInput's behaviour: ChatInput only renders when
  // `pendingUserQuestion` is null (see below), so the value it sees is unchanged.
  const isAgentBusy =
    (taskStatus === TaskStatus.RUNNING && workingUserMessageId !== null) || pendingUserQuestion !== null;
  const isMobile = useIsMobile();
  const effectiveQueuedMessages = useMemo(
    () => (isAgentBusy ? omitMessagesAlreadyInChat(queuedChatMessages, chatMessages) : []),
    [chatMessages, isAgentBusy, queuedChatMessages],
  );

  const effectiveChatMessages = useMemo(
    () => mergeChatAndQueuedMessages(chatMessages, isAgentBusy ? [] : queuedChatMessages),
    [chatMessages, isAgentBusy, queuedChatMessages],
  );

  // Build message tree and filter out tool-result-only messages
  const messageTree = useMemo(() => buildSubagentTree(effectiveChatMessages), [effectiveChatMessages]);
  const toolResultMap = useMemo(() => buildToolResultMap(effectiveChatMessages), [effectiveChatMessages]);
  const subagentMetadataMap = useMemo(
    () =>
      buildSubagentMetadataMap(
        effectiveChatMessages as unknown as Array<{ content: Array<{ type?: string; [key: string]: unknown }> }>,
      ),
    [effectiveChatMessages],
  );

  const filteredNodes = useMemo(() => filterRenderableNodes(messageTree), [messageTree]);

  // Build a map from filtered index to the previous filtered node (for isNewCycle detection)
  const prevNodeMap = useMemo(() => {
    const map = new Map<number, (typeof filteredNodes)[0]>();
    for (let i = 1; i < filteredNodes.length; i++) {
      map.set(i, filteredNodes[i - 1]);
    }
    return map;
  }, [filteredNodes]);

  const lastMessageRole = filteredNodes.length > 0 ? filteredNodes[filteredNodes.length - 1].message.role : null;

  // Index of the most recent user message.  Used by scroll-to-top so it
  // fires even when user + assistant messages arrive in the same React
  // render batch (where lastMessageRole would be ASSISTANT).
  const lastUserMessageIndex = useMemo(() => {
    for (let i = filteredNodes.length - 1; i >= 0; i--) {
      if (filteredNodes[i].message.role === ChatMessageRole.USER) return i;
    }
    return -1;
  }, [filteredNodes]);

  // Measure the intro block height so the virtualizer's paddingStart can
  // reserve exactly that much space.  Without this, the first virtual item
  // (absolutely positioned at translateY(paddingStart)) would overlap the
  // intro text, which lives in normal document flow above the items.
  //
  // useLayoutEffect for the initial read: the height must be available
  // before the first paint so paddingStart is correct on mount and avoids
  // a 0→real transition that shifts virtual items and causes scroll drift
  // during task switches.  ResizeObserver in a regular useEffect handles
  // subsequent size changes (e.g. viewport resize).
  const introRef = useRef<HTMLDivElement>(null);
  const [introHeight, setIntroHeight] = useState(0);
  useLayoutEffect(() => {
    const el = introRef.current;
    if (el) setIntroHeight(el.offsetHeight);
  }, []);
  useEffect(() => {
    const el = introRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => setIntroHeight(el.offsetHeight));
    observer.observe(el);
    return (): void => observer.disconnect();
  }, []);

  // Set true before any programmatic scroll of the chat container so
  // ChatScrollProvider doesn't dismiss popovers on it. Cleared by
  // useAlphaAutoScroll.handleScroll after it consumes the scroll event.
  const isProgrammaticScrollRef = useRef(false);

  // Single owner of scroll state (authority + layout settle + suppression).
  // Declared before the scroll hooks so its attach layout effect runs first and
  // so they can dispatch into / read from it.
  const scrollMachine = useScrollStateMachine(scrollContainerRef);

  const virtualizer = useAlphaVirtualizer(
    scrollContainerRef,
    filteredNodes.length,
    lastMessageRole,
    taskID,
    scrollMachine,
    introHeight,
    isProgrammaticScrollRef,
    isStreaming,
  );

  const density = useAtomValue(chatToolDensityAtom);

  const inProgressMessageId = smoothInProgressChatMessage?.id ?? null;

  // Auto-scroll: follows streaming output, disengages on user scroll away
  const { isAtBottom, scrollToBottom, setIsSuppressed, isJumpSuppressed, isUserScrollingRef } = useAlphaAutoScroll(
    scrollContainerRef,
    isStreaming,
    filteredNodes.length,
    virtualizer,
    lastMessageRole,
    lastUserMessageIndex,
    taskID,
    scrollMachine,
    isProgrammaticScrollRef,
  );

  // Scroll position persistence per task
  const filteredMessageRefs = useMemo(() => filteredNodes.map((n) => ({ id: n.message.id })), [filteredNodes]);
  useAlphaScrollPersistence(scrollContainerRef, virtualizer, taskID, filteredMessageRefs, scrollMachine);

  // Prompt navigation: ArrowUp/Down to cycle through user prompts
  const filteredChatMessages = useMemo(() => filteredNodes.map((n) => n.message), [filteredNodes]);

  // Pre-compute user prompt indices so the scroll-spy and nav hook can share
  // the same "active prompt" cursor.
  const userPromptIndices = useMemo(
    () =>
      filteredChatMessages.reduce<Array<number>>((acc, msg, idx) => {
        if (msg.role === ChatMessageRole.USER) acc.push(idx);
        return acc;
      }, []),
    [filteredChatMessages],
  );

  // User message objects for the dot rail tooltip previews.
  const userMessages = useMemo(
    () => filteredNodes.filter((n) => n.message.role === ChatMessageRole.USER).map((n) => n.message),
    [filteredNodes],
  );

  // Active dot index (scroll-spy) — shared with keyboard nav as the single
  // cursor. Reads the `navigating` phase off the shared scroll machine so the
  // scroll spy and stick-to-bottom logic don't fight the explicit user intent.
  const activePromptIndex = useAlphaActivePromptIndex(
    userPromptIndices,
    virtualizer,
    scrollContainerRef,
    isAtBottom,
    scrollMachine,
  );

  // ─── Anchor the active user message during chat tool density flips ──────────
  //
  // Toggling density resizes every tool-bearing message at once. The
  // virtualizer's built-in compensation only kicks in for items entirely
  // above the viewport, so items that span / are below the viewport top
  // still cause the message the user is reading to slide tens of pixels.
  //
  // We pin the prompt-navigator's active user message by working with the
  // virtualizer's `measurementsCache` directly (its source of truth for
  // virtual positions), not getBoundingClientRect — that avoids races
  // between React commit, virtualizer state, and the actual DOM layout.
  //
  //   pre-flip:  viewport_y(anchor) = oldStart - oldScrollTop
  //   want:      viewport_y(anchor) stays the same
  //   so:        newScrollTop = oldScrollTop + (newStart - oldStart)
  //
  // Capture during render (DOM/virtualizer state is still pre-flip), then
  // in a useLayoutEffect after commit, force the virtualizer to remeasure
  // synchronously and assign scrollTop *absolutely* (overrides whatever the
  // virtualizer's auto-compensation might also have adjusted).
  const prevDensityRef = useRef(density);

  useLayoutEffect(() => {
    if (prevDensityRef.current === density) return;
    prevDensityRef.current = density;
    const container = scrollContainerRef.current;
    if (!container) return;

    // Capture the anchor *before* remeasuring below. This layout effect runs
    // after the new-density DOM commits but before the manual remeasure, so the
    // virtualizer's measurementsCache and the container's scrollTop still hold
    // their pre-flip values here.
    let captured: { msgIdx: number; oldStart: number; oldScrollTop: number } | null = null;
    const msgIdx = userPromptIndices[activePromptIndex.index];
    const oldStart = msgIdx !== undefined ? virtualizer.measurementsCache[msgIdx]?.start : undefined;
    if (msgIdx !== undefined && oldStart != null) {
      captured = { msgIdx, oldStart, oldScrollTop: container.scrollTop };
    }

    // Each chat message wrapper carries `ref={virtualizer.measureElement}`,
    // but its identity is preserved across density flips, so the
    // virtualizer would only see the size change via the async
    // ResizeObserver path — too late to settle inside this commit.
    // Manually invoke measureElement on every visible wrapper to update
    // itemSizeCache synchronously, then call getVirtualItems() to force
    // the memoized cumulative-position calculation to rebuild
    // measurementsCache from the new sizes.
    flushSync(() => {
      container.querySelectorAll<HTMLElement>("[data-index]").forEach((el) => {
        virtualizer.measureElement(el);
      });
    });
    virtualizer.getVirtualItems();

    if (!captured) return;
    const newStart = virtualizer.measurementsCache[captured.msgIdx]?.start;
    if (newStart == null) return;
    const newScrollTop = captured.oldScrollTop + (newStart - captured.oldStart);

    // The virtual-content div's `height` style is set from
    // `virtualizer.getTotalSize()` during render, but that render runs
    // before measureElement updates the cache — so even after flushSync's
    // cascading re-render commits, scrollTop's clamping sometimes still
    // sees the stale (pre-flip) scrollHeight and pins our target down.
    // Set the height directly here so scrollTop lands where we want;
    // React will re-apply the same value on its next render.
    const totalSize = virtualizer.getTotalSize();
    const virtualContent = container.firstElementChild as HTMLElement | null;
    if (virtualContent) {
      virtualContent.style.height = `${totalSize}px`;
    }
    container.scrollTop = newScrollTop;
    // userPromptIndices / activePromptIndex are intentionally read at the
    // density flip only; the effect early-returns on every other render, so
    // re-running when they change would be wasted work.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [density, virtualizer]);

  const { exitNavigation, navigateToPrompt } = useAlphaPromptNav(
    filteredChatMessages,
    virtualizer,
    scrollToBottom,
    setIsSuppressed,
    activePromptIndex,
    scrollMachine,
  );

  const handlePromptNavigate = useCallback(
    (promptIndex: number): void => {
      navigateToPrompt(promptIndex);
    },
    [navigateToPrompt],
  );

  // In-chat search
  const {
    matches: searchMatches,
    activeMatch,
    totalMatchCount,
    activeIndex: searchActiveIndex,
    navigateToMatch,
    isSearchVisible,
    query: searchQuery,
  } = useAlphaSearch(filteredChatMessages, virtualizer);

  // The search query to pass to message nodes for highlighting
  const effectiveSearchQuery = isSearchVisible && searchQuery ? searchQuery : undefined;
  const activeMatchMessageId = activeMatch?.messageId ?? null;

  // Compute which content block and occurrence within that block is active.
  // Each text block in a message gets its own AlphaMarkdownBlock that resets
  // its highlight counter, so we need a per-block index rather than a
  // per-message index.
  const activeBlockIndex = activeMatch?.blockIndex ?? -1;
  const activeOccurrenceInBlock = useMemo(() => {
    if (!activeMatch) return -1;
    let count = 0;
    for (let i = 0; i < searchActiveIndex; i++) {
      if (
        searchMatches[i].messageId === activeMatch.messageId &&
        searchMatches[i].blockIndex === activeMatch.blockIndex
      ) {
        count++;
      }
    }
    return count;
  }, [searchMatches, searchActiveIndex, activeMatch]);

  // Close search on task switch
  const setSearchVisible = useSetAtom(chatSearchVisibleAtom);
  useEffect(() => {
    setSearchVisible(false);
  }, [taskID, setSearchVisible]);

  // Suppress auto-scroll while search is open so streaming doesn't fight with
  // search navigation. Exit prompt navigation when search opens (it has its own
  // suppression that we supersede here).
  useEffect(() => {
    // The machine's top-level suppression guard drops auto-scroll initiation
    // events while search is open, so a search session never starts pinning or
    // anchoring.
    scrollMachine.setSuppressed(isSearchVisible);
    if (isSearchVisible) {
      exitNavigation();
      setIsSuppressed(true);
    } else {
      setIsSuppressed(false);
    }
  }, [isSearchVisible, exitNavigation, setIsSuppressed, scrollMachine]);

  // Jump-to-bottom button
  const { isVisible: isJumpVisible, label: jumpLabel } = useJumpToBottom(
    isAtBottom,
    effectiveChatMessages,
    isStreaming,
    isJumpSuppressed,
  );

  // Global Cmd+Shift+Enter handler: interrupt and send the queued message.
  // Mirror the latest "has queued messages" flag into a ref so the keydown
  // handler below reads the current value without re-subscribing the listener.
  const hasQueuedMessagesRef = useRef(effectiveQueuedMessages.length > 0);
  useEffect(() => {
    hasQueuedMessagesRef.current = effectiveQueuedMessages.length > 0;
  });

  useEffect(() => {
    if (!taskID) return;

    const handleGlobalInterruptAndSend = (e: KeyboardEvent): void => {
      if (!hasQueuedMessagesRef.current) return;
      if (e.key === "Enter" && e.shiftKey && isModifierPressed(e)) {
        e.preventDefault();
        void interruptWorkspaceAgent({ path: { workspace_id: workspaceID, agent_id: taskID } });
      }
    };

    window.addEventListener("keydown", handleGlobalInterruptAndSend);
    return (): void => window.removeEventListener("keydown", handleGlobalInterruptAndSend);
  }, [taskID, workspaceID]);

  // Expose the jump-to-bottom callback to the command palette so Cmd+K →
  // Jump to bottom invokes it directly instead of synthesizing a key event.
  const handleJumpToBottom = useCallback((): void => {
    exitNavigation();
    scrollToBottom();
  }, [exitNavigation, scrollToBottom]);
  useRegisterCommandAction("chat.jumpToBottom", handleJumpToBottom);

  const handleRetryLastUserMessage = useCallback(async (): Promise<void> => {
    const userMessages = chatMessages.filter((msg) => msg.role === ChatMessageRole.USER);
    const lastUserMsg = userMessages[userMessages.length - 1];
    if (!lastUserMsg || !taskID) return;

    const messageText = lastUserMsg.content
      .filter((block) => block.type === "text")
      .map((block) => block.text)
      .join("");

    if (messageText) {
      try {
        await sendWorkspaceAgentMessages({
          path: { workspace_id: workspaceID, agent_id: taskID },
          body: { message: messageText, model: (taskModel as LlmModel) || LlmModel.CLAUDE_4_OPUS_200K },
        });
        posthog.capture("agent.message_retried", {
          workspace_id: workspaceID,
          agent_id: taskID,
        });
      } catch (error) {
        console.error("Failed to retry message:", error);
        setToast({ title: "Failed to retry message", type: ToastType.ERROR });
      }
    }
  }, [chatMessages, taskID, taskModel, workspaceID]);

  const openDiffTab = useSetAtom(openDiffTabAtom);
  const handleOpenDiffFile = useCallback(
    (filePath: string): void => {
      openDiffTab({ workspaceId: workspaceID, filePath, status: "M" });
    },
    [workspaceID, openDiffTab],
  );

  const submitAnswersToBackend = useCallback(
    async (answers: Record<string, string>, notes: Record<string, string>): Promise<void> => {
      if (!pendingUserQuestion || !taskID) return;
      try {
        await answerWorkspaceAgentQuestion({
          path: { workspace_id: workspaceID, agent_id: taskID },
          body: {
            answers,
            notes,
            questionData: pendingUserQuestion,
            toolUseId: pendingUserQuestion.toolUseId,
            model: (taskModel as LlmModel) || LlmModel.CLAUDE_4_OPUS_200K,
          },
        });
      } catch (error) {
        console.error("Failed to submit answers:", error);
        setToast({ title: "Failed to submit answers", type: ToastType.ERROR });
      }
    },
    [pendingUserQuestion, taskID, taskModel, workspaceID],
  );

  const handleSubmitAnswers = useCallback(
    async (answers: Record<string, string>, notes: Record<string, string> = {}): Promise<void> => {
      if (!pendingUserQuestion || !taskID) return;
      posthog.capture("agent.question_answered", {
        workspace_id: workspaceID,
        agent_id: taskID,
        question_count: pendingUserQuestion.questions.length,
      });
      await submitAnswersToBackend(answers, notes);
    },
    [submitAnswersToBackend, pendingUserQuestion, taskID, workspaceID],
  );

  const handleDismissQuestion = useCallback(async (): Promise<void> => {
    if (!pendingUserQuestion || !taskID) return;
    const dismissedAnswers: Record<string, string> = {};
    for (const question of pendingUserQuestion.questions) {
      dismissedAnswers[question.question] = "[Dismissed]";
    }
    posthog.capture("agent.question_dismissed", {
      workspace_id: workspaceID,
      agent_id: taskID,
      question_count: pendingUserQuestion.questions.length,
    });
    await submitAnswersToBackend(dismissedAnswers, {});
  }, [submitAnswersToBackend, pendingUserQuestion, taskID, workspaceID]);

  return (
    <AgentLightboxProvider taskId={taskID}>
      <ChatScrollProvider scrollContainerRef={scrollContainerRef} isUserScrollingRef={isUserScrollingRef}>
        <Flex
          direction="column"
          className={styles.container}
          width="100%"
          position="relative"
          data-testid={ElementIds.CHAT_PANEL}
          data-taskid={taskID}
        >
          {isSearchVisible && (
            <AlphaSearchBar
              totalMatchCount={totalMatchCount}
              activeIndex={searchActiveIndex}
              navigateToMatch={navigateToMatch}
            />
          )}
          <ChatContextMenu>
            <div className={styles.scrollArea}>
              <div
                ref={scrollContainerRef}
                className={styles.scrollContainer}
                data-testid={ElementIds.ALPHA_CHAT_VIEW}
                role="log"
                aria-label="Chat messages"
                tabIndex={0}
              >
                <div className={styles.virtualContent} style={{ height: virtualizer.getTotalSize() }}>
                  <div ref={introRef}>
                    <AlphaChatIntro />
                  </div>
                  {virtualizer.getVirtualItems().map((virtualItem) => {
                    const node = filteredNodes[virtualItem.index];
                    const prevNode = prevNodeMap.get(virtualItem.index);
                    const isLastMessage = virtualItem.index === filteredNodes.length - 1;
                    const isAssistant = node.message.role === ChatMessageRole.ASSISTANT;
                    return (
                      <div
                        key={node.message.id}
                        ref={virtualizer.measureElement}
                        data-index={virtualItem.index}
                        aria-setsize={filteredNodes.length}
                        aria-posinset={virtualItem.index + 1}
                        aria-live={isLastMessage && isAssistant ? "polite" : undefined}
                        style={{
                          position: "absolute",
                          top: 0,
                          left: 0,
                          width: "100%",
                          transform: `translateY(${virtualItem.start}px)`,
                        }}
                      >
                        <AlphaMessageNode
                          node={node}
                          prevNode={prevNode}
                          inProgressMessageId={inProgressMessageId}
                          toolResultMap={toolResultMap}
                          subagentMetadataMap={subagentMetadataMap}
                          searchQuery={effectiveSearchQuery}
                          activeSearchBlockIndex={activeMatchMessageId === node.message.id ? activeBlockIndex : -1}
                          activeSearchOccurrence={
                            activeMatchMessageId === node.message.id ? activeOccurrenceInBlock : -1
                          }
                          isLastMessage={virtualItem.index === filteredNodes.length - 1}
                          isStreaming={isStreaming && isLastMessage && isAssistant}
                          taskStatus={taskStatus ?? TaskStatus.RUNNING}
                          onRetryRequest={handleRetryLastUserMessage}
                          onOpenDiffFile={handleOpenDiffFile}
                          messageIndex={virtualItem.index}
                        />
                      </div>
                    );
                  })}
                  {/* Bottom sentinel for the smooth-streaming viewport observer.
                    useSmoothStreamingViewportObserver watches this element with
                    an IntersectionObserver and disables smooth streaming when
                    it scrolls off-screen. It is pinned to the bottom of the
                    virtual content so it leaves the viewport exactly when the
                    message tail does. */}
                  <div
                    ref={bottomSentinelRef}
                    data-testid={ElementIds.ALPHA_CHAT_BOTTOM_SENTINEL}
                    aria-hidden="true"
                    className={styles.bottomSentinel}
                  />
                </div>
              </div>
              <div className={styles.bottomBar}>
                <JumpToBottomButton
                  isVisible={isJumpVisible}
                  label={jumpLabel}
                  onClick={(): void => {
                    exitNavigation();
                    scrollToBottom();
                  }}
                  scrollContainerRef={scrollContainerRef}
                />
                <StatusPill
                  taskStatus={taskStatus ?? null}
                  isAutoCompacting={isAutoCompacting}
                  isStreaming={isStreaming}
                  inProgressChatMessage={smoothInProgressChatMessage}
                  workingUserMessageId={workingUserMessageId}
                  pendingBackgroundTaskCount={pendingBackgroundTaskCount}
                />
              </div>
              <VerticalOverlayScrollbar
                scrollRef={scrollContainerRef}
                thumbTestId={ElementIds.ALPHA_CHAT_SCROLLBAR_THUMB}
              />
            </div>
          </ChatContextMenu>
          {/* The prompt-navigator rail is a desktop-only companion to the input
              (↑↓ keyboard nav); mobile has no hardware arrows, so it's hidden
              there. The queued-messages strip shows on both. */}
          {!isMobile && (
            <AlphaPromptNavigator
              userMessages={userMessages}
              scrollContainerRef={scrollContainerRef}
              activePromptIndex={activePromptIndex.index}
              onNavigate={handlePromptNavigate}
            />
          )}
          <QueuedMessages messages={effectiveQueuedMessages} />
          {taskStatus !== TaskStatus.ERROR &&
            (pendingUserQuestion ? (
              <AskUserQuestion
                key={pendingUserQuestion.toolUseId}
                taskId={taskID}
                questionData={pendingUserQuestion}
                onSubmit={handleSubmitAnswers}
                onDismiss={handleDismissQuestion}
              />
            ) : (
              <ChatInput
                isDisabled={effectiveQueuedMessages.length > 0}
                isAgentBusy={isAgentBusy}
                chatMessages={effectiveChatMessages}
                appendTextRef={appendTextRef}
                insertSkillRef={insertSkillRef}
                editorRef={editorRef}
                taskId={taskID}
                workspaceId={workspaceID}
                showPromptNavHint={!isMobile}
              />
            ))}
          {taskStatus === TaskStatus.ERROR && <ErrorInput workspaceId={workspaceID} taskId={taskID} />}
        </Flex>
      </ChatScrollProvider>
      <Toast open={!!toast} onOpenChange={handleToastOpenChange} title={toast?.title} type={toast?.type} />
    </AgentLightboxProvider>
  );
};
