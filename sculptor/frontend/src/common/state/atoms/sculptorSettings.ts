import { atom } from "jotai";

import type { SculptorSettings } from "../../../api";

export const sculptorSettingsAtom = atom<SculptorSettings | null>(null);

// Whether integration-testing mode is enabled. A narrow selector so consumers
// re-render only when this flag flips, not on every settings change.
export const isIntegrationTestingEnabledAtom = atom(
  (get) => get(sculptorSettingsAtom)?.TESTING?.INTEGRATION_ENABLED ?? false,
);

// The display-name override for the deterministic testing models (FakeClaude).
// When set, model labels render this value for those models and the picker
// hides them — lets a demo/screenshot harness present scripted agents under a
// custom name. Null (production and integration tests) keeps the real labels
// and picker entries.
export const fakeModelDisplayNameAtom = atom(
  (get) => get(sculptorSettingsAtom)?.TESTING?.FAKE_MODEL_DISPLAY_NAME ?? null,
);
