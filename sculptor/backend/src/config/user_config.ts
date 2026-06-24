import { createHash, randomBytes } from "node:crypto";
import { existsSync } from "node:fs";

import { configPath } from "~/config/sculptor_folder";
import {
  loadSettings,
  saveSettings,
  UserConfigSchema,
  type UserConfig,
} from "~/config/settings";

// The user-config service: the TS equivalent of
// sculptor/sculptor/services/user_config/user_config.py. config.toml is the
// source of truth (REQ-DATA-002); the in-memory "current config" is re-derived
// from disk on each read and persisted on each write, so the observable
// behavior matches Python's global-instance model without mutable module state.
//
// Internally UserConfig is snake_case (the on-disk + service representation,
// settings.ts). The HTTP API serializes it camelCase (Pydantic's
// alias_generator=to_camel); userConfigToWire / wirePartialToInternal are that
// boundary (RW-API-3).

// A per-process random id identifying this run of Sculptor. Mirrors
// _EXECUTION_INSTANCE_ID; used as the anonymous user's identity before
// onboarding writes a real one.
const EXECUTION_INSTANCE_ID = createHash("md5")
  .update(randomBytes(32))
  .digest("hex");

export function getExecutionInstanceId(): string {
  return EXECUTION_INSTANCE_ID;
}

// ids.py: a user/org id is the md5 of the (namespaced) email.
export function createUserId(email: string): string {
  return createHash("md5").update(email).digest("hex");
}

export function createOrganizationId(email: string): string {
  return createHash("md5").update(`organization:${email}`).digest("hex");
}

export interface PrivacySettings {
  is_error_reporting_enabled: boolean;
  is_product_analytics_enabled: boolean;
  is_session_recording_enabled: boolean;
}

// Telemetry consent is binary: either the SDK-facing flags are on or everything
// is off. Session recording is always off (no user-facing toggle).
export const TELEMETRY_ENABLED_PRIVACY_SETTINGS: PrivacySettings = {
  is_error_reporting_enabled: true,
  is_product_analytics_enabled: true,
  is_session_recording_enabled: false,
};

export const TELEMETRY_DISABLED_PRIVACY_SETTINGS: PrivacySettings = {
  is_error_reporting_enabled: false,
  is_product_analytics_enabled: false,
  is_session_recording_enabled: false,
};

export function getPrivacySettingsForTelemetry(
  isEnabled: boolean,
): PrivacySettings {
  return isEnabled
    ? TELEMETRY_ENABLED_PRIVACY_SETTINGS
    : TELEMETRY_DISABLED_PRIVACY_SETTINGS;
}

// startup_checks.check_is_user_email_field_valid: a loose ".@..." shape.
export function checkIsUserEmailFieldValid(config: UserConfig): boolean {
  return /^[^@]+@[^@]+\.[^@]+$/.test(config.user_email);
}

// canonicalize_telemetry_flags: collapse a mixed consent (the two SDK flags
// disagree — only possible from old/hand-edited files) back to all-off, the
// conservative direction.
export function canonicalizeTelemetryFlags(config: UserConfig): UserConfig {
  if (
    config.is_error_reporting_enabled === config.is_product_analytics_enabled
  ) {
    return config;
  }
  return { ...config, ...TELEMETRY_DISABLED_PRIVACY_SETTINGS };
}

// _generate_default_user_config_instance: the anonymized config used before
// onboarding — execution-instance identity, consent not yet given, telemetry at
// the default (enabled) level.
export function defaultAnonymousUserConfig(): UserConfig {
  return UserConfigSchema.parse({
    user_email: "",
    user_id: EXECUTION_INSTANCE_ID,
    organization_id: EXECUTION_INSTANCE_ID,
    instance_id: EXECUTION_INSTANCE_ID,
    is_privacy_policy_consented: false,
    is_telemetry_level_set: false,
    ...TELEMETRY_ENABLED_PRIVACY_SETTINGS,
  });
}

// Whether onboarding has run (config.toml exists). Mirrors initialize_from_file
// returning False when no file is present.
export function isUserConfigInitialized(file: string = configPath()): boolean {
  return existsSync(file);
}

// get_user_config_instance (never null): the loaded, canonicalized config when
// config.toml exists, else the anonymous default. load_config injects the
// execution instance id when the file omits one.
export function getCurrentUserConfig(file: string = configPath()): UserConfig {
  if (!existsSync(file)) {
    return defaultAnonymousUserConfig();
  }
  let config = loadSettings(file);
  if (config.instance_id === "") {
    config = { ...config, instance_id: EXECUTION_INSTANCE_ID };
  }
  return canonicalizeTelemetryFlags(config);
}

export function saveUserConfig(
  config: UserConfig,
  file: string = configPath(),
): void {
  saveSettings(config, file);
}

// --- snake_case (internal) <-> camelCase (wire) boundary --------------------
//
// Pydantic's alias_generator=to_camel aliases model field names but NOT the
// keys of plain dict fields. `keybindings` is a dict[str, str | None] whose keys
// are user-facing action ids (data, not field names), so its mapping is carried
// through verbatim; every other nested object is a model and is converted.

const OPAQUE_DICT_FIELDS: ReadonlySet<string> = new Set(["keybindings"]);

export function toCamelKey(key: string): string {
  return key.replace(/_([a-z0-9])/g, (_match, char: string) =>
    char.toUpperCase(),
  );
}

export function toSnakeKey(key: string): string {
  return key.replace(/[A-Z]/g, (char) => `_${char.toLowerCase()}`);
}

function convertKeys(value: unknown, keyFn: (key: string) => string): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => convertKeys(item, keyFn));
  }
  if (value !== null && typeof value === "object") {
    const result: Record<string, unknown> = {};
    for (const [key, inner] of Object.entries(value)) {
      const converted = keyFn(key);
      // keybindings: keep the value (and its arbitrary keys) exactly as-is.
      result[converted] = OPAQUE_DICT_FIELDS.has(key)
        ? inner
        : convertKeys(inner, keyFn);
    }
    return result;
  }
  return value;
}

// Serialize the internal (snake_case) config to its camelCase wire shape.
export function userConfigToWire(config: UserConfig): Record<string, unknown> {
  return convertKeys(config, toCamelKey) as Record<string, unknown>;
}

// Convert a partial camelCase wire patch (the PUT /config body) back to the
// internal snake_case keys, so it can be merged onto the current config.
export function wirePartialToInternal(
  partial: Record<string, unknown>,
): Record<string, unknown> {
  return convertKeys(partial, toSnakeKey) as Record<string, unknown>;
}
