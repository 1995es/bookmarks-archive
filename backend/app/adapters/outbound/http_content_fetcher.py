"""Outbound adapter implementing ContentFetcher over httpx.AsyncClient."""

import re
from types import TracebackType

import httpx

from app.domain.exceptions import ContentFetchError
from app.domain.ports import ContentFetcher

_TIMEOUT_SECONDS = 10.0
_MAX_RESPONSE_BYTES = 1_000_000
_USER_AGENT = "bookmarks-archive/1.0 (+content-enrichment)"
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


class HttpContentFetcher(ContentFetcher):
    """Fetches a URL and returns its plain-text content, capped at _MAX_RESPONSE_BYTES.

    Created per background task and closed via `async with` — a single request per
    instance, so there's no shared connection pool to manage across tasks.
    """

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        )

    async def __aenter__(self) -> HttpContentFetcher:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    async def fetch(self, url: str) -> str:
        try:
            async with self._client.stream("GET", url) as response:
                if response.status_code >= 400:
                    raise ContentFetchError(
                        f"fetching {url} returned status {response.status_code}"
                    )

                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) >= _MAX_RESPONSE_BYTES:
                        break
                body = bytes(chunks[:_MAX_RESPONSE_BYTES])
        except httpx.HTTPError as exc:
            raise ContentFetchError(f"failed to fetch {url}: {exc}") from exc

        # A break on an oversized body can truncate mid-stream before httpx has
        # buffered enough to sniff the charset, so decode as utf-8 unconditionally
        # rather than relying on response.encoding (which assumes a fully-read body).
        text = body.decode("utf-8", errors="replace")
        return self._strip_html(text)

    @staticmethod
    def _strip_html(html: str) -> str:
        text = _TAG_RE.sub(" ", html)
        return _WHITESPACE_RE.sub(" ", text).strip()
