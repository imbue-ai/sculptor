from enum import StrEnum

from sculptor.foundation.pydantic_serialization import FrozenModel


class ProviderGroup(StrEnum):
    """How a pi provider's credentials are supplied.

    SINGLE_KEY providers are fully supported in v1: a single API key persisted in
    ``auth.json`` is enough to authenticate them. SESSION_ONLY providers draw extra
    values (region, base URL, account/gateway id, AWS profile) from the environment
    that are not expressible in ``auth.json`` alone, so v1 surfaces them as
    env-detected only.
    """

    SINGLE_KEY = "single_key"
    SESSION_ONLY = "session_only"


class ProviderCatalogEntry(FrozenModel):
    """One pi LLM provider: its identity, env vars, display name, and group.

    ``provider_id`` equals both the ``auth.json`` top-level key and the ``provider``
    field pi reports in ``get_available_models`` (e.g. Gemini is ``google``).
    ``env_var_names`` lists every conventional env var that authenticates the
    provider; the first is the canonical/primary one.
    """

    provider_id: str
    env_var_names: tuple[str, ...]
    display_name: str
    group: ProviderGroup
    is_subscription: bool


_PROVIDER_CATALOG: tuple[ProviderCatalogEntry, ...] = (
    ProviderCatalogEntry(
        provider_id="anthropic",
        env_var_names=("ANTHROPIC_API_KEY",),
        display_name="Anthropic",
        group=ProviderGroup.SINGLE_KEY,
        is_subscription=True,
    ),
    ProviderCatalogEntry(
        provider_id="openai",
        env_var_names=("OPENAI_API_KEY",),
        display_name="OpenAI",
        group=ProviderGroup.SINGLE_KEY,
        is_subscription=True,
    ),
    ProviderCatalogEntry(
        provider_id="google",
        env_var_names=("GEMINI_API_KEY",),
        display_name="Google",
        group=ProviderGroup.SINGLE_KEY,
        is_subscription=True,
    ),
    ProviderCatalogEntry(
        provider_id="deepseek",
        env_var_names=("DEEPSEEK_API_KEY",),
        display_name="DeepSeek",
        group=ProviderGroup.SINGLE_KEY,
        is_subscription=False,
    ),
    ProviderCatalogEntry(
        provider_id="mistral",
        env_var_names=("MISTRAL_API_KEY",),
        display_name="Mistral",
        group=ProviderGroup.SINGLE_KEY,
        is_subscription=False,
    ),
    ProviderCatalogEntry(
        provider_id="groq",
        env_var_names=("GROQ_API_KEY",),
        display_name="Groq",
        group=ProviderGroup.SINGLE_KEY,
        is_subscription=False,
    ),
    ProviderCatalogEntry(
        provider_id="cerebras",
        env_var_names=("CEREBRAS_API_KEY",),
        display_name="Cerebras",
        group=ProviderGroup.SINGLE_KEY,
        is_subscription=False,
    ),
    ProviderCatalogEntry(
        provider_id="xai",
        env_var_names=("XAI_API_KEY",),
        display_name="xAI",
        group=ProviderGroup.SINGLE_KEY,
        is_subscription=False,
    ),
    ProviderCatalogEntry(
        provider_id="openrouter",
        env_var_names=("OPENROUTER_API_KEY",),
        display_name="OpenRouter",
        group=ProviderGroup.SINGLE_KEY,
        is_subscription=False,
    ),
    ProviderCatalogEntry(
        provider_id="vercel-ai-gateway",
        env_var_names=("AI_GATEWAY_API_KEY",),
        display_name="Vercel AI Gateway",
        group=ProviderGroup.SINGLE_KEY,
        is_subscription=False,
    ),
    ProviderCatalogEntry(
        provider_id="zai",
        env_var_names=("ZAI_API_KEY",),
        display_name="Z.AI",
        group=ProviderGroup.SINGLE_KEY,
        is_subscription=False,
    ),
    ProviderCatalogEntry(
        provider_id="opencode",
        env_var_names=("OPENCODE_API_KEY",),
        display_name="OpenCode",
        group=ProviderGroup.SINGLE_KEY,
        is_subscription=False,
    ),
    ProviderCatalogEntry(
        provider_id="opencode-go",
        env_var_names=("OPENCODE_API_KEY",),
        display_name="OpenCode Go",
        group=ProviderGroup.SINGLE_KEY,
        is_subscription=False,
    ),
    ProviderCatalogEntry(
        provider_id="huggingface",
        env_var_names=("HF_TOKEN",),
        display_name="Hugging Face",
        group=ProviderGroup.SINGLE_KEY,
        is_subscription=False,
    ),
    ProviderCatalogEntry(
        provider_id="fireworks",
        env_var_names=("FIREWORKS_API_KEY",),
        display_name="Fireworks",
        group=ProviderGroup.SINGLE_KEY,
        is_subscription=False,
    ),
    ProviderCatalogEntry(
        provider_id="together",
        env_var_names=("TOGETHER_API_KEY",),
        display_name="Together AI",
        group=ProviderGroup.SINGLE_KEY,
        is_subscription=False,
    ),
    ProviderCatalogEntry(
        provider_id="kimi-coding",
        env_var_names=("KIMI_API_KEY",),
        display_name="Kimi Coding",
        group=ProviderGroup.SINGLE_KEY,
        is_subscription=False,
    ),
    ProviderCatalogEntry(
        provider_id="minimax",
        env_var_names=("MINIMAX_API_KEY",),
        display_name="MiniMax",
        group=ProviderGroup.SINGLE_KEY,
        is_subscription=False,
    ),
    ProviderCatalogEntry(
        provider_id="minimax-cn",
        env_var_names=("MINIMAX_CN_API_KEY",),
        display_name="MiniMax (CN)",
        group=ProviderGroup.SINGLE_KEY,
        is_subscription=False,
    ),
    ProviderCatalogEntry(
        provider_id="xiaomi",
        env_var_names=("XIAOMI_API_KEY",),
        display_name="Xiaomi",
        group=ProviderGroup.SINGLE_KEY,
        is_subscription=False,
    ),
    ProviderCatalogEntry(
        provider_id="xiaomi-token-plan-cn",
        env_var_names=("XIAOMI_TOKEN_PLAN_CN_API_KEY",),
        display_name="Xiaomi Token Plan (CN)",
        group=ProviderGroup.SINGLE_KEY,
        is_subscription=False,
    ),
    ProviderCatalogEntry(
        provider_id="xiaomi-token-plan-ams",
        env_var_names=("XIAOMI_TOKEN_PLAN_AMS_API_KEY",),
        display_name="Xiaomi Token Plan (AMS)",
        group=ProviderGroup.SINGLE_KEY,
        is_subscription=False,
    ),
    ProviderCatalogEntry(
        provider_id="xiaomi-token-plan-sgp",
        env_var_names=("XIAOMI_TOKEN_PLAN_SGP_API_KEY",),
        display_name="Xiaomi Token Plan (SGP)",
        group=ProviderGroup.SINGLE_KEY,
        is_subscription=False,
    ),
    ProviderCatalogEntry(
        provider_id="azure-openai-responses",
        env_var_names=("AZURE_OPENAI_API_KEY",),
        display_name="Azure OpenAI",
        group=ProviderGroup.SESSION_ONLY,
        is_subscription=False,
    ),
    ProviderCatalogEntry(
        provider_id="amazon-bedrock",
        env_var_names=(),
        display_name="Amazon Bedrock",
        group=ProviderGroup.SESSION_ONLY,
        is_subscription=False,
    ),
    ProviderCatalogEntry(
        provider_id="cloudflare-ai-gateway",
        env_var_names=("CLOUDFLARE_API_KEY", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_GATEWAY_ID"),
        display_name="Cloudflare AI Gateway",
        group=ProviderGroup.SESSION_ONLY,
        is_subscription=False,
    ),
    ProviderCatalogEntry(
        provider_id="cloudflare-workers-ai",
        env_var_names=("CLOUDFLARE_API_KEY", "CLOUDFLARE_ACCOUNT_ID"),
        display_name="Cloudflare Workers AI",
        group=ProviderGroup.SESSION_ONLY,
        is_subscription=False,
    ),
)

_PROVIDER_CATALOG_BY_ID: dict[str, ProviderCatalogEntry] = {entry.provider_id: entry for entry in _PROVIDER_CATALOG}


def get_provider_catalog() -> tuple[ProviderCatalogEntry, ...]:
    """Return the full static provider catalog."""
    return _PROVIDER_CATALOG


def get_provider_entry(provider_id: str) -> ProviderCatalogEntry | None:
    """Return the catalog entry for ``provider_id``, or ``None`` if unknown."""
    return _PROVIDER_CATALOG_BY_ID.get(provider_id)
