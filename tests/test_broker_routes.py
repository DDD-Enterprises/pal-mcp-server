"""Broker selection must agree across listing, tool lookup, aliases and transport."""

from unittest.mock import AsyncMock, Mock

import pytest

from providers.catalog_endpoint import AnthropicProvider, CheaperInferenceProvider
from providers.openai import OpenAIModelProvider
from providers.openrouter import OpenRouterProvider
from providers.registry import ModelProviderRegistry as Registry
from providers.shared import ProviderType
from tools.consensus import ConsensusTool


@pytest.fixture
def brokers(monkeypatch):
    monkeypatch.setenv("PAL_BROKER_FIRST", "true")
    monkeypatch.setattr(OpenRouterProvider, "_registry", None)
    monkeypatch.setattr(Registry, "_instance", None)
    for kind, implementation in (
        (ProviderType.OPENAI, OpenAIModelProvider),
        (ProviderType.ANTHROPIC, AnthropicProvider),
        (ProviderType.OPENROUTER, OpenRouterProvider),
        (ProviderType.CHEAPERINFERENCE, CheaperInferenceProvider),
    ):
        monkeypatch.setenv(f"{kind.value.upper()}_API_KEY", "test-only")
        Registry.register_provider(kind, implementation)


@pytest.mark.parametrize(
    "name, kind, wire",
    [
        ("google/gemini-4-neon", "cheaperinference", "gemini-4-neon"),
        ("grok-4.7", "cheaperinference", "grok-4.7"),
        ("claude-sonnet-5-5", "cheaperinference", "claude-sonnet-5.5"),
        ("gpt-6.2-sol", "cheaperinference", "gpt-6.2-sol"),
        ("openai/gpt-6.2-astra", "cheaperinference", "gpt-6.2-astra"),
        ("gpt-6-luna-pro", "openrouter", "openai/gpt-6-luna-pro"),
        ("openai/gpt-6-astra-pro", "cheaperinference", "gpt-6-astra-pro"),
    ],
)
def test_route_and_wire_id(brokers, name, kind, wire):
    assert Registry.get_available_models()[name].value == kind
    provider = Registry.get_provider_for_model(name)
    assert provider.get_provider_type().value == kind
    assert provider.get_capabilities(name).model_name == wire


def test_secondary_then_native_for_same_model(brokers):
    Registry.unregister_provider(ProviderType.CHEAPERINFERENCE)
    for name in ["openai/gpt-6.2-sol", "claude-sonnet-5-5"]:
        assert Registry.get_provider_for_model(name).get_provider_type() == ProviderType.OPENROUTER
    Registry.unregister_provider(ProviderType.OPENROUTER)
    assert Registry.get_provider_for_model("openai/gpt-6.2-sol").get_provider_type() == ProviderType.OPENAI
    claude = Registry.get_provider_for_model("claude-sonnet-5.5")
    assert claude.get_provider_type() == ProviderType.ANTHROPIC
    assert claude.get_capabilities("claude-sonnet-5.5").model_name == "claude-sonnet-5-5"


def test_unknown_and_batch_ids_have_no_interactive_route(brokers):
    from server import parse_model_option

    for name in ["anthropic/missing", "openai/gpt-6.2-sol:batch"]:
        assert Registry.get_provider_for_model(parse_model_option(name)[0]) is None


def test_ambiguous_failure_is_not_replayed(brokers):
    provider = Registry.get_provider_for_model("gpt-6-luna")
    client = Mock()
    provider._client = client
    client.chat.completions.create.side_effect = TimeoutError("timeout")
    with pytest.raises(RuntimeError, match="after 1 attempt"):
        provider.generate_content("Synthetic test", "gpt-6-luna", max_output_tokens=32, thinking_mode="low")
    client.chat.completions.create.assert_called_once()
    params = client.chat.completions.create.call_args.kwargs
    assert params["model"] == "gpt-6-luna" and params["max_tokens"] == 32
    assert "temperature" not in params
    assert params["extra_body"] == {"reasoning": {"effort": "low"}}


@pytest.mark.asyncio
async def test_failed_verdict_does_not_complete_consensus(brokers, monkeypatch):
    import json

    tool = ConsensusTool()
    failure = {"model": "gpt-6-luna-pro", "status": "error", "error": "402"}
    monkeypatch.setattr(tool, "_consult_model", AsyncMock(return_value=failure))
    result = await tool.execute_workflow(
        {
            "step": "Synthetic proposal",
            "findings": "Synthetic finding",
            "step_number": 1,
            "total_steps": 1,
            "next_step_required": False,
            "models": [{"model": "gpt-6-luna-pro"}],
        }
    )
    body = json.loads(result[0].text)
    assert body["status"] == "consensus_incomplete"
    assert body["consensus_complete"] is False
    assert body["models_errored"] == ["gpt-6-luna-pro"]


def test_pro_mode_uses_stateless_responses(brokers):
    provider = Registry.get_provider_for_model("openai/gpt-5.6-luna-pro")
    provider._client = Mock()
    provider._client.responses.create.return_value.output_text = "OK"
    provider.generate_content("Synthetic", "openai/gpt-5.6-luna-pro", thinking_mode="low", max_output_tokens=32)
    args = provider._client.responses.create.call_args.kwargs
    assert args["model"] == "gpt-5.6-luna"
    assert args["reasoning"] == {"mode": "pro", "effort": "low"}
    assert args["store"] is False and args["stream"] is False
    provider._client.chat.completions.create.assert_not_called()
