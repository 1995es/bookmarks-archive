"""Outbound adapter implementing BookmarkEnricherService. Stub — litellm integration pending.

When implemented:
- use litellm.acompletion (the async variant — the whole stack is async), not the sync one
- default model "anthropic/claude-opus-5" (provider prefix + model id)
- request structured output via response_format with a JSON schema
  {description: str, tags: list[str]}, not free-text parsing
- truncate `content` to max_content_chars before sending
- wrap any litellm exception in EnrichmentError
"""

from app.domain.models import ExtractedData
from app.domain.ports import BookmarkEnricherService


class LLMBookmarkEnricherService(BookmarkEnricherService):
    def __init__(
        self, *, model: str = "anthropic/claude-opus-5", max_content_chars: int = 8000
    ) -> None:
        self._model = model
        self._max_content_chars = max_content_chars

    async def extract_data(self, *, url: str, content: str) -> ExtractedData:
        raise NotImplementedError("pending litellm integration")
