import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";

import { AlphaChipDiffPopover } from "../AlphaChipDiffPopover.tsx";
import { ChatTaskProvider } from "../ChatTaskContext.tsx";
import type { ChipData } from "../chipRow.types.ts";

const WORKSPACE_PATH = "/repo/workspace";

vi.mock("~/pages/workspace/hooks/useWorkspaceCodePath.ts", () => ({
  useWorkspaceCodePath: (): string => WORKSPACE_PATH,
}));

// The highlighter-readiness gate would kick off a real shiki load in jsdom;
// these tests never render a diff body (chipData.results: []), so report
// ready without loading anything.
vi.mock("~/pages/workspace/diffPanel/usePierreHighlighterReady.ts", () => ({
  usePierreHighlighterReady: (): boolean => true,
}));

// Replace every atom the component reads with a labelled placeholder so the
// jotai mock below can route reads/writes per-atom. Returning a blanket null
// from `useAtomValue` would silently keep passing if the routing logic later
// starts depending on a real atom value.
vi.mock("~/pages/workspace/diffPanel/atoms/diffPanel.ts", () => ({
  openDiffTabAtom: { __label: "diff" },
  openFileViewTabAtom: { __label: "fileView" },
}));

vi.mock("~/common/state/atoms/userConfig.ts", () => ({
  appThemeAtom: { __label: "appTheme" },
}));

vi.mock("~/common/state/atoms/themeBuilder.ts", () => ({
  themeCodeThemeAtom: { __label: "themeCode" },
}));

type Recorder = { diff: Array<unknown>; fileView: Array<unknown> };
const recorder: Recorder = { diff: [], fileView: [] };

vi.mock("jotai", async () => {
  const actual: Record<string, unknown> = await vi.importActual("jotai");
  return {
    ...actual,
    useSetAtom:
      (atom: { __label?: "diff" | "fileView" }) =>
      (payload: unknown): void => {
        if (atom.__label === "diff") recorder.diff.push(payload);
        else if (atom.__label === "fileView") recorder.fileView.push(payload);
      },
    useAtomValue: (atom: { __label?: string }): unknown => {
      // Theme atoms feed into <PatchDiff>, which doesn't render in these
      // tests (chipData.results: []), so a stub is safe. Throwing on
      // anything else surfaces future drift loudly.
      if (atom.__label === "appTheme") return "light";
      if (atom.__label === "themeCode") return "GitHub";
      throw new Error(`Unexpected useAtomValue call: ${JSON.stringify(atom)}`);
    },
  };
});

const makeChipData = (overrides: Partial<ChipData> = {}): ChipData => ({
  id: "tool-1",
  filePath: `${WORKSPACE_PATH}/src/file.ts`,
  displayName: "file.ts",
  state: "completed",
  stats: { added: 1, removed: 0 },
  isNewFile: false,
  blocks: [],
  results: [],
  errorDetail: null,
  errorContentType: null,
  ...overrides,
});

const renderPopover = (chipData: ChipData): ReactElement => (
  <ChatTaskProvider workspaceId="ws-test" taskId="agent-1">
    <Theme>
      <AlphaChipDiffPopover chipData={chipData} onClose={(): void => {}} onNavigate={(): void => {}} />
    </Theme>
  </ChatTaskProvider>
);

beforeEach(() => {
  recorder.diff = [];
  recorder.fileView = [];
});

afterEach(() => {
  cleanup();
});

describe("AlphaChipDiffPopover.handleOpenDiffPanel routing (SCU-366)", () => {
  it("opens a diff tab for an in-workspace file", () => {
    render(renderPopover(makeChipData({ filePath: `${WORKSPACE_PATH}/src/file.ts`, isNewFile: false })));

    fireEvent.click(screen.getByTestId(ElementIds.ALPHA_CHAT_CHIP_VIEW_FULL_DIFF_BTN));

    expect(recorder.diff).toHaveLength(1);
    expect(recorder.fileView).toHaveLength(0);
    expect(recorder.diff[0]).toMatchObject({
      workspaceId: "ws-test",
      filePath: `${WORKSPACE_PATH}/src/file.ts`,
      status: "M",
    });
  });

  it("opens a file-view tab for a file outside the workspace clone", () => {
    render(renderPopover(makeChipData({ filePath: "/tmp/outside.md", isNewFile: true })));

    fireEvent.click(screen.getByTestId(ElementIds.ALPHA_CHAT_CHIP_VIEW_FULL_DIFF_BTN));

    expect(recorder.fileView).toHaveLength(1);
    expect(recorder.diff).toHaveLength(0);
    expect(recorder.fileView[0]).toMatchObject({ workspaceId: "ws-test", filePath: "/tmp/outside.md" });
  });

  it("opens a file-view tab for a plan file even when inside the workspace", () => {
    const planPath = `${WORKSPACE_PATH}/.claude/plans/my-plan.md`;
    render(renderPopover(makeChipData({ filePath: planPath, isNewFile: true })));

    fireEvent.click(screen.getByTestId(ElementIds.ALPHA_CHAT_CHIP_VIEW_FULL_DIFF_BTN));

    expect(recorder.fileView).toHaveLength(1);
    expect(recorder.diff).toHaveLength(0);
    expect(recorder.fileView[0]).toMatchObject({ workspaceId: "ws-test", filePath: planPath });
  });
});
