"""Tests for HttpContentFetcher, using httpx.MockTransport instead of real network calls."""

import httpx
import pytest

from app.adapters.outbound.http_content_fetcher import (
    _MAX_RESPONSE_BYTES,
    HttpContentFetcher,
)
from app.domain.exceptions import ContentFetchError


def _fetcher(handler) -> HttpContentFetcher:
    fetcher = HttpContentFetcher()
    fetcher._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=True
    )
    return fetcher


async def test_returns_text_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, html="<html><body><p>Hello world</p></body></html>")

    async with _fetcher(handler) as fetcher:
        fetched = await fetcher.fetch("https://example.com")

    assert "Hello world" in fetched.content
    assert "<" not in fetched.content


async def test_raises_on_http_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    async with _fetcher(handler) as fetcher:
        with pytest.raises(ContentFetchError):
            await fetcher.fetch("https://example.com")


async def test_raises_on_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    async with _fetcher(handler) as fetcher:
        with pytest.raises(ContentFetchError):
            await fetcher.fetch("https://example.com")


async def test_truncates_oversized_response() -> None:
    oversized_body = b"a" * (_MAX_RESPONSE_BYTES * 2)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=oversized_body)

    async with _fetcher(handler) as fetcher:
        fetched = await fetcher.fetch("https://example.com")

    assert len(fetched.content) <= _MAX_RESPONSE_BYTES


async def test_follows_redirects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"Location": "https://example.com/end"})
        return httpx.Response(200, html="<p>final destination</p>")

    async with _fetcher(handler) as fetcher:
        fetched = await fetcher.fetch("https://example.com/start")

    assert "final destination" in fetched.content


async def test_drops_script_and_style_content() -> None:
    html = (
        "<html><head><style>body { color: red; }</style></head>"
        "<body><script>alert('hi')</script><p>Real content</p></body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, html=html)

    async with _fetcher(handler) as fetcher:
        fetched = await fetcher.fetch("https://example.com")

    assert "Real content" in fetched.content
    assert "color: red" not in fetched.content
    assert "alert" not in fetched.content


async def test_drops_nav_header_footer_content() -> None:
    html = (
        "<html><body>"
        "<nav>Home About Contact</nav>"
        "<header>Site Header</header>"
        "<p>Real content</p>"
        "<footer>Copyright 2026</footer>"
        "</body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, html=html)

    async with _fetcher(handler) as fetcher:
        fetched = await fetcher.fetch("https://example.com")

    assert "Real content" in fetched.content
    assert "Home About Contact" not in fetched.content
    assert "Site Header" not in fetched.content
    assert "Copyright 2026" not in fetched.content


async def test_prefers_main_content_over_surrounding_chrome() -> None:
    html = (
        "<html><body>"
        "<div>Sidebar chrome that isn't tagged as boilerplate</div>"
        "<main><p>The actual article text</p></main>"
        "</body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, html=html)

    async with _fetcher(handler) as fetcher:
        fetched = await fetcher.fetch("https://example.com")

    assert "The actual article text" in fetched.content
    assert "Sidebar chrome" not in fetched.content


async def test_surfaces_title_and_meta_description() -> None:
    html = (
        "<html><head>"
        "<title>Example Page</title>"
        '<meta name="description" content="A page about examples.">'
        "</head><body><p>Body text</p></body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, html=html)

    async with _fetcher(handler) as fetcher:
        fetched = await fetcher.fetch("https://example.com")

    assert fetched.name == "Example Page"
    assert fetched.description == "A page about examples."
    assert "Body text" in fetched.content


async def test_missing_title_yields_empty_name() -> None:
    html = "<html><body><p>Body text</p></body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, html=html)

    async with _fetcher(handler) as fetcher:
        fetched = await fetcher.fetch("https://example.com")

    assert fetched.name == ""
    assert fetched.description == ""


def _html_with_links(links: str) -> str:
    return f"<html><head>{links}</head><body><p>Body</p></body></html>"


async def _fetch_favicon(links: str, url: str = "https://example.com/page") -> str:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, html=_html_with_links(links))

    async with _fetcher(handler) as fetcher:
        fetched = await fetcher.fetch(url)

    return fetched.favicon_url


async def test_finds_a_declared_favicon() -> None:
    favicon_url = await _fetch_favicon('<link rel="icon" href="https://cdn.example.com/i.png">')

    assert favicon_url == "https://cdn.example.com/i.png"


async def test_resolves_a_relative_favicon_against_the_page_url() -> None:
    favicon_url = await _fetch_favicon('<link rel="icon" href="/static/i.png">')

    assert favicon_url == "https://example.com/static/i.png"


async def test_accepts_the_shortcut_icon_rel_spelling() -> None:
    favicon_url = await _fetch_favicon('<link rel="shortcut icon" href="/old.ico">')

    assert favicon_url == "https://example.com/old.ico"


async def test_prefers_the_largest_declared_icon() -> None:
    favicon_url = await _fetch_favicon(
        '<link rel="icon" sizes="16x16" href="/small.png">'
        '<link rel="icon" sizes="64x64" href="/large.png">'
    )

    assert favicon_url == "https://example.com/large.png"


async def test_prefers_a_scalable_icon_over_any_raster_size() -> None:
    favicon_url = await _fetch_favicon(
        '<link rel="icon" sizes="64x64" href="/large.png">'
        '<link rel="icon" sizes="any" href="/icon.svg">'
    )

    assert favicon_url == "https://example.com/icon.svg"


async def test_falls_back_to_the_conventional_favicon_path() -> None:
    favicon_url = await _fetch_favicon("")

    assert favicon_url == "https://example.com/favicon.ico"


async def test_falls_back_when_the_declared_icon_is_a_data_uri() -> None:
    favicon_url = await _fetch_favicon('<link rel="icon" href="data:image/png;base64,iVBORw0K">')

    assert favicon_url == "https://example.com/favicon.ico"


async def test_resolves_the_favicon_against_the_final_url_after_a_redirect() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "start.example.com":
            return httpx.Response(302, headers={"Location": "https://end.example.com/article"})
        return httpx.Response(200, html=_html_with_links('<link rel="icon" href="/i.png">'))

    async with _fetcher(handler) as fetcher:
        fetched = await fetcher.fetch("https://start.example.com/article")

    assert fetched.favicon_url == "https://end.example.com/i.png"


async def test_favicon_discovery_never_fails_the_fetch() -> None:
    # Discovery rides inside the fetch that feeds the LLM, so a malformed or
    # unusable icon declaration must degrade to "no icon", never raise.
    html = '<html><head><link rel="icon" href="http://"><title>T</title></head><body>x'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, html=html)

    async with _fetcher(handler) as fetcher:
        fetched = await fetcher.fetch("https://example.com")

    assert fetched.name == "T"
    assert fetched.favicon_url == "https://example.com/favicon.ico"
