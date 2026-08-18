"""Outbound adapter implementing BookmarkEnricherService via litellm + Gemini."""

import json

import litellm

from app.domain.exceptions import EnrichmentError
from app.domain.models import ExtractedData
from app.domain.ports import BookmarkEnricherService

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["description", "tags"],
}

_SYSTEM_PROMPT = (
    "You derive a short description and a list of tags for a bookmark, given its "
    "URL and the text content fetched from that URL. Respond with a concise "
    "description and relevant tags."
)


class LLMBookmarkEnricherService(BookmarkEnricherService):
    def __init__(
        self, *, model: str = "gemini/gemini-3.7-flash", max_content_chars: int = 8000
    ) -> None:
        self._model = model
        self._max_content_chars = max_content_chars

    async def extract_data(self, *, url: str, content: str) -> ExtractedData:
        truncated_content = content[: self._max_content_chars]

        try:
            response = await litellm.acompletion(
                model=self._model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"URL: {url}\n\nContent:\n{truncated_content}",
                    },
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "extracted_data", "schema": _RESPONSE_SCHEMA},
                },
            )
        except Exception as exc:
            raise EnrichmentError(f"litellm request failed: {exc}") from exc

        raw = response.choices[0].message.content

        try:
            parsed = json.loads(raw)
            description = parsed["description"]
            tags = parsed["tags"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise EnrichmentError(f"could not parse LLM response: {exc}") from exc

        return ExtractedData(description=description, tags=list(tags))
