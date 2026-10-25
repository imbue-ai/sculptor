/**
 * Sculptor TrustedRouter provider extension.
 *
 * Registers `trustedrouter` as a pi provider: an OpenAI-compatible endpoint at
 * https://api.trustedrouter.com/v1 whose model list is read at startup from the
 * public, unauthenticated https://api.trustedrouter.com/v1/models (the same
 * OpenRouter-shaped document OpenRouter serves). Only models that accept tool
 * calls are registered, because every pi session drives tools.
 *
 * Authentication is pi's own: a key saved through Sculptor's Settings lands in
 * `auth.json` under `trustedrouter` and takes precedence; otherwise the
 * `TRUSTEDROUTER_API_KEY` environment variable is used. No secret is read,
 * logged, or embedded here, and the catalog fetch sends no credentials.
 *
 * Fail-soft: if the catalog cannot be fetched or parsed (offline, timeout,
 * unexpected shape), nothing is registered and pi starts normally; the provider
 * simply offers no models in that session.
 *
 * Pinned with the pi binary as one immutable unit (PI_VERSION_RANGE in
 * `dependency_management_service`) and loaded explicitly via `-e`.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const PROVIDER_ID = "trustedrouter";
const BASE_URL = "https://api.trustedrouter.com/v1";
const MODELS_URL = `${BASE_URL}/models`;
const CATALOG_TIMEOUT_MS = 8000;
const DEFAULT_MAX_TOKENS = 32768;

type CatalogModel = {
  id?: unknown;
  name?: unknown;
  context_length?: unknown;
  pricing?: Record<string, unknown>;
  architecture?: { input_modalities?: unknown };
  top_provider?: { max_completion_tokens?: unknown };
  supported_parameters?: unknown;
};

const perMillion = (value: unknown): number => {
  const parsed = typeof value === "string" || typeof value === "number" ? Number(value) : Number.NaN;
  return Number.isFinite(parsed) && parsed > 0 ? parsed * 1_000_000 : 0;
};

const positiveInt = (value: unknown): number | undefined =>
  typeof value === "number" && Number.isInteger(value) && value > 0 ? value : undefined;

export const toPiModels = (catalog: unknown) => {
  const rows = (catalog as { data?: unknown })?.data;
  if (!Array.isArray(rows)) return [];
  const models = [];
  for (const row of rows as CatalogModel[]) {
    const parameters = Array.isArray(row.supported_parameters) ? row.supported_parameters : [];
    if (typeof row.id !== "string" || !parameters.includes("tools")) continue;
    const modalities = Array.isArray(row.architecture?.input_modalities) ? row.architecture.input_modalities : [];
    const contextWindow = positiveInt(row.context_length) ?? 128000;
    const pricing = row.pricing ?? {};
    models.push({
      type: "chat" as const,
      id: row.id,
      name: typeof row.name === "string" ? row.name : row.id,
      reasoning: parameters.includes("reasoning"),
      input: modalities.includes("image") ? (["text", "image"] as const) : (["text"] as const),
      cost: {
        input: perMillion(pricing.prompt),
        output: perMillion(pricing.completion),
        cacheRead: perMillion(pricing.input_cache_read),
        cacheWrite: perMillion(pricing.input_cache_write),
      },
      contextWindow,
      maxTokens: positiveInt(row.top_provider?.max_completion_tokens) ?? Math.min(DEFAULT_MAX_TOKENS, contextWindow),
    });
  }
  return models;
};

export default async function sculptorTrustedRouterExtension(pi: ExtensionAPI): Promise<void> {
  let models: ReturnType<typeof toPiModels>;
  try {
    const response = await fetch(MODELS_URL, { signal: AbortSignal.timeout(CATALOG_TIMEOUT_MS) });
    if (!response.ok) return;
    models = toPiModels(await response.json());
  } catch {
    return;
  }
  if (models.length === 0) return;
  pi.registerProvider(PROVIDER_ID, {
    name: "TrustedRouter",
    baseUrl: BASE_URL,
    apiKey: "$TRUSTEDROUTER_API_KEY",
    api: "openai-completions",
    // TrustedRouter takes OpenRouter's request shape: the `reasoning` object
    // for thinking and `max_tokens` for the output cap.
    compat: { thinkingFormat: "openrouter", maxTokensField: "max_tokens" },
    models,
  });
}
