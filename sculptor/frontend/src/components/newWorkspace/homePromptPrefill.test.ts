import { describe, expect, it } from "vitest";

import { BUILTIN_SCULPTOR_ACTIONS } from "~/common/utils/builtinActions.ts";

import { HOME_PROMPT_PREFILL } from "./homePromptPrefill.ts";

describe("HOME_PROMPT_PREFILL", () => {
  it("leads with the built-in /help action prompt, so the command never drifts", () => {
    const help = BUILTIN_SCULPTOR_ACTIONS.find((action) => action.name === "/help");
    expect(help).toBeDefined();
    expect(HOME_PROMPT_PREFILL.startsWith(`${help?.prompt} `)).toBe(true);
  });

  it("is the sculptor help command plus the onboarding question", () => {
    expect(HOME_PROMPT_PREFILL).toBe(
      "/sculptor:help I just set up Sculptor for the first time. What should I know to get started?",
    );
  });
});
