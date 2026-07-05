import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ChatMessage } from "~/api";

import type { AgentState, UseAgentStatusProps } from "./useAgentStatus.ts";
import { useAgentStatus } from "./useAgentStatus.ts";

const DEBOUNCE_MS = 500;
const STOPPED_LINGER_MS = 1500;

const defaultProps: UseAgentStatusProps = {
  agentStatus: null,
  isAutoCompacting: false,
  isStreaming: false,
  inProgressChatMessage: null,
  workingUserMessageId: null,
  isStoppingAgent: false,
};

const makeChatMessage = (content: ChatMessage["content"]): ChatMessage =>
  ({
    id: "msg-test",
    role: "ASSISTANT",
    content,
  }) as unknown as ChatMessage;

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useAgentStatus", () => {
  describe("raw state derivation", () => {
    it("returns idle when nothing is active", () => {
      const { result } = renderHook(() => useAgentStatus(defaultProps));
      expect(result.current.state).toBe("idle");
      expect(result.current.isVisible).toBe(false);
      expect(result.current.label).toBe("");
      expect(result.current.isCancellable).toBe(false);
    });

    it("returns compacting when isAutoCompacting is true", () => {
      const { result } = renderHook(() => useAgentStatus({ ...defaultProps, isAutoCompacting: true }));
      expect(result.current.state).toBe("compacting");
      expect(result.current.label).toBe("Compacting...");
      expect(result.current.isCancellable).toBe(false);
      expect(result.current.isVisible).toBe(true);
    });

    it("returns stopping when isStoppingAgent is true", () => {
      const { result } = renderHook(() => useAgentStatus({ ...defaultProps, isStoppingAgent: true }));
      expect(result.current.state).toBe("stopping");
      expect(result.current.label).toBe("Stopping...");
      expect(result.current.isCancellable).toBe(false);
      expect(result.current.isVisible).toBe(true);
    });

    it("returns thinking when streaming with no content", () => {
      const { result } = renderHook(() => useAgentStatus({ ...defaultProps, isStreaming: true }));
      expect(result.current.state).toBe("thinking");
      expect(result.current.label).toBe("Thinking...");
      expect(result.current.isCancellable).toBe(true);
    });

    it("returns calling_tools when streaming with a tool_use block", () => {
      const message = makeChatMessage([{ type: "tool_use", id: "tu-1", name: "Read", input: {} }]);
      const { result } = renderHook(() =>
        useAgentStatus({ ...defaultProps, isStreaming: true, inProgressChatMessage: message }),
      );
      expect(result.current.state).toBe("calling_tools");
    });

    it("returns streaming when streaming with text content", () => {
      const message = makeChatMessage([{ type: "text", text: "Hello" }]);
      const { result } = renderHook(() =>
        useAgentStatus({ ...defaultProps, isStreaming: true, inProgressChatMessage: message }),
      );
      expect(result.current.state).toBe("streaming");
      expect(result.current.label).toBe("Streaming...");
      expect(result.current.isCancellable).toBe(true);
    });

    it("returns thinking when agent is running with a working message but not yet streaming", () => {
      const { result } = renderHook(() =>
        useAgentStatus({ ...defaultProps, agentStatus: "RUNNING", workingUserMessageId: "msg-1" }),
      );
      expect(result.current.state).toBe("thinking");
      expect(result.current.label).toBe("Thinking...");
      expect(result.current.isCancellable).toBe(true);
    });

    it("returns idle when agent is running but no working message", () => {
      const { result } = renderHook(() => useAgentStatus({ ...defaultProps, agentStatus: "RUNNING" }));
      expect(result.current.state).toBe("idle");
    });

    it("returns waiting_for_background when a background task is in flight (SCU-387)", () => {
      // After the agent emits its launched text, the in-progress message
      // ends with a text block — the raw lifecycle state would be "streaming"
      // — but the harness is sitting idle waiting for the bg task_notification.
      const message = makeChatMessage([{ type: "text", text: "Background subagent launched." }]);
      const { result } = renderHook(() =>
        useAgentStatus({
          ...defaultProps,
          isStreaming: true,
          inProgressChatMessage: message,
          agentStatus: "RUNNING",
          workingUserMessageId: "msg-1",
          pendingBackgroundTaskCount: 1,
        }),
      );
      expect(result.current.state).toBe("waiting_for_background");
      expect(result.current.label).toBe("Waiting for background tasks...");
      expect(result.current.isCancellable).toBe(true);
      expect(result.current.isVisible).toBe(true);
    });

    it("does NOT override compacting / stopping when a background task is in flight", () => {
      // Compacting is its own lifecycle event — bg-task accounting should
      // not mask it, otherwise the user can't see auto-compaction happening.
      const { result } = renderHook(() =>
        useAgentStatus({
          ...defaultProps,
          isAutoCompacting: true,
          pendingBackgroundTaskCount: 1,
        }),
      );
      expect(result.current.state).toBe("compacting");
    });

    it("returns idle when the agent has truly settled even with pending bg tasks", () => {
      // ``pendingBackgroundTaskCount`` only escalates ``thinking`` /
      // ``streaming`` / ``calling_tools`` to ``waiting_for_background`` —
      // an idle agent (no streaming, no working message) stays idle.
      const { result } = renderHook(() =>
        useAgentStatus({
          ...defaultProps,
          pendingBackgroundTaskCount: 1,
        }),
      );
      expect(result.current.state).toBe("idle");
    });

    it("returns idle when agentStatus is WAITING (AUQ / ExitPlanMode panel showing)", () => {
      // The held MCP tools/call keeps the request alive, so isStreaming and
      // inProgressChatMessage may still indicate activity — but the agent is
      // blocked on user input and the AUQ panel itself conveys that, so the
      // status pill should hide rather than say "Calling tools...".
      const message = makeChatMessage([{ type: "tool_use", id: "tu-1", name: "Read", input: {} }]);
      const { result } = renderHook(() =>
        useAgentStatus({
          ...defaultProps,
          agentStatus: "WAITING",
          isStreaming: true,
          inProgressChatMessage: message,
          workingUserMessageId: "msg-1",
        }),
      );
      expect(result.current.state).toBe("idle");
      expect(result.current.isVisible).toBe(false);
    });
  });

  describe("priority ordering", () => {
    it("compacting takes priority over stopping", () => {
      const { result } = renderHook(() =>
        useAgentStatus({ ...defaultProps, isAutoCompacting: true, isStoppingAgent: true }),
      );
      expect(result.current.state).toBe("compacting");
    });

    it("stopping takes priority over streaming", () => {
      const message = makeChatMessage([{ type: "text", text: "Hello" }]);
      const { result } = renderHook(() =>
        useAgentStatus({
          ...defaultProps,
          isStoppingAgent: true,
          isStreaming: true,
          inProgressChatMessage: message,
        }),
      );
      expect(result.current.state).toBe("stopping");
    });

    it("streaming takes priority over running-agent thinking", () => {
      const message = makeChatMessage([{ type: "text", text: "Hello" }]);
      const { result } = renderHook(() =>
        useAgentStatus({
          ...defaultProps,
          isStreaming: true,
          inProgressChatMessage: message,
          agentStatus: "RUNNING",
          workingUserMessageId: "msg-1",
        }),
      );
      expect(result.current.state).toBe("streaming");
    });
  });

  describe("debouncing", () => {
    it("debounces rapid state changes", () => {
      const { result, rerender } = renderHook((props: UseAgentStatusProps) => useAgentStatus(props), {
        initialProps: { ...defaultProps, isStreaming: true },
      });
      expect(result.current.state).toBe("thinking");

      // Immediately switch to streaming with text — should be debounced
      const message = makeChatMessage([{ type: "text", text: "Hello" }]);
      rerender({ ...defaultProps, isStreaming: true, inProgressChatMessage: message });

      // State should still be thinking (debounced)
      expect(result.current.state).toBe("thinking");

      // After debounce period, state should update
      act(() => {
        vi.advanceTimersByTime(DEBOUNCE_MS);
      });
      expect(result.current.state).toBe("streaming");
    });

    it("applies state immediately after debounce period has elapsed", () => {
      const { result, rerender } = renderHook((props: UseAgentStatusProps) => useAgentStatus(props), {
        initialProps: { ...defaultProps, isStreaming: true },
      });
      expect(result.current.state).toBe("thinking");

      // Advance past debounce time
      act(() => {
        vi.advanceTimersByTime(DEBOUNCE_MS + 1);
      });

      // Now switch — should apply immediately
      const message = makeChatMessage([{ type: "text", text: "Hello" }]);
      rerender({ ...defaultProps, isStreaming: true, inProgressChatMessage: message });
      expect(result.current.state).toBe("streaming");
    });

    it("debounces brief idle transitions to prevent timer reset", () => {
      const { result, rerender } = renderHook((props: UseAgentStatusProps) => useAgentStatus(props), {
        initialProps: { ...defaultProps, isStreaming: true },
      });
      expect(result.current.state).toBe("thinking");

      // Advance past debounce so next change applies immediately
      act(() => {
        vi.advanceTimersByTime(DEBOUNCE_MS);
      });

      // Switch to calling_tools
      const toolMessage = makeChatMessage([{ type: "tool_use", id: "tu-1", name: "Read", input: {} }]);
      rerender({ ...defaultProps, isStreaming: true, inProgressChatMessage: toolMessage });
      expect(result.current.state).toBe("calling_tools");

      // Brief idle flicker (e.g., between tool calls) — should NOT go idle
      rerender(defaultProps);
      expect(result.current.state).toBe("calling_tools");
      expect(result.current.isVisible).toBe(true);

      // Active state returns quickly
      rerender({ ...defaultProps, isStreaming: true });

      // After debounce, should show the new active state, not have flickered to idle
      act(() => {
        vi.advanceTimersByTime(DEBOUNCE_MS);
      });
      expect(result.current.state).toBe("thinking");
      expect(result.current.isVisible).toBe(true);
    });

    it("transitions to idle after debounce period when turn truly ends", () => {
      const { result, rerender } = renderHook((props: UseAgentStatusProps) => useAgentStatus(props), {
        initialProps: { ...defaultProps, isStreaming: true },
      });
      expect(result.current.state).toBe("thinking");

      // Switch to a new active state so lastChangeTime resets
      act(() => {
        vi.advanceTimersByTime(DEBOUNCE_MS);
      });
      const toolMessage = makeChatMessage([{ type: "tool_use", id: "tu-1", name: "Read", input: {} }]);
      rerender({ ...defaultProps, isStreaming: true, inProgressChatMessage: toolMessage });
      expect(result.current.state).toBe("calling_tools");

      // Go idle shortly after — should be debounced
      rerender(defaultProps);
      expect(result.current.state).toBe("calling_tools");

      // After debounce period, should transition to idle
      act(() => {
        vi.advanceTimersByTime(DEBOUNCE_MS);
      });
      expect(result.current.state).toBe("idle");
      expect(result.current.isVisible).toBe(false);
    });
  });

  describe("compacting indicator (SCU-1564)", () => {
    it("shows compacting even when compaction ends within the debounce window", () => {
      // A compaction brief enough to end within the debounce window must still
      // appear in the pill. The render callback records every displayed state
      // so the assertion can confirm "compacting" showed at some point, rather
      // than only inspecting the final state.
      const observed: Array<AgentState> = [];
      const { rerender } = renderHook(
        (props: UseAgentStatusProps) => {
          const status = useAgentStatus(props);
          observed.push(status.state);
          return status;
        },
        { initialProps: { ...defaultProps, agentStatus: "RUNNING", workingUserMessageId: "msg-1" } },
      );
      expect(observed).toContain("thinking");

      // Compaction starts almost immediately, well within the debounce window.
      rerender({ ...defaultProps, agentStatus: "RUNNING", workingUserMessageId: "msg-1", isAutoCompacting: true });

      // It ends before DEBOUNCE_MS elapses: the agent resumes streaming.
      act(() => {
        vi.advanceTimersByTime(DEBOUNCE_MS - 100);
      });
      const summary = makeChatMessage([{ type: "text", text: "Summary of the conversation so far." }]);
      rerender({
        ...defaultProps,
        agentStatus: "RUNNING",
        workingUserMessageId: "msg-1",
        isStreaming: true,
        inProgressChatMessage: summary,
      });
      act(() => {
        vi.runAllTimers();
      });

      // The compacting state must have been displayed at some point.
      expect(observed).toContain("compacting");
    });

    it("shows compacting immediately, not after the debounce delay", () => {
      // Even when the previous displayed-state change was recent (so an active
      // state would be debounced), entering compaction must light the pill on
      // the very next render — the indicator should not lag the actual start
      // of compaction by up to DEBOUNCE_MS.
      const { result, rerender } = renderHook((props: UseAgentStatusProps) => useAgentStatus(props), {
        initialProps: { ...defaultProps, agentStatus: "RUNNING", workingUserMessageId: "msg-1" },
      });
      expect(result.current.state).toBe("thinking");

      rerender({ ...defaultProps, agentStatus: "RUNNING", workingUserMessageId: "msg-1", isAutoCompacting: true });
      // No timer advance: compacting is shown synchronously.
      expect(result.current.state).toBe("compacting");
      expect(result.current.label).toBe("Compacting...");
      expect(result.current.isVisible).toBe(true);
    });
  });

  describe("stopped state transition", () => {
    it("shows stopped briefly when transitioning from stopping to idle", () => {
      const { result, rerender } = renderHook((props: UseAgentStatusProps) => useAgentStatus(props), {
        initialProps: { ...defaultProps, isStoppingAgent: true },
      });
      expect(result.current.state).toBe("stopping");

      // Stop completes — isStoppingAgent goes false, raw state goes idle
      rerender(defaultProps);

      // Should show "Stopped" not "idle"
      expect(result.current.state).toBe("stopped");
      expect(result.current.label).toBe("Stopped");
      expect(result.current.isVisible).toBe(true);
      expect(result.current.isCancellable).toBe(false);
    });

    it("stopped state lingers for STOPPED_LINGER_MS then goes idle", () => {
      const { result, rerender } = renderHook((props: UseAgentStatusProps) => useAgentStatus(props), {
        initialProps: { ...defaultProps, isStoppingAgent: true },
      });

      // Transition stopping → idle → stopped
      rerender(defaultProps);
      expect(result.current.state).toBe("stopped");

      // Not yet idle
      act(() => {
        vi.advanceTimersByTime(STOPPED_LINGER_MS - 1);
      });
      expect(result.current.state).toBe("stopped");

      // Now goes idle
      act(() => {
        vi.advanceTimersByTime(1);
      });
      expect(result.current.state).toBe("idle");
      expect(result.current.isVisible).toBe(false);
    });

    it("stopped state is interrupted if a new active state arrives", () => {
      const { result, rerender } = renderHook((props: UseAgentStatusProps) => useAgentStatus(props), {
        initialProps: { ...defaultProps, isStoppingAgent: true },
      });

      // Go to stopped
      rerender(defaultProps);
      expect(result.current.state).toBe("stopped");

      // Advance past debounce to ensure immediate application
      act(() => {
        vi.advanceTimersByTime(DEBOUNCE_MS);
      });

      // New active state arrives while stopped
      rerender({ ...defaultProps, isStreaming: true });
      expect(result.current.state).toBe("thinking");
      expect(result.current.isVisible).toBe(true);
    });

    it("normal idle transition (not from stopping) does not show stopped", () => {
      const { result, rerender } = renderHook((props: UseAgentStatusProps) => useAgentStatus(props), {
        initialProps: { ...defaultProps, isStreaming: true },
      });
      expect(result.current.state).toBe("thinking");

      // Advance past debounce
      act(() => {
        vi.advanceTimersByTime(DEBOUNCE_MS);
      });

      // Go directly to idle (not from stopping) — debounced
      rerender(defaultProps);

      act(() => {
        vi.advanceTimersByTime(DEBOUNCE_MS);
      });
      expect(result.current.state).toBe("idle");
    });
  });

  describe("visibility", () => {
    it("is visible for all active states", () => {
      const activeStates: Array<Partial<UseAgentStatusProps>> = [
        { isStreaming: true },
        { isAutoCompacting: true },
        { isStoppingAgent: true },
        { agentStatus: "RUNNING", workingUserMessageId: "msg-1" },
      ];

      for (const overrides of activeStates) {
        const { result } = renderHook(() => useAgentStatus({ ...defaultProps, ...overrides }));
        expect(result.current.isVisible).toBe(true);
      }
    });

    it("is not visible when idle", () => {
      const { result } = renderHook(() => useAgentStatus(defaultProps));
      expect(result.current.isVisible).toBe(false);
    });
  });
});
