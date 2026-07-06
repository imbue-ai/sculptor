/**
 * PierreDiffView must not mount Pierre's renderer while the shared syntax
 * highlighter's themes are still cold.
 *
 * Pierre renders NOTHING when its shared highlighter lacks the configured
 * themes at mount — it leaves a bare `<pre>` behind and relies on an async
 * recovery re-render once the themes attach. Under React StrictMode (the dev
 * bundle) the simulated remount severs that recovery: the remounted Pierre
 * instance finds the aborted mount's empty `<pre>`, mistakes it for
 * prerendered content, and never renders — the first diff of a dev session
 * stays permanently blank. PierreDiffView therefore gates Pierre on
 * highlighter readiness, so the first real Pierre render is always
 * synchronous and survives the StrictMode remount.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Controlled shared-highlighter state, read lazily by the mock below.
let isLoaded = false;
let areAttached = false;
let resolveSharedHighlighter: () => void = () => {};

vi.mock("@pierre/diffs", () => ({
  isHighlighterLoaded: (): boolean => isLoaded,
  areThemesAttached: (): boolean => areAttached,
  getSharedHighlighter: (): Promise<void> =>
    new Promise((resolve) => {
      resolveSharedHighlighter = (): void => {
        isLoaded = true;
        areAttached = true;
        resolve();
      };
    }),
  getSingularPatch: vi.fn(),
  processFile: vi.fn(),
}));

// Pierre's real components need shadow DOM / web components that jsdom lacks;
// a sentinel div is enough to observe whether the gate mounted them.
vi.mock("@pierre/diffs/react", () => ({
  PatchDiff: ({ patch }: { patch: string }): ReactElement => <div data-testid="patch-diff">{patch}</div>,
  FileDiff: (): ReactElement => <div data-testid="file-diff" />,
}));

import { PierreDiffView } from "./PierreDiffView.tsx";

const DIFF = "diff --git a/stuff.txt b/stuff.txt\n@@ -0,0 +1 @@\n+stuff\n";

const renderView = (): void => {
  render(
    <StrictMode>
      <PierreDiffView diffString={DIFF} viewType="unified" overflow="wrap" themeType="dark" />
    </StrictMode>,
  );
};

describe("PierreDiffView highlighter readiness gate", () => {
  beforeEach(() => {
    isLoaded = false;
    areAttached = false;
  });

  afterEach(() => {
    cleanup();
  });

  it("defers Pierre until the shared highlighter's themes attach", async () => {
    renderView();

    // Cold highlighter: mounting Pierre now would render a bare <pre> that a
    // StrictMode remount then mistakes for prerendered content, leaving the
    // diff permanently blank.
    expect(screen.queryByTestId("patch-diff")).not.toBeInTheDocument();

    resolveSharedHighlighter();
    await waitFor(() => expect(screen.getByTestId("patch-diff")).toBeInTheDocument());
  });

  it("renders Pierre immediately when the themes are already attached", () => {
    isLoaded = true;
    areAttached = true;
    renderView();

    expect(screen.getByTestId("patch-diff")).toBeInTheDocument();
  });
});
