import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentTaskStatus, type Task } from "~/api";

import { useTaskTiers } from "../useTaskTiers";

const t = (id: string, blockedBy: Array<string> = [], status: AgentTaskStatus = AgentTaskStatus.PENDING): Task => ({
  id,
  subject: `Task ${id}`,
  description: "",
  activeForm: null,
  status,
  blocks: [],
  blockedBy,
  owner: null,
  metadata: {},
});

describe("useTaskTiers", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns empty tier map for null / empty input", () => {
    const nullResult = renderHook(() => useTaskTiers(null)).result.current;
    expect(nullResult.tierById.size).toBe(0);
    expect(nullResult.maxTier).toBe(0);
    expect(nullResult.liveTier).toBeNull();

    const emptyResult = renderHook(() => useTaskTiers([])).result.current;
    expect(emptyResult.tierById.size).toBe(0);
    expect(emptyResult.maxTier).toBe(0);
    expect(emptyResult.liveTier).toBeNull();
  });

  it("assigns tiers along a linear chain", () => {
    const tasks = [t("1"), t("2", ["1"]), t("3", ["2"])];
    const { tierById, maxTier } = renderHook(() => useTaskTiers(tasks)).result.current;
    expect(tierById.get("1")).toBe(0);
    expect(tierById.get("2")).toBe(1);
    expect(tierById.get("3")).toBe(2);
    expect(maxTier).toBe(2);
  });

  it("handles fan-out (one parent, multiple dependents at same tier)", () => {
    const tasks = [t("1"), t("2", ["1"]), t("3", ["1"])];
    const { tierById, maxTier } = renderHook(() => useTaskTiers(tasks)).result.current;
    expect(tierById.get("1")).toBe(0);
    expect(tierById.get("2")).toBe(1);
    expect(tierById.get("3")).toBe(1);
    expect(maxTier).toBe(1);
  });

  it("handles fan-in (multiple parents at tier 0, single dependent at tier 1)", () => {
    const tasks = [t("1"), t("2"), t("3", ["1", "2"])];
    const { tierById, maxTier } = renderHook(() => useTaskTiers(tasks)).result.current;
    expect(tierById.get("1")).toBe(0);
    expect(tierById.get("2")).toBe(0);
    expect(tierById.get("3")).toBe(1);
    expect(maxTier).toBe(1);
  });

  it("handles a diamond", () => {
    const tasks = [t("1"), t("2", ["1"]), t("3", ["1"]), t("4", ["2", "3"])];
    const { tierById, maxTier } = renderHook(() => useTaskTiers(tasks)).result.current;
    expect(tierById.get("1")).toBe(0);
    expect(tierById.get("2")).toBe(1);
    expect(tierById.get("3")).toBe(1);
    expect(tierById.get("4")).toBe(2);
    expect(maxTier).toBe(2);
  });

  it("warns and degrades when blockedBy references an unknown task", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const tasks = [t("2", ["missing"])];
    const { tierById } = renderHook(() => useTaskTiers(tasks)).result.current;
    expect(tierById.get("2")).toBe(1);
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("blockedBy unknown missing"));
  });

  it("warns and assigns tier 0 to tasks in a cycle", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const tasks = [t("1", ["2"]), t("2", ["1"])];
    const { tierById } = renderHook(() => useTaskTiers(tasks)).result.current;
    expect(tierById.get("1")).toBe(0);
    expect(tierById.get("2")).toBe(0);
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("cycle detected"));
  });

  it("reports liveTier as the tier of the first in_progress task", () => {
    const tasks = [
      t("1", [], AgentTaskStatus.COMPLETED),
      t("2", ["1"], AgentTaskStatus.IN_PROGRESS),
      t("3", ["2"], AgentTaskStatus.PENDING),
    ];
    const { liveTier } = renderHook(() => useTaskTiers(tasks)).result.current;
    expect(liveTier).toBe(1);
  });

  it("returns liveTier null when no task is in_progress", () => {
    const tasks = [t("1", [], AgentTaskStatus.COMPLETED), t("2", ["1"], AgentTaskStatus.PENDING)];
    const { liveTier } = renderHook(() => useTaskTiers(tasks)).result.current;
    expect(liveTier).toBeNull();
  });

  it("picks the first in_progress task in input order when multiple exist", () => {
    const tasks = [
      t("1", [], AgentTaskStatus.PENDING),
      t("2", ["1"], AgentTaskStatus.IN_PROGRESS),
      t("3", ["2"], AgentTaskStatus.IN_PROGRESS),
    ];
    const { liveTier } = renderHook(() => useTaskTiers(tasks)).result.current;
    expect(liveTier).toBe(1);
  });
});
