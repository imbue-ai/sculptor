import { BUILTIN_SCULPTOR_ACTIONS } from "~/common/builtinActions.ts";

/**
 * The prompt the empty first-run form starts with (FIRST-04): the same
 * `/sculptor:help` slash command the built-in `/help` action sends, so a
 * brand-new user's very first workspace lands them in the help flow. Sourced
 * from `BUILTIN_SCULPTOR_ACTIONS` rather than hardcoded so the two can never
 * drift — if the built-in `/help` prompt changes, this follows.
 */
const HELP_ACTION_NAME = "/help";

export const HOME_PROMPT_PREFILL: string =
  BUILTIN_SCULPTOR_ACTIONS.find((action) => action.name === HELP_ACTION_NAME)?.prompt ?? "/sculptor:help";
