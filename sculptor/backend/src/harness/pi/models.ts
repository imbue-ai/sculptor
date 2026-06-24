// Pi model-catalog curation, ported from `pi_agent/agent_wrapper.py`
// (`_model_option_from_pi`, `_curate_models`, `_model_sort_key`). Pi reports a
// raw catalog at start; the switcher offers the curated, newest-first subset.

export interface ModelOption {
  provider: string;
  model_id: string;
  display_name: string;
}

// The pre-4 claude-3-* family the live Anthropic catalog still lists but the
// switcher must not offer.
const PI_MODEL_BLACKLIST: ReadonlySet<string> = new Set([
  "claude-3-5-haiku-20241022",
  "claude-3-5-haiku-latest",
  "claude-3-5-sonnet-20240620",
  "claude-3-5-sonnet-20241022",
  "claude-3-5-sonnet-latest",
  "claude-3-7-sonnet-20250219",
  "claude-3-7-sonnet-latest",
  "claude-3-haiku-20240307",
  "claude-3-opus-20240229",
  "claude-3-opus-latest",
  "claude-3-sonnet-20240229",
]);

const DATED_PIN_SUFFIX_RE = /-\d{8}$/;
const MODEL_VERSION_RE = /-(\d+)-(\d+)$/;

// Map one pi Model dict to a ModelOption, or null when `id` is missing.
export function modelOptionFromPi(raw: unknown): ModelOption | null {
  if (typeof raw !== "object" || raw === null) {
    return null;
  }
  const r = raw as Record<string, unknown>;
  if (typeof r.id !== "string" || !r.id) {
    return null;
  }
  return {
    provider:
      typeof r.provider === "string" && r.provider ? r.provider : "anthropic",
    model_id: r.id,
    display_name: typeof r.name === "string" && r.name ? r.name : r.id,
  };
}

function sortKey(model: ModelOption): [number, number, string] {
  const match = MODEL_VERSION_RE.exec(model.model_id);
  if (match === null) {
    return [1, 0, model.model_id];
  }
  return [-Number(match[1]), -Number(match[2]), model.model_id];
}

function compareModels(a: ModelOption, b: ModelOption): number {
  const ka = sortKey(a);
  const kb = sortKey(b);
  if (ka[0] !== kb[0]) {
    return ka[0] - kb[0];
  }
  if (ka[1] !== kb[1]) {
    return ka[1] - kb[1];
  }
  return ka[2] < kb[2] ? -1 : ka[2] > kb[2] ? 1 : 0;
}

// Trim pi's raw catalog to the offered set, newest-first. Drops blacklisted ids
// and dated-pin duplicates (keeping the current model regardless), de-dupes
// first-wins. Mirrors `_curate_models`.
export function curateModels(
  models: ModelOption[],
  currentModel: ModelOption | null,
): ModelOption[] {
  const kept: ModelOption[] = [];
  const seenIds = new Set<string>();
  const currentId = currentModel?.model_id ?? null;
  for (const model of models) {
    if (seenIds.has(model.model_id)) {
      continue;
    }
    const isCurrent = model.model_id === currentId;
    if (!isCurrent && PI_MODEL_BLACKLIST.has(model.model_id)) {
      continue;
    }
    if (!isCurrent && DATED_PIN_SUFFIX_RE.test(model.model_id)) {
      continue;
    }
    seenIds.add(model.model_id);
    kept.push(model);
  }
  if (currentModel !== null && currentId !== null && !seenIds.has(currentId)) {
    kept.push(currentModel);
  }
  return kept.sort(compareModels);
}
