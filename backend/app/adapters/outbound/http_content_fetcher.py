"""Outbound adapter implementing ContentFetcher over httpx.AsyncClient."""

import re
from html.parser import HTMLParser
from types import TracebackType

import httpx

from app.domain.exceptions import ContentFetchError
from app.domain.ports import ContentFetcher

_TIMEOUT_SECONDS = 10.0
_MAX_RESPONSE_BYTES = 1_000_000
_USER_AGENT = "bookmarks-archive/1.0 (+content-enrichment)"
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

# Tags whose content is boilerplate/non-visible, not article text — dropped entirely
# rather than just having their tags stripped, so e.g. inline <script> JS never
# reaches the enricher.
_SKIP_TAGS = frozenset(
    {"script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form"}
)
# If either appears, only text inside it is used as the body — everything else on
# the page (surrounding chrome the site didn't tag as one of _SKIP_TAGS) is dropped.
_CONTENT_TAGS = frozenset({"main", "article"})


class _ContentExtractor(HTMLParser):
    """Pulls title, meta description, and boilerplate-free body text from one page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self._skip_depth = 0
        self._content_depth = 0
        self._in_title = False
        self._body_parts: list[str] = []
        self._content_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _CONTENT_TAGS:
            self._content_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "meta" and not self.description:
            attrs_dict = dict(attrs)
            name = (attrs_dict.get("name") or attrs_dict.get("property") or "").lower()
            if name in ("description", "og:description"):
                self.description = (attrs_dict.get("content") or "").strip()

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in _CONTENT_TAGS:
            self._content_depth = max(0, self._content_depth - 1)
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title += data
            return
        self._body_parts.append(data)
        if self._content_depth:
            self._content_parts.append(data)

    @property
    def body(self) -> str:
        # Prefer text scoped to <main>/<article> over the whole page when present.
        parts = self._content_parts or self._body_parts
        return _WHITESPACE_RE.sub(" ", "".join(parts)).strip()


class HttpContentFetcher(ContentFetcher):
    """Fetches a URL and returns its extracted text content, capped at _MAX_RESPONSE_BYTES.

    "Extracted" means: title and meta description surfaced up front, script/style/nav/
    header/footer/etc. dropped rather than just un-tagged, and body text scoped to
    <main>/<article> when the page provides one — all to keep boilerplate out of what
    gets passed to the enricher.

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
        return self._extract(text)

    @staticmethod
    def _extract(html: str) -> str:
        extractor = _ContentExtractor()
        # A truncated response can end mid-tag; HTMLParser tolerates malformed/
        # unterminated markup rather than raising, so no extra guarding is needed.
        extractor.feed(html)
        extractor.close()

        parts = []
        if extractor.title.strip():
            parts.append(f"Title: {_WHITESPACE_RE.sub(' ', extractor.title).strip()}")
        if extractor.description:
            parts.append(f"Description: {extractor.description}")
        if extractor.body:
            parts.append(extractor.body)
        return "\n".join(parts)
