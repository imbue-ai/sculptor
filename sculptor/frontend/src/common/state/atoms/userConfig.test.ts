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

  it("turns a configured 200K variant into its 1M sibling for new agents", () => {
    const store = createStore();
    store.set(userConfigAtom, { defaultLlm: LlmModel.CLAUDE_5_OPUS_200K } as never);
    expect(store.get(defaultModelAtom)).toBe(LlmModel.CLAUDE_5_OPUS);
  });
});

describe("configuredDefaultModelAtom", () => {
  it("reads a configured 200K variant as its 1M sibling, the model new agents get", () => {
    const store = createStore();
    store.set(userConfigAtom, { defaultLlm: LlmModel.CLAUDE_5_5_OPUS_200K } as never);
    expect(store.get(configuredDefaultModelAtom)).toBe(LlmModel.CLAUDE_5_5_OPUS);
  });

  it("treats a configured value that is no longer a known model as unset", () => {
    const store = createStore();
    store.set(userConfigAtom, { defaultLlm: "CLAUDE-3-OPUS" } as never);
    expect(store.get(configuredDefaultModelAtom)).toBeNull();
  });
});
