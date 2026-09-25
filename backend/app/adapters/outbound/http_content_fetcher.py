"""Outbound adapter implementing ContentFetcher over httpx.AsyncClient."""

import re
from html.parser import HTMLParser
from types import TracebackType
from urllib.parse import urljoin, urlparse

import httpx

from app.domain.exceptions import ContentFetchError
from app.domain.models import FetchedContent
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

# Every site that declares no icon still answers /favicon.ico by convention.
_DEFAULT_FAVICON_PATH = "/favicon.ico"
# Matches _MAX_URL_LENGTH in domain/models.py, which drops an over-length icon URL.
_MAX_FAVICON_URL_LENGTH = 2000
# An apple-touch-icon carries no `sizes` in practice but is 180px by convention —
# scored as such so it beats a bare 16px .ico but loses to an explicit larger one.
_APPLE_TOUCH_ICON_SIZE = 180


def _icon_score(sizes: str, rels: list[str]) -> int:
    """How good an icon candidate is, in pixels of its largest declared edge.

    `sizes="any"` means a scalable SVG, which beats every raster size.
    """
    sizes = sizes.lower()
    if "any" in sizes.split():
        return 10_000

    largest = 0
    for token in sizes.split():
        width, _, _height = token.partition("x")
        if width.isdigit():
            largest = max(largest, int(width))
    if largest:
        return largest

    return _APPLE_TOUCH_ICON_SIZE if any(r.startswith("apple-touch-icon") for r in rels) else 0


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
        self._icons: list[tuple[int, str]] = []

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
        elif tag == "link":
            self._collect_icon(dict(attrs))

    def _collect_icon(self, attrs_dict: dict[str, str | None]) -> None:
        # `rel` is a space-separated token list, so "shortcut icon" contains "icon".
        rels = (attrs_dict.get("rel") or "").lower().split()
        href = (attrs_dict.get("href") or "").strip()
        if not href:
            return
        if "icon" not in rels and not any(r.startswith("apple-touch-icon") for r in rels):
            return
        self._icons.append((_icon_score(attrs_dict.get("sizes") or "", rels), href))

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

    @property
    def icon_href(self) -> str:
        """The highest-scoring declared icon, still as written in the markup.

        Ties go to the one declared first, which is the page's own preference order.
        """
        if not self._icons:
            return ""
        return max(enumerate(self._icons), key=lambda pair: (pair[1][0], -pair[0]))[1][1]


class HttpContentFetcher(ContentFetcher):
    """Fetches a URL and returns its extracted content as a FetchedContent, capped at
    _MAX_RESPONSE_BYTES.

    "Extracted" means: title and meta description surfaced as their own fields, script/
    style/nav/header/footer/etc. dropped rather than just un-tagged, and body text scoped
    to <main>/<article> when the page provides one — all to keep boilerplate out of what
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

    async def fetch(self, url: str) -> FetchedContent:
        try:
            async with self._client.stream("GET", url) as response:
                if response.status_code >= 400:
                    raise ContentFetchError(
                        f"fetching {url} returned status {response.status_code}"
                    )

                # Relative icon hrefs resolve against the URL the response actually
                # came from, not the one the user pasted — a redirect to another
                # host would otherwise send us to the wrong origin for the icon.
                final_url = str(response.url)

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
        return self._extract(text, final_url)

    @staticmethod
    def _extract(html: str, base_url: str) -> FetchedContent:
        extractor = _ContentExtractor()
        # A truncated response can end mid-tag; HTMLParser tolerates malformed/
        # unterminated markup rather than raising, so no extra guarding is needed.
        extractor.feed(html)
        extractor.close()

        name = _WHITESPACE_RE.sub(" ", extractor.title).strip()
        return FetchedContent(
            name=name,
            description=extractor.description,
            content=extractor.body,
            favicon_url=_resolve_favicon(extractor.icon_href, base_url),
        )


def _resolve_favicon(href: str, base_url: str) -> str:
    """Absolutize a declared icon href, falling back to the origin's /favicon.ico.

    Returns "" rather than raising for anything unusable — a `data:` URI, a
    malformed href, an over-long URL. Favicons are decoration: discovery must
    never be the reason an enrichment fails and a bookmark ends up FAILED,
    since it rides inside the same fetch that feeds the LLM.
    """
    for candidate in (href, _DEFAULT_FAVICON_PATH):
        if not candidate:
            continue
        try:
            resolved = urljoin(base_url, candidate)
            parsed = urlparse(resolved)
        except ValueError:
            continue
        if parsed.scheme in ("http", "https") and parsed.netloc:
            if len(resolved) <= _MAX_FAVICON_URL_LENGTH:
                return resolved
    return ""
