import { afterEach, describe, expect, it, vi } from "vitest";

import { BUILTIN_SCULPTOR_ACTIONS } from "~/common/builtinActions.ts";

import { HOME_PROMPT_PREFILL } from "./homePromptPrefill.ts";

describe("HOME_PROMPT_PREFILL", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("leads with the built-in /help action prompt, so the command never drifts", () => {
    const help = BUILTIN_SCULPTOR_ACTIONS.find((action) => action.name === "/help");
    expect(help).toBeDefined();
    expect(HOME_PROMPT_PREFILL.startsWith(`${help?.prompt} `)).toBe(true);
  });

  it("is the sculptor help command plus the onboarding question for users and tests", () => {
    expect(HOME_PROMPT_PREFILL).toBe(
      "/sculptor:help I just set up Sculptor for the first time. What should I know to get started?",
    );
  });

  it("is empty in the from-source dev app (SCULPTOR_EMPTY_FIRST_RUN_PROMPT set)", async () => {
    vi.stubEnv("SCULPTOR_EMPTY_FIRST_RUN_PROMPT", "1");
    vi.resetModules();
    const { HOME_PROMPT_PREFILL: devPrefill } = await import("./homePromptPrefill.ts");
    expect(devPrefill).toBe("");
  });
});
