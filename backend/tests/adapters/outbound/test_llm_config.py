"""Tests for resolve_llm_model's env var validation."""

import pytest

from app.adapters.outbound.llm_config import DEFAULT_MODEL, resolve_llm_model
from app.domain.exceptions import MissingLLMCredentialsError


def test_resolve_llm_model_defaults_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    assert resolve_llm_model() == DEFAULT_MODEL


def test_resolve_llm_model_raises_when_provider_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_MODEL", "gemini/gemini-3.5-flash")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(MissingLLMCredentialsError):
        resolve_llm_model()


def test_resolve_llm_model_checks_configured_models_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-4o")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "unrelated-key")

    with pytest.raises(MissingLLMCredentialsError) as exc_info:
        resolve_llm_model()

    assert exc_info.value.env_var == "OPENAI_API_KEY"


def test_resolve_llm_model_succeeds_when_matching_key_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_MODEL", "anthropic/claude-sonnet-5")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    assert resolve_llm_model() == "anthropic/claude-sonnet-5"


def test_resolve_llm_model_handles_openrouters_three_segment_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # OpenRouter models carry the underlying provider too, so the string has three
    # segments rather than the usual two.
    monkeypatch.setenv("LLM_MODEL", "openrouter/anthropic/claude-sonnet-4.5")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(MissingLLMCredentialsError) as exc_info:
        resolve_llm_model()

    assert exc_info.value.env_var == "OPENROUTER_API_KEY"

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    assert resolve_llm_model() == "openrouter/anthropic/claude-sonnet-4.5"
