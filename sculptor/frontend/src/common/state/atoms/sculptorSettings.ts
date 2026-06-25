import { atom } from "jotai";

import type { SculptorSettings } from "../../../api";

export const sculptorSettingsAtom = atom<SculptorSettings | null>(null);

// Whether integration-testing mode is enabled. A narrow selector so consumers
// re-render only when this flag flips, not on every settings change.
export const isIntegrationTestingEnabledAtom = atom(
  (get) => get(sculptorSettingsAtom)?.TESTING?.INTEGRATION_ENABLED ?? false,
);
