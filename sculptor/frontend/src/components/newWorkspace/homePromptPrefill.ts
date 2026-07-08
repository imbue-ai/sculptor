import { BUILTIN_SCULPTOR_ACTIONS } from "~/common/builtinActions.ts";

// Built-in action whose slash command the first-run prompt leads with.
const HELP_ACTION_NAME = "/help";

// Plain-language onboarding question appended after the `/help` command, so the
// first-run prompt reads like a real question a brand-new user would ask.
const ONBOARDING_QUESTION = "I just set up Sculptor for the first time. What should I know to get started?";

// The `/sculptor:help` slash command (sourced from the built-in `/help` action
// so the command can never drift) followed by the onboarding question, e.g.
// `/sculptor:help I just set up Sculptor for the first time. What should I know to get started?`.
const HELP_PROMPT_PREFILL: string = `${
  BUILTIN_SCULPTOR_ACTIONS.find((action) => action.name === HELP_ACTION_NAME)?.prompt ?? "/sculptor:help"
} ${ONBOARDING_QUESTION}`;

/**
 * The prompt the first-run auto-opened new-workspace dialog starts with. For
 * real (packaged) users and in tests this is the `/sculptor:help` onboarding
 * prompt, which lands a brand-new user's very first workspace in the help flow
 * with context about who is asking.
 *
 * The from-source dev app starts it empty instead so QA can type immediately:
 * `just frontend` sets `SCULPTOR_EMPTY_FIRST_RUN_PROMPT`, which Vite exposes here
 * via the `SCULPTOR_` env prefix. The test harness launches the frontend without
 * that flag, so tests keep the onboarding prompt.
 */
export const HOME_PROMPT_PREFILL: string = import.meta.env.SCULPTOR_EMPTY_FIRST_RUN_PROMPT ? "" : HELP_PROMPT_PREFILL;
