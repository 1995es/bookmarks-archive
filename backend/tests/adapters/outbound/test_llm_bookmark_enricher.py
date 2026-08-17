"""Documents the current stub state of LLMBookmarkEnricherService.

Intentionally fragile: once litellm is wired in, this test starts failing and
forces writing the real tests (well-formed response -> ExtractedData; invalid
JSON -> EnrichmentError; provider error -> EnrichmentError; content truncated
before being sent).
"""

import pytest

from app.adapters.outbound.llm_bookmark_enricher import LLMBookmarkEnricherService


async def test_extract_data_not_implemented_yet() -> None:
    enricher = LLMBookmarkEnricherService()

    with pytest.raises(NotImplementedError):
        await enricher.extract_data(url="https://example.com", content="some content")
