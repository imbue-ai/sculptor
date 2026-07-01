"""Unit tests for the static pi provider catalog: presence, grouping, lookup,
and provider-id uniqueness.
"""

from __future__ import annotations

from sculptor.agents.pi_agent.provider_catalog import ProviderGroup
from sculptor.agents.pi_agent.provider_catalog import get_provider_catalog
from sculptor.agents.pi_agent.provider_catalog import get_provider_entry


def test_single_key_providers_present_with_expected_env_vars() -> None:
    anthropic = get_provider_entry("anthropic")
    assert anthropic is not None
    assert anthropic.env_var_names == ("ANTHROPIC_API_KEY",)
    assert anthropic.group == ProviderGroup.SINGLE_KEY

    openai = get_provider_entry("openai")
    assert openai is not None
    assert openai.env_var_names == ("OPENAI_API_KEY",)
    assert openai.group == ProviderGroup.SINGLE_KEY

    google = get_provider_entry("google")
    assert google is not None
    assert google.env_var_names == ("GEMINI_API_KEY",)
    assert google.group == ProviderGroup.SINGLE_KEY


def test_session_only_providers_present_and_grouped() -> None:
    for provider_id in (
        "azure-openai-responses",
        "amazon-bedrock",
        "cloudflare-ai-gateway",
        "cloudflare-workers-ai",
    ):
        entry = get_provider_entry(provider_id)
        assert entry is not None, provider_id
        assert entry.group == ProviderGroup.SESSION_ONLY, provider_id


def test_get_provider_entry_lookup() -> None:
    assert get_provider_entry("anthropic") is not None
    assert get_provider_entry("does-not-exist") is None


def test_provider_ids_are_unique() -> None:
    provider_ids = [entry.provider_id for entry in get_provider_catalog()]
    assert len(provider_ids) == len(set(provider_ids))
