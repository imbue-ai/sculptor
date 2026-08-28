import type { Editor as TipTapEditor } from "@tiptap/react";
import { describe, expect, it } from "vitest";

import { parsePseudoSkillCommand } from "./pseudoSkills";

type FakeMentionNode = {
  type: { name: "mention" };
  attrs: { id: string; mentionSuggestionChar: string };
};
type FakeTextNode = { type: { name: "text" }; text: string };
type FakeChild = FakeMentionNode | FakeTextNode;

const fakeEditor = (children: Array<FakeChild>): TipTapEditor => {
  const paragraph = {
    childCount: children.length,
    child: (index: number): FakeChild => children[index],
  };
  const doc = {
    childCount: children.length === 0 ? 0 : 1,
    child: (_: number): typeof paragraph => paragraph,
  };
  return { state: { doc } } as unknown as TipTapEditor;
};

const emptyEditor = (): TipTapEditor => fakeEditor([]);

describe("parsePseudoSkillCommand", () => {
  describe("plain-text argless commands", () => {
    it("matches /clear exactly", () => {
      expect(parsePseudoSkillCommand(emptyEditor(), "/clear")).toEqual({ name: "clear", args: "" });
    });

    it("trims surrounding whitespace on /clear", () => {
      expect(parsePseudoSkillCommand(emptyEditor(), "   /clear   ")).toEqual({ name: "clear", args: "" });
    });

    it("matches /copy exactly", () => {
      expect(parsePseudoSkillCommand(emptyEditor(), "/copy")).toEqual({ name: "copy", args: "" });
    });

    it("rejects /clear followed by extra text", () => {
      expect(parsePseudoSkillCommand(emptyEditor(), "/clear the cache")).toBeNull();
    });

    it("rejects commands not at the start", () => {
      expect(parsePseudoSkillCommand(emptyEditor(), "please /clear")).toBeNull();
    });

    it("returns null for regular text", () => {
      expect(parsePseudoSkillCommand(emptyEditor(), "hello world")).toBeNull();
    });

    it("returns null for empty input", () => {
      expect(parsePseudoSkillCommand(emptyEditor(), "")).toBeNull();
    });
  });

  describe("plain-text arg-required commands (/btw)", () => {
    it("captures the argument text", () => {
      expect(parsePseudoSkillCommand(emptyEditor(), "/btw why did you pick X?")).toEqual({
        name: "btw",
        args: "why did you pick X?",
      });
    });

    it("returns empty args for bare /btw", () => {
      expect(parsePseudoSkillCommand(emptyEditor(), "/btw")).toEqual({ name: "btw", args: "" });
    });

    it("returns empty args for whitespace-only /btw", () => {
      expect(parsePseudoSkillCommand(emptyEditor(), "/btw   ")).toEqual({ name: "btw", args: "" });
    });

    it("accepts a tab separator", () => {
      expect(parsePseudoSkillCommand(emptyEditor(), "/btw\thello")).toEqual({ name: "btw", args: "hello" });
    });

    it("preserves inner and trailing whitespace", () => {
      expect(parsePseudoSkillCommand(emptyEditor(), "/btw   hello  ")).toEqual({ name: "btw", args: "hello" });
    });

    it("rejects /btw followed by non-whitespace", () => {
      expect(parsePseudoSkillCommand(emptyEditor(), "/btwfoo")).toBeNull();
    });

    it("rejects /btw2", () => {
      expect(parsePseudoSkillCommand(emptyEditor(), "/btw2")).toBeNull();
    });

    it("rejects /btw not at the start", () => {
      expect(parsePseudoSkillCommand(emptyEditor(), "hello /btw world")).toBeNull();
    });
  });

  describe("TipTap mention-node path", () => {
    it("recognizes a bare /btw mention", () => {
      const editor = fakeEditor([{ type: { name: "mention" }, attrs: { id: "/btw", mentionSuggestionChar: "/" } }]);
      expect(parsePseudoSkillCommand(editor, "")).toEqual({ name: "btw", args: "" });
    });

    it("concatenates trailing text nodes as args", () => {
      const editor = fakeEditor([
        { type: { name: "mention" }, attrs: { id: "/btw", mentionSuggestionChar: "/" } },
        { type: { name: "text" }, text: " why?" },
      ]);
      expect(parsePseudoSkillCommand(editor, "")).toEqual({ name: "btw", args: "why?" });
    });

    it("accepts argless /clear with the trailing space TipTap autocomplete inserts", () => {
      // Selecting `/clear` from the slash-menu autocomplete adds a trailing
      // space after the mention node.
      const editor = fakeEditor([
        { type: { name: "mention" }, attrs: { id: "/clear", mentionSuggestionChar: "/" } },
        { type: { name: "text" }, text: " " },
      ]);
      expect(parsePseudoSkillCommand(editor, "/clear ")).toEqual({ name: "clear", args: "" });
    });

    it("falls through to plain-text when argless /clear has extra non-whitespace trailing", () => {
      // Mixed input like "/clear the cache" should be sent as a regular
      // message — the mention-only path can't claim it, and the plain-text
      // path has no exact match for argless skills.
      const editor = fakeEditor([
        { type: { name: "mention" }, attrs: { id: "/clear", mentionSuggestionChar: "/" } },
        { type: { name: "text" }, text: " the cache" },
      ]);
      expect(parsePseudoSkillCommand(editor, "/clear the cache")).toBeNull();
    });

    it("matches bare /copy mention", () => {
      const editor = fakeEditor([{ type: { name: "mention" }, attrs: { id: "/copy", mentionSuggestionChar: "/" } }]);
      expect(parsePseudoSkillCommand(editor, "")).toEqual({ name: "copy", args: "" });
    });

    it("returns null for an unknown mention", () => {
      const editor = fakeEditor([{ type: { name: "mention" }, attrs: { id: "/unknown", mentionSuggestionChar: "/" } }]);
      expect(parsePseudoSkillCommand(editor, "")).toBeNull();
    });

    it("falls through to plain-text when first child is not a mention", () => {
      const editor = fakeEditor([{ type: { name: "text" }, text: "hello" }]);
      expect(parsePseudoSkillCommand(editor, "hello")).toBeNull();
    });
  });

  describe("case sensitivity", () => {
    it("rejects uppercase /BTW", () => {
      expect(parsePseudoSkillCommand(emptyEditor(), "/BTW hello")).toBeNull();
    });

    it("rejects mixed-case /Clear", () => {
      expect(parsePseudoSkillCommand(emptyEditor(), "/Clear")).toBeNull();
    });
  });
});
