import type { VoiceEngine, VoiceEngineEvents } from "~/common/voice/types";

export type VoiceEngineModule = { createVoiceEngine: (events: VoiceEngineEvents) => VoiceEngine };

/**
 * Lazily load the on-device speech engine. Isolated in its own module so the
 * (large) engine runtime and its `import()` stay off the initial bundle and out
 * of every consumer's static dependency graph — the mic button only pulls it in
 * once the user actually starts dictation. Tests mock this loader so the button /
 * hook can be exercised without the real engine module.
 */
export const loadVoiceEngine = (): Promise<VoiceEngineModule> => import("~/common/voice/engine");
