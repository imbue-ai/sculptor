import { describe, expect, it } from "vitest";

import { BUILTIN_SCULPTOR_ACTIONS } from "~/common/builtinActions.ts";

import { HOME_PROMPT_PREFILL } from "./homePromptPrefill.ts";

describe("HOME_PROMPT_PREFILL", () => {
  it("matches the built-in /help action prompt, so the two never drift", () => {
    const help = BUILTIN_SCULPTOR_ACTIONS.find((action) => action.name === "/help");
    expect(help).toBeDefined();
    expect(HOME_PROMPT_PREFILL).toBe(help?.prompt);
  });

  it("is the sculptor help slash command", () => {
    expect(HOME_PROMPT_PREFILL).toBe("/sculptor:help");
  });
});
