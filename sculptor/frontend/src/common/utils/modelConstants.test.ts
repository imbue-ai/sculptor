import { describe, expect, it } from "vitest";

import { LlmModel } from "~/api";

import { getModelCapabilities } from "./modelCapabilities";
import {
  DEFAULT_LLM_MODEL,
  getModelLongName,
  getModelShortName,
  modelForNewRecord,
  PRODUCTION_MODELS,
} from "./modelConstants";

describe("Opus 5.5", () => {
  it("is labelled by its pinned generation, with no context suffix on either member", () => {
    for (const model of [LlmModel.CLAUDE_5_5_OPUS, LlmModel.CLAUDE_5_5_OPUS_200K]) {
      expect(getModelShortName(model)).toBe("Opus 5.5");
      expect(getModelLongName(model)).toBe("Claude 5.5 Opus");
    }
  });

  it("supports fast mode and file attachments", () => {
    for (const model of [LlmModel.CLAUDE_5_5_OPUS, LlmModel.CLAUDE_5_5_OPUS_200K]) {
      expect(getModelCapabilities(model)).toEqual({ supportsFastMode: true, supportsFileAttachments: true });
    }
  });

  it("leads the Opus block in the picker without displacing Fable", () => {
    const opusStart = PRODUCTION_MODELS.indexOf(LlmModel.CLAUDE_5_5_OPUS);
    expect(opusStart).toBeGreaterThan(PRODUCTION_MODELS.indexOf(LlmModel.CLAUDE_FABLE_5_1));
    expect(PRODUCTION_MODELS.indexOf(LlmModel.CLAUDE_5_OPUS)).toBe(opusStart + 1);
  });
});

describe("the picker", () => {
  it("offers one accurately labelled entry per current model", () => {
    expect(PRODUCTION_MODELS.map(getModelLongName)).toEqual([
      "Fable 5.2",
      "Fable 5.1",
      "Claude 5.5 Opus",
      "Claude 5 Opus",
      "Claude 4.8 Opus",
      "Claude 5.5 Sonnet",
      "Claude 5.5 Haiku",
    ]);
  });

  it("offers no 200K member, since from Opus 4.7 on those ids run the same 1M window", () => {
    expect(PRODUCTION_MODELS.filter((model) => model.endsWith("-200K"))).toEqual([]);
  });
});

describe("Sonnet 5.5 and Haiku 5.5", () => {
  it("are labelled by their pinned generation, with no 1M variant", () => {
    expect(getModelShortName(LlmModel.CLAUDE_5_5_SONNET)).toBe("Sonnet 5.5");
    expect(getModelLongName(LlmModel.CLAUDE_5_5_SONNET)).toBe("Claude 5.5 Sonnet");
    expect(getModelShortName(LlmModel.CLAUDE_5_5_HAIKU)).toBe("Haiku 5.5");
    expect(getModelLongName(LlmModel.CLAUDE_5_5_HAIKU)).toBe("Claude 5.5 Haiku");
  });

  it("support file attachments but not fast mode", () => {
    for (const model of [LlmModel.CLAUDE_5_5_SONNET, LlmModel.CLAUDE_5_5_HAIKU]) {
      expect(getModelCapabilities(model)).toEqual({ supportsFastMode: false, supportsFileAttachments: true });
    }
  });

  it("follow the Opus block in the picker, Sonnet before Haiku", () => {
    expect(PRODUCTION_MODELS.slice(-2)).toEqual([LlmModel.CLAUDE_5_5_SONNET, LlmModel.CLAUDE_5_5_HAIKU]);
  });
});

describe("retired models", () => {
  it("keeps Opus 4.7 out of the picker while leaving it selectable by a stored value", () => {
    expect(PRODUCTION_MODELS).not.toContain(LlmModel.CLAUDE_4_7_OPUS);
    expect(PRODUCTION_MODELS).not.toContain(LlmModel.CLAUDE_4_7_OPUS_200K);
    expect(getModelShortName(LlmModel.CLAUDE_4_7_OPUS_200K)).toBe("Opus 4.7");
  });

  it("keeps the rolling Sonnet and Haiku aliases out of the picker, labelled as rolling", () => {
    for (const model of [LlmModel.CLAUDE_4_SONNET, LlmModel.CLAUDE_4_SONNET_200K, LlmModel.CLAUDE_4_HAIKU]) {
      expect(PRODUCTION_MODELS).not.toContain(model);
      expect(getModelLongName(model)).toMatch(/\(latest/);
    }
  });
});

// The rolling "latest Opus" alias launches whatever the Claude CLI treats as newest,
// so it never counts as a pinned generation.
const ROLLING_OPUS_ALIASES: ReadonlyArray<string> = ["CLAUDE_4_OPUS"];

const compareVersions = (a: ReadonlyArray<number>, b: ReadonlyArray<number>): number => {
  for (let index = 0; index < Math.max(a.length, b.length); index += 1) {
    const difference = (a[index] ?? 0) - (b[index] ?? 0);
    if (difference !== 0) {
      return difference;
    }
  }
  return 0;
};

const newestPinnedOpus = (): LlmModel => {
  const pinned = Object.entries(LlmModel).flatMap(([name, model]) => {
    const match = /^CLAUDE_(\d+(?:_\d+)*)_OPUS$/.exec(name);
    if (match === null || ROLLING_OPUS_ALIASES.includes(name)) {
      return [];
    }
    return [{ model, version: match[1].split("_").map(Number) }];
  });
  const [newest] = pinned.sort((a, b) => compareVersions(b.version, a.version));
  return newest.model;
};

describe("DEFAULT_LLM_MODEL", () => {
  it("names the newest pinned Opus, so an Opus release that forgets to repoint it fails here", () => {
    expect(DEFAULT_LLM_MODEL).toBe(newestPinnedOpus());
  });

  it("is a model the picker offers", () => {
    // A default the picker does not list is a selection the user cannot get back to
    // after switching away from it.
    expect(PRODUCTION_MODELS).toContain(DEFAULT_LLM_MODEL);
  });

  it("supports the capabilities a default needs", () => {
    expect(getModelCapabilities(DEFAULT_LLM_MODEL)).toEqual({
      supportsFastMode: true,
      supportsFileAttachments: true,
    });
  });
});

describe("modelForNewRecord", () => {
  const all = Object.values(LlmModel);

  it.each(all.filter((model) => model.endsWith("-200K")))("stores %s as its 1M sibling", (model) => {
    const sibling = modelForNewRecord(model);
    expect(sibling).toBe(model.replace(/-200K$/, ""));
    expect(all).toContain(sibling);
  });

  it.each(all.filter((model) => !model.endsWith("-200K")))("leaves %s unchanged", (model) => {
    expect(modelForNewRecord(model)).toBe(model);
  });
});
