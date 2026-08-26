import { describe, expect, it } from "vitest";

import { appendTranscript } from "~/common/voiceEntryText.ts";

describe("appendTranscript", () => {
  it("uses the trimmed segment as-is when the draft is empty", () => {
    expect(appendTranscript({ draft: "", segment: "  hello world  " })).toBe("hello world");
  });

  it("inserts a single separating space when the draft ends in a non-space", () => {
    expect(appendTranscript({ draft: "hello", segment: "world" })).toBe("hello world");
  });

  it("appends directly when the draft already ends in a space", () => {
    expect(appendTranscript({ draft: "hello ", segment: "world" })).toBe("hello world");
  });

  it("treats a trailing newline as whitespace and does not add a space", () => {
    expect(appendTranscript({ draft: "hello\n", segment: "world" })).toBe("hello\nworld");
  });

  it("adds no trailing whitespace so successive segments read naturally", () => {
    const once = appendTranscript({ draft: "one", segment: "two" });
    expect(appendTranscript({ draft: once, segment: "three" })).toBe("one two three");
  });

  it("leaves the draft untouched when the segment is blank", () => {
    expect(appendTranscript({ draft: "hello", segment: "   " })).toBe("hello");
    expect(appendTranscript({ draft: "", segment: "" })).toBe("");
  });
});
