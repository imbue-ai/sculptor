import { describe, expect, it } from "vitest";

import { activeEngineCount, registerEngine, StreamingEngine, unregisterEngine } from "./StreamingEngine.ts";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function msg(blocks: Array<{ type: string; [k: string]: unknown }>): any {
  return { role: "assistant", id: "msg-1", content: blocks, approximateCreationTime: new Date().toISOString() };
}

function txt(text: string): { type: "text"; text: string } {
  return { type: "text" as const, text };
}

function tool(
  id: string,
  name: string,
): { type: "tool_use"; id: string; name: string; input: Record<string, unknown> } {
  return { type: "tool_use" as const, id, name, input: {} };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function visibleText(result: any): string {
  if (!result) return "";
  return result.content
    .filter((b: { type: string }) => b.type === "text")
    .map((b: { text: string }) => b.text)
    .join("");
}

describe("engine registration", () => {
  it("allows more than one engine to be registered at once (concurrent agent chats)", () => {
    // Two agent panels — e.g. one in the center section and one in the right — each
    // mount their own engine. Registering the second must NOT throw.
    const a = new StreamingEngine();
    const b = new StreamingEngine();
    registerEngine(a);
    expect(() => registerEngine(b)).not.toThrow();
    expect(activeEngineCount()).toBe(2);

    unregisterEngine(a);
    expect(activeEngineCount()).toBe(1);
    unregisterEngine(b);
    expect(activeEngineCount()).toBe(0);
  });

  it("registering the same engine twice is idempotent", () => {
    const a = new StreamingEngine();
    registerEngine(a);
    registerEngine(a);
    expect(activeEngineCount()).toBe(1);
    unregisterEngine(a);
    expect(activeEngineCount()).toBe(0);
  });
});

describe("StreamingEngine", () => {
  it("flush returns null when no snapshot", () => {
    expect(new StreamingEngine().flush()).toBeNull();
  });

  it("flush reveals all text", () => {
    const e = new StreamingEngine();
    e.updateLatestSnapshot(msg([txt("Hello!")]));
    expect(visibleText(e.flush())).toBe("Hello!");
  });

  it("updateLatestSnapshot returns null for null", () => {
    expect(new StreamingEngine().updateLatestSnapshot(null)).toBeNull();
  });

  it("first snapshot aligns cursor to end", () => {
    const e = new StreamingEngine();
    expect(visibleText(e.updateLatestSnapshot(msg([txt("abc")])))).toBe("abc");
  });

  it("advanceCursor reveals text incrementally", () => {
    const e = new StreamingEngine();
    e.updateLatestSnapshot(msg([txt("Hello")]));
    e.updateLatestSnapshot(msg([txt("Hello, world!")]));
    expect(e.getBufferSize()).toBe(8);
    expect(visibleText(e.advanceCursor(3))).toBe("Hello, w");
    expect(e.getBufferSize()).toBe(5);
  });

  it("advanceCursor does not overshoot", () => {
    const e = new StreamingEngine();
    e.updateLatestSnapshot(msg([txt("Hi")]));
    e.updateLatestSnapshot(msg([txt("Hi there")]));
    e.advanceCursor(1000);
    expect(e.getBufferSize()).toBe(0);
    expect(visibleText(e.advanceCursor(0))).toBe("Hi there");
  });

  it("advanceCursor(0) returns current state", () => {
    const e = new StreamingEngine();
    e.updateLatestSnapshot(msg([txt("abc")]));
    expect(visibleText(e.advanceCursor(0))).toBe("abc");
  });

  it("advanceCursor skips non-text blocks and preserves already-visible text", () => {
    const e = new StreamingEngine();
    e.updateLatestSnapshot(msg([txt("start")]));
    e.updateLatestSnapshot(msg([txt("start"), tool("t1", "read"), txt("end")]));
    expect(e.getBufferSize()).toBe(3);

    // The cursor was at the end of "start" (isTailFullyRendered=true),
    // so "end" was already fully visible. advanceCursor must not regress it.
    const r = e.advanceCursor(1)!;
    expect(r.content).toHaveLength(3);
    expect(r.content[0].type).toBe("text");
    expect(r.content[1].type).toBe("tool_use");
    expect(r.content[2].type).toBe("text");
    expect(r.content[2].text).toBe("end");
  });

  it("advanceCursor works across multiple text blocks preserving visible content", () => {
    const e = new StreamingEngine();
    e.updateLatestSnapshot(msg([txt("aaa")]));
    e.updateLatestSnapshot(msg([txt("aaa"), txt("bbb")]));
    // "bbb" was already visible (cursor at end of "aaa", isTailFullyRendered=true).
    // Buffer counts the text but advanceCursor should skip already-visible chars.
    expect(e.getBufferSize()).toBe(3);
    e.advanceCursor(2);
    expect(e.getBufferSize()).toBe(0);
  });

  it("getBufferSize returns 0 with no snapshot", () => {
    expect(new StreamingEngine().getBufferSize()).toBe(0);
  });

  it("getBufferSize returns 0 when flushed", () => {
    const e = new StreamingEngine();
    e.updateLatestSnapshot(msg([txt("hello")]));
    e.flush();
    expect(e.getBufferSize()).toBe(0);
  });

  it("getBufferSize counts unrevealed chars", () => {
    const e = new StreamingEngine();
    e.updateLatestSnapshot(msg([txt("ab")]));
    e.updateLatestSnapshot(msg([txt("abcde")]));
    expect(e.getBufferSize()).toBe(3);
    e.advanceCursor(1);
    expect(e.getBufferSize()).toBe(2);
  });

  it("peekSnapshot returns latest snapshot", () => {
    const e = new StreamingEngine();
    expect(e.peekSnapshot()).toBeNull();
    const m = msg([txt("test")]);
    e.updateLatestSnapshot(m);
    expect(e.peekSnapshot()).toBe(m);
  });

  it("peekCursor returns cursor position", () => {
    const e = new StreamingEngine();
    expect(e.peekCursor().blockIndex).toBeNull();
    e.updateLatestSnapshot(msg([txt("test")]));
    expect(e.peekCursor()).toEqual({ blockIndex: 0, offset: 4 });
  });

  it("resets cursor when snapshot becomes null", () => {
    const e = new StreamingEngine();
    e.updateLatestSnapshot(msg([txt("hi")]));
    e.updateLatestSnapshot(null);
    expect(e.getBufferSize()).toBe(0);
    expect(e.peekCursor().blockIndex).toBeNull();
  });

  it("handles empty content array", () => {
    const e = new StreamingEngine();
    const r = e.updateLatestSnapshot(msg([]));
    expect(r).not.toBeNull();
    expect(r!.content).toHaveLength(0);
  });

  describe("content regression during block transitions", () => {
    it("does not regress visible text when cursor transitions between consecutive text blocks", () => {
      const e = new StreamingEngine();
      e.updateLatestSnapshot(msg([txt("AB")]));
      // Cursor aligned to end of "AB" (block 0, offset 2)

      e.updateLatestSnapshot(msg([txt("AB"), txt("CD")]));
      // Cursor still at block 0, offset 2. Buffer = 2 ("CD").

      // At cursor end, isTailFullyRendered=true so materialize shows all content
      const before = e.advanceCursor(0)!;
      expect(visibleText(before)).toBe("ABCD");

      // Advancing should not decrease visible text
      const after = e.advanceCursor(1)!;
      expect(visibleText(after)).toBe("ABCD");
    });

    it("does not regress visible text when transitioning through non-text blocks to text", () => {
      const e = new StreamingEngine();
      e.updateLatestSnapshot(msg([txt("Hello")]));
      // Cursor at block 0, offset 5

      e.updateLatestSnapshot(msg([txt("Hello"), tool("t1", "read"), txt("World")]));
      // Cursor at block 0, offset 5. Buffer = 5 ("World").

      // At cursor end, all subsequent blocks (tool + text) are visible
      const before = visibleText(e.advanceCursor(0));
      expect(before).toBe("HelloWorld");

      // Advancing should not decrease visible text
      const after = visibleText(e.advanceCursor(1));
      expect(after).toBe("HelloWorld");
    });

    it("drains only NEW text that arrives after a block transition", () => {
      const e = new StreamingEngine();
      e.updateLatestSnapshot(msg([txt("Hello")]));
      e.updateLatestSnapshot(msg([txt("Hello"), tool("t1", "read"), txt("World")]));

      // Drain all buffer
      e.advanceCursor(1000);
      expect(e.getBufferSize()).toBe(0);
      expect(visibleText(e.advanceCursor(0))).toBe("HelloWorld");

      // Now new text arrives extending the last block
      e.updateLatestSnapshot(msg([txt("Hello"), tool("t1", "read"), txt("World!!!")]));
      expect(e.getBufferSize()).toBe(3);

      // Draining 1 char should show "World!" not regress to "W!"
      const r = e.advanceCursor(1)!;
      expect(visibleText(r)).toBe("HelloWorld!");
    });
  });

  describe("block visibility during text growth", () => {
    it("does not hide subsequent blocks when cursor text block grows", () => {
      const e = new StreamingEngine();
      // Initial: text only, cursor aligned to end
      e.updateLatestSnapshot(msg([txt("Hello")]));

      // Tool appears after text — cursor at (0,5), isTailFullyRendered=true
      e.updateLatestSnapshot(msg([txt("Hello"), tool("t1", "read")]));
      const withTool = e.advanceCursor(0)!;
      expect(withTool.content).toHaveLength(2);
      expect(withTool.content[1].type).toBe("tool_use");

      // Text block grows while tool already exists
      e.updateLatestSnapshot(msg([txt("Hello World"), tool("t1", "read")]));

      // Tool should remain visible even though cursor is mid-text in block 0
      const afterGrow = e.advanceCursor(0)!;
      expect(afterGrow.content).toHaveLength(2);
      expect(afterGrow.content[0].text).toBe("Hello");
      expect(afterGrow.content[1].type).toBe("tool_use");
    });

    it("keeps tool and trailing text visible when cursor text block grows", () => {
      const e = new StreamingEngine();
      e.updateLatestSnapshot(msg([txt("Hello")]));

      // Tool + trailing text appear
      e.updateLatestSnapshot(msg([txt("Hello"), tool("t1", "read"), txt("Result")]));
      const before = e.advanceCursor(0)!;
      expect(before.content).toHaveLength(3);

      // First text block grows
      e.updateLatestSnapshot(msg([txt("Hello World"), tool("t1", "read"), txt("Result")]));

      // All blocks should remain visible; only cursor text is truncated
      const after = e.advanceCursor(0)!;
      expect(after.content).toHaveLength(3);
      expect(after.content[0].text).toBe("Hello");
      expect(after.content[1].type).toBe("tool_use");
      expect(after.content[2].text).toBe("Result");
    });

    it("keeps blocks visible during incremental cursor advancement", () => {
      const e = new StreamingEngine();
      e.updateLatestSnapshot(msg([txt("Hello")]));
      e.updateLatestSnapshot(msg([txt("Hello"), tool("t1", "read")]));

      // Text grows
      e.updateLatestSnapshot(msg([txt("Hello World"), tool("t1", "read")]));

      // Each cursor step should keep the tool visible
      const step1 = e.advanceCursor(3)!;
      expect(step1.content).toHaveLength(2);
      expect(step1.content[0].text).toBe("Hello Wo");
      expect(step1.content[1].type).toBe("tool_use");

      const step2 = e.advanceCursor(3)!;
      expect(step2.content).toHaveLength(2);
      expect(step2.content[0].text).toBe("Hello World");
      expect(step2.content[1].type).toBe("tool_use");
    });
  });

  describe("content regression on block reorder", () => {
    it("does not hide already-visible text when a block is inserted before the cursor", () => {
      const e = new StreamingEngine();
      // Fully reveal a first block...
      e.updateLatestSnapshot(msg([txt("0123456789")]));
      // ...then a trailing text block, and drain everything so all of it is visible.
      e.updateLatestSnapshot(msg([txt("0123456789"), txt("ABCDE")]));
      e.advanceCursor(1000);
      expect(visibleText(e.advanceCursor(0))).toBe("0123456789ABCDE");

      // The backend now REORDERS content: a new block is inserted before the
      // cursor's block. This mirrors output_processor._materialize_content splicing
      // an extracted <img> FileBlock (and the text after it) in front of an
      // already-streamed block, which shifts every later block's index.
      //
      // The cursor is tracked by (blockIndex, offset) — position, not identity —
      // so it now points at a DIFFERENT, longer block. The engine's invariant is
      // that already-visible content is never regressed, so neither previously
      // fully-revealed block may disappear.
      const after = e.updateLatestSnapshot(msg([txt("XY"), txt("0123456789"), txt("ABCDE")]));

      expect(visibleText(after)).toContain("0123456789");
      expect(visibleText(after)).toContain("ABCDE");
    });
  });
});
