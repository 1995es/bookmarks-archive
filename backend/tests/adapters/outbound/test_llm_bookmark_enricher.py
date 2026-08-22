"""Tests for LLMBookmarkEnricherService, mocking litellm.acompletion."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.adapters.outbound.llm_bookmark_enricher import LLMBookmarkEnricherService
from app.domain.exceptions import EnrichmentError
from app.domain.models import ExtractedData, FetchedContent


def _mock_response(content: str):
    response = AsyncMock()
    response.choices = [AsyncMock(message=AsyncMock(content=content))]
    return response


def _fetched(**overrides: object) -> FetchedContent:
    defaults = dict(name="Example Page", description="A page about examples.", content="body")
    defaults.update(overrides)
    return FetchedContent(**defaults)


async def test_extract_data_returns_parsed_description_and_tags() -> None:
    enricher = LLMBookmarkEnricherService()
    payload = json.dumps({"description": "A neat article.", "tags": ["python", "async"]})

    with patch(
        "app.adapters.outbound.llm_bookmark_enricher.litellm.acompletion",
        new=AsyncMock(return_value=_mock_response(payload)),
    ):
        result = await enricher.extract_data(url="https://example.com", fetched=_fetched())

    assert result == ExtractedData(description="A neat article.", tags=["python", "async"])


async def test_extract_data_wraps_invalid_json_in_enrichment_error() -> None:
    enricher = LLMBookmarkEnricherService()

    with patch(
        "app.adapters.outbound.llm_bookmark_enricher.litellm.acompletion",
        new=AsyncMock(return_value=_mock_response("not json")),
    ):
        with pytest.raises(EnrichmentError):
            await enricher.extract_data(url="https://example.com", fetched=_fetched())


async def test_extract_data_wraps_provider_error_in_enrichment_error() -> None:
    enricher = LLMBookmarkEnricherService()

    with patch(
        "app.adapters.outbound.llm_bookmark_enricher.litellm.acompletion",
        new=AsyncMock(side_effect=RuntimeError("provider down")),
    ):
        with pytest.raises(EnrichmentError):
            await enricher.extract_data(url="https://example.com", fetched=_fetched())


async def test_extract_data_truncates_content_before_sending() -> None:
    enricher = LLMBookmarkEnricherService(max_content_chars=10)
    payload = json.dumps({"description": "d", "tags": []})
    mock_acompletion = AsyncMock(return_value=_mock_response(payload))

    with patch(
        "app.adapters.outbound.llm_bookmark_enricher.litellm.acompletion",
        new=mock_acompletion,
    ):
        await enricher.extract_data(url="https://example.com", fetched=_fetched(content="x" * 100))

    sent_messages = mock_acompletion.call_args.kwargs["messages"]
    user_message = next(m["content"] for m in sent_messages if m["role"] == "user")
    assert "x" * 100 not in user_message
    assert "x" * 10 in user_message


async def test_extract_data_includes_title_and_description_in_prompt() -> None:
    enricher = LLMBookmarkEnricherService()
    payload = json.dumps({"description": "d", "tags": []})
    mock_acompletion = AsyncMock(return_value=_mock_response(payload))

    with patch(
        "app.adapters.outbound.llm_bookmark_enricher.litellm.acompletion",
        new=mock_acompletion,
    ):
        await enricher.extract_data(
            url="https://example.com",
            fetched=_fetched(name="Example Page", description="A page about examples."),
        )

    sent_messages = mock_acompletion.call_args.kwargs["messages"]
    user_message = next(m["content"] for m in sent_messages if m["role"] == "user")
    assert "Example Page" in user_message
    assert "A page about examples." in user_message
