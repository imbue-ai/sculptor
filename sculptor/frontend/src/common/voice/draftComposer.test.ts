import { describe, expect, it } from "vitest";

import { createVoiceDraftComposer } from "./draftComposer.ts";

describe("createVoiceDraftComposer", () => {
  it("captures the base on the first preview and replaces the tail on later ones", () => {
    const composer = createVoiceDraftComposer();
    expect(composer.previewText("draft", "hello")).toBe("draft hello");
    // Later previews ignore the (now preview-bearing) current draft.
    expect(composer.previewText("draft hello", "hello there")).toBe("draft hello there");
  });

  it("commits base + final and ends the utterance", () => {
    const composer = createVoiceDraftComposer();
    composer.previewText("draft", "hel");
    expect(composer.commitText("draft hel", "hello world")).toBe("draft hello world");
    // The next utterance captures a fresh base.
    expect(composer.previewText("draft hello world", "again")).toBe("draft hello world again");
  });

  it("commits against the current draft when no preview was shown", () => {
    const composer = createVoiceDraftComposer();
    expect(composer.commitText("draft", "hello")).toBe("draft hello");
  });

  it("restores the base on discard once, and only when a preview was shown", () => {
    const composer = createVoiceDraftComposer();
    expect(composer.discard()).toBeNull();
    composer.previewText("draft", "ghost");
    expect(composer.discard()).toBe("draft");
    expect(composer.discard()).toBeNull();
  });
});
