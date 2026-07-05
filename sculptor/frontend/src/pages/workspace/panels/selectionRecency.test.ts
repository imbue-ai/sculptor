import { describe, expect, it } from "vitest";

import type { DiffTab } from "~/pages/workspace/diffPanel/types.ts";
import type { DiffSelection } from "~/pages/workspace/diffViewer/types.ts";

import { reconcileSelectionByRecency } from "./selectionRecency.ts";

type LocalPick = { filePath: string; at: number };

const fileViewTab = (realPath: string, viewedAt: number): DiffTab => ({
  kind: "file-view",
  filePath: `__file_view__:${realPath}`,
  realPath,
  viewedAt,
});

const singleTab = (filePath: string, viewedAt: number): DiffTab => ({
  kind: "single",
  filePath,
  status: "M",
  viewedAt,
});

const toSelection = (local: LocalPick): DiffSelection => ({ kind: "file-view", filePath: local.filePath });

const fromTab = (tab: DiffTab | null): DiffSelection | null =>
  tab !== null && tab.kind === "file-view" ? { kind: "file-view", filePath: tab.realPath } : null;

const reconcile = (local: LocalPick | null, tab: DiffTab | null): DiffSelection | null =>
  reconcileSelectionByRecency({ local, tab, tabKind: "file-view", toSelection, fromTab });

describe("reconcileSelectionByRecency", () => {
  it("returns null when there is no selection from either source", () => {
    expect(reconcile(null, null)).toBeNull();
  });

  it("uses the local click when it is the only source", () => {
    expect(reconcile({ filePath: "a.ts", at: 10 }, null)).toEqual({ kind: "file-view", filePath: "a.ts" });
  });

  it("uses the tab when there is no local click", () => {
    expect(reconcile(null, fileViewTab("b.ts", 10))).toEqual({ kind: "file-view", filePath: "b.ts" });
  });

  it("picks whichever source was activated last", () => {
    expect(reconcile({ filePath: "clicked.ts", at: 20 }, fileViewTab("opened.ts", 10))).toEqual({
      kind: "file-view",
      filePath: "clicked.ts",
    });
    expect(reconcile({ filePath: "clicked.ts", at: 10 }, fileViewTab("opened.ts", 20))).toEqual({
      kind: "file-view",
      filePath: "opened.ts",
    });
  });

  it("breaks a timestamp tie in favor of the local click", () => {
    expect(reconcile({ filePath: "clicked.ts", at: 10 }, fileViewTab("opened.ts", 10))).toEqual({
      kind: "file-view",
      filePath: "clicked.ts",
    });
  });

  it("lets an old local click win over a newer tab of a foreign kind", () => {
    // An agent-opened diff belongs to another panel; it must not clear this
    // panel's open file, however recent it is.
    expect(reconcile({ filePath: "clicked.ts", at: 10 }, singleTab("foreign.ts", 99))).toEqual({
      kind: "file-view",
      filePath: "clicked.ts",
    });
  });

  it("returns null for a foreign-kind tab with no local click", () => {
    expect(reconcile(null, singleTab("foreign.ts", 99))).toBeNull();
  });
});
