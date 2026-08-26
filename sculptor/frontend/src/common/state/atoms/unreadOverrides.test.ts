import { beforeEach, describe, expect, it } from "vitest";

import { TaskStatus } from "../../../api";
import {
  clearUnreadOverride,
  getAgentDotStatusWithUnreadOverride,
  isUnreadOverrideActive,
  resetUnreadOverridesForTesting,
  setUnreadOverride,
} from "./unreadOverrides";

const UPDATED_AT = "2024-01-01T00:00:00Z";
const LATER_UPDATED_AT = "2024-01-01T00:05:00Z";
const EVEN_LATER_UPDATED_AT = "2024-01-01T00:10:00Z";

const idle = (updatedAt: string): { status: TaskStatus; updatedAt: string } => ({
  status: TaskStatus.READY,
  updatedAt,
});

const running = (updatedAt: string): { status: TaskStatus; updatedAt: string } => ({
  status: TaskStatus.RUNNING,
  updatedAt,
});

beforeEach(() => {
  resetUnreadOverridesForTesting();
});

describe("unread override lifecycle", () => {
  it("is inactive for a task that was never marked", () => {
    expect(isUnreadOverrideActive("task-1", idle(UPDATED_AT))).toBe(false);
  });

  it("is active while the task's updatedAt matches the value recorded at mark time", () => {
    setUnreadOverride("task-1", idle(UPDATED_AT));
    expect(isUnreadOverrideActive("task-1", idle(UPDATED_AT))).toBe(true);
  });

  it("expires when an idle-marked task's updatedAt advances (a new agent turn)", () => {
    setUnreadOverride("task-1", idle(UPDATED_AT));
    expect(isUnreadOverrideActive("task-1", idle(LATER_UPDATED_AT))).toBe(false);
  });

  it("holds through streaming ticks when marked mid-run", () => {
    setUnreadOverride("task-1", running(UPDATED_AT));
    // Every tick advances updatedAt while the run continues — the override holds.
    expect(isUnreadOverrideActive("task-1", running(LATER_UPDATED_AT))).toBe(true);
    expect(isUnreadOverrideActive("task-1", running(EVEN_LATER_UPDATED_AT))).toBe(true);
  });

  it("re-keys a mid-run override to the run's final updatedAt on completion", () => {
    setUnreadOverride("task-1", running(UPDATED_AT));
    // The run completes: still active (re-keyed to the completion's updatedAt)…
    expect(isUnreadOverrideActive("task-1", idle(LATER_UPDATED_AT))).toBe(true);
    expect(isUnreadOverrideActive("task-1", idle(LATER_UPDATED_AT))).toBe(true);
    // …until the NEXT turn advances updatedAt past it.
    expect(isUnreadOverrideActive("task-1", idle(EVEN_LATER_UPDATED_AT))).toBe(false);
  });

  it("clears on clearUnreadOverride (a fresh activation of the agent)", () => {
    setUnreadOverride("task-1", idle(UPDATED_AT));
    clearUnreadOverride("task-1");
    expect(isUnreadOverrideActive("task-1", idle(UPDATED_AT))).toBe(false);
  });

  it("tracks each task independently", () => {
    setUnreadOverride("task-1", idle(UPDATED_AT));
    setUnreadOverride("task-2", idle(UPDATED_AT));
    clearUnreadOverride("task-1");
    expect(isUnreadOverrideActive("task-1", idle(UPDATED_AT))).toBe(false);
    expect(isUnreadOverrideActive("task-2", idle(UPDATED_AT))).toBe(true);
  });
});

describe("getAgentDotStatusWithUnreadOverride", () => {
  it("upgrades read to unread while the override is active", () => {
    setUnreadOverride("task-1", idle(UPDATED_AT));
    const task = { status: TaskStatus.READY, updatedAt: UPDATED_AT, lastReadAt: LATER_UPDATED_AT };
    expect(getAgentDotStatusWithUnreadOverride("task-1", task)).toBe("unread");
  });

  it("keeps activity dots (running) over the override", () => {
    setUnreadOverride("task-1", running(UPDATED_AT));
    const task = { status: TaskStatus.RUNNING, updatedAt: LATER_UPDATED_AT, lastReadAt: null };
    expect(getAgentDotStatusWithUnreadOverride("task-1", task)).toBe("running");
  });
});
