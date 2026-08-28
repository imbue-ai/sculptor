import type { SuggestionProps } from "@tiptap/suggestion";
import { describe, expect, it, vi } from "vitest";

import { navigateUpPathMode } from "./suggestion";

// `navigateUpPathMode` is the Shift+Tab handler for the @-mention file picker.
// It reads `props.query` to decide whether the popover is in "path mode"
// (a query starting with `~`, `/`, or `.`) and, if so, rewrites the mention
// range with the parent-directory query so the popover re-queries one level
// up. For fuzzy-mode queries or path-mode roots it is a no-op.

type EditorChain = {
  focus: () => EditorChain;
  deleteRange: (range: unknown) => EditorChain;
  insertContentAt: (from: number, content: string) => EditorChain;
  run: () => boolean;
};

type MockChainCalls = {
  deleteRange: Array<unknown>;
  insertContentAt: Array<{ from: number; content: string }>;
  runCount: number;
};

const makeProps = (query: string): { props: SuggestionProps; calls: MockChainCalls } => {
  const calls: MockChainCalls = { deleteRange: [], insertContentAt: [], runCount: 0 };
  const chain: EditorChain = {
    focus: (): EditorChain => chain,
    deleteRange: (range): EditorChain => {
      calls.deleteRange.push(range);
      return chain;
    },
    insertContentAt: (from, content): EditorChain => {
      calls.insertContentAt.push({ from, content });
      return chain;
    },
    run: (): boolean => {
      calls.runCount += 1;
      return true;
    },
  };
  const props = {
    query,
    range: { from: 5, to: 10 },
    editor: {
      chain: (): EditorChain => chain,
    },
  } as unknown as SuggestionProps;
  return { props, calls };
};

describe("navigateUpPathMode", () => {
  it("returns false for a fuzzy-mode query (no path prefix)", () => {
    const { props, calls } = makeProps("editor");
    expect(navigateUpPathMode(props)).toBe(false);
    // No rewrite should have happened.
    expect(calls.runCount).toBe(0);
    expect(calls.insertContentAt).toEqual([]);
  });

  it("returns false for empty query", () => {
    const { props, calls } = makeProps("");
    expect(navigateUpPathMode(props)).toBe(false);
    expect(calls.runCount).toBe(0);
  });

  it("returns false at the workspace-root path-mode root (./)", () => {
    const { props, calls } = makeProps("./");
    expect(navigateUpPathMode(props)).toBe(false);
    expect(calls.runCount).toBe(0);
  });

  it("returns false at the home-directory path-mode root (~/)", () => {
    const { props, calls } = makeProps("~/");
    expect(navigateUpPathMode(props)).toBe(false);
    expect(calls.runCount).toBe(0);
  });

  it("returns false at the absolute-filesystem path-mode root (/)", () => {
    const { props, calls } = makeProps("/");
    expect(navigateUpPathMode(props)).toBe(false);
    expect(calls.runCount).toBe(0);
  });

  it("walks up one level from a nested workspace directory", () => {
    // Query "./src/components/" -> parent is "./src/"
    const { props, calls } = makeProps("./src/components/");
    expect(navigateUpPathMode(props)).toBe(true);
    expect(calls.runCount).toBe(1);
    expect(calls.deleteRange).toEqual([{ from: 5, to: 10 }]);
    expect(calls.insertContentAt).toEqual([{ from: 5, content: "@./src/" }]);
  });

  it("walks up from ./src/ to ./ (the path-mode root)", () => {
    const { props, calls } = makeProps("./src/");
    expect(navigateUpPathMode(props)).toBe(true);
    expect(calls.runCount).toBe(1);
    expect(calls.insertContentAt).toEqual([{ from: 5, content: "@./" }]);
  });

  it("walks up from ~/foo/bar/ to ~/foo/", () => {
    const { props, calls } = makeProps("~/foo/bar/");
    expect(navigateUpPathMode(props)).toBe(true);
    expect(calls.runCount).toBe(1);
    expect(calls.insertContentAt).toEqual([{ from: 5, content: "@~/foo/" }]);
  });

  it("walks up from ~/foo/ to ~/", () => {
    const { props, calls } = makeProps("~/foo/");
    expect(navigateUpPathMode(props)).toBe(true);
    expect(calls.runCount).toBe(1);
    expect(calls.insertContentAt).toEqual([{ from: 5, content: "@~/" }]);
  });

  it("walks up an absolute path from /usr/local/ to /usr/", () => {
    const { props, calls } = makeProps("/usr/local/");
    expect(navigateUpPathMode(props)).toBe(true);
    expect(calls.runCount).toBe(1);
    expect(calls.insertContentAt).toEqual([{ from: 5, content: "@/usr/" }]);
  });

  it("walks from inside a directory (filter query) up to that directory's parent", () => {
    // With "./src/comp" the directory is "./src/" and "comp" is a filter
    // within it. Shift+Tab walks to the parent of "./src/", which is "./".
    const { props, calls } = makeProps("./src/comp");
    expect(navigateUpPathMode(props)).toBe(true);
    expect(calls.insertContentAt).toEqual([{ from: 5, content: "@./" }]);
  });

  it("rewrites through the full editor chain (focus → deleteRange → insertContentAt → run)", () => {
    // Regression: the rewrite is chained on the editor and must call .run() so
    // the insertion is actually committed. Without .run() the transaction is
    // built but never dispatched, leaving the picker stuck on the child query.
    const { props, calls } = makeProps("./src/components/");
    const chainSpy = vi.spyOn(props.editor, "chain");
    expect(navigateUpPathMode(props)).toBe(true);
    expect(chainSpy).toHaveBeenCalledTimes(1);
    expect(calls.runCount).toBe(1);
  });
});
