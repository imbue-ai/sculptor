import type { SculptorSettings } from "../../api";
import type { NewWorkspaceModalEntrySource } from "./atoms.ts";

/**
 * Editable prefill for the inline Home form's prompt, shown the first time a
 * user lands on an empty Home. It is a normal draft value — the user can edit
 * or clear it, and an untouched prefill is still only sent if it's non-empty —
 * so this just lowers the activation energy of asking for help; it never sends
 * on the user's behalf.
 */
export const HOME_PROMPT_PREFILL =
  "/sculptor:help I just set up Sculptor for the first time. What should I know to get started?";

/**
 * Whether the inline Home form should apply {@link HOME_PROMPT_PREFILL} to its
 * prompt right now. The prefill is:
 *  - only for the inline "home" entry source (the modal never prefills),
 *  - one-shot per mount (`hasAlreadyPrefilled` is a per-mount ref) so a user
 *    who edits or clears it makes the change stick — we never re-apply on
 *    emptiness alone,
 *  - gated off under integration tests, deciding only once `settings` has
 *    loaded so we don't prefill in the window before the deterministic suites
 *    flip INTEGRATION_ENABLED on.
 */
export const shouldPrefillHomePrompt = (inputs: {
  entrySource: NewWorkspaceModalEntrySource;
  settings: SculptorSettings | null;
  hasAlreadyPrefilled: boolean;
}): boolean => {
  if (inputs.entrySource !== "home") return false;
  if (inputs.hasAlreadyPrefilled) return false;
  if (inputs.settings === null) return false;
  if (inputs.settings.TESTING?.INTEGRATION_ENABLED === true) return false;
  return true;
};
