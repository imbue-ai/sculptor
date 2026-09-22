import { createStore } from "jotai";
import { describe, expect, it } from "vitest";

import { LlmModel } from "../../../api";
import { configuredDefaultModelAtom, defaultModelAtom, lastUsedModelAtom, userConfigAtom } from "./userConfig";

describe("defaultModelAtom", () => {
  it("falls back to the pinned 1M Opus when nothing is configured or remembered", () => {
    const store = createStore();
    expect(store.get(configuredDefaultModelAtom)).toBeNull();
    expect(store.get(defaultModelAtom)).toBe(LlmModel.CLAUDE_5_5_OPUS);
  });

  it("prefers a remembered selection over the fallback", () => {
    const store = createStore();
    store.set(lastUsedModelAtom, LlmModel.CLAUDE_FABLE_5_1);
    expect(store.get(defaultModelAtom)).toBe(LlmModel.CLAUDE_FABLE_5_1);
  });

  it("ignores a remembered value that is no longer a known model", () => {
    const store = createStore();
    store.set(lastUsedModelAtom, "CLAUDE-3-OPUS");
    expect(store.get(defaultModelAtom)).toBe(LlmModel.CLAUDE_5_5_OPUS);
  });

  it("prefers an explicitly configured default over a remembered selection", () => {
    const store = createStore();
    store.set(lastUsedModelAtom, LlmModel.CLAUDE_FABLE_5_1);
    store.set(userConfigAtom, { defaultLlm: LlmModel.CLAUDE_4_HAIKU } as never);
    expect(store.get(defaultModelAtom)).toBe(LlmModel.CLAUDE_4_HAIKU);
  });
});
