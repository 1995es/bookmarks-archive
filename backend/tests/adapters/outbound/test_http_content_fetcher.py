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
        content = await fetcher.fetch("https://example.com")

    assert "Hello world" in content
    assert "<" not in content


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
        content = await fetcher.fetch("https://example.com")

    assert len(content) <= _MAX_RESPONSE_BYTES


async def test_follows_redirects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"Location": "https://example.com/end"})
        return httpx.Response(200, html="<p>final destination</p>")

    async with _fetcher(handler) as fetcher:
        content = await fetcher.fetch("https://example.com/start")

    assert "final destination" in content


async def test_drops_script_and_style_content() -> None:
    html = (
        "<html><head><style>body { color: red; }</style></head>"
        "<body><script>alert('hi')</script><p>Real content</p></body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, html=html)

    async with _fetcher(handler) as fetcher:
        content = await fetcher.fetch("https://example.com")

    assert "Real content" in content
    assert "color: red" not in content
    assert "alert" not in content


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
        content = await fetcher.fetch("https://example.com")

    assert "Real content" in content
    assert "Home About Contact" not in content
    assert "Site Header" not in content
    assert "Copyright 2026" not in content


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
        content = await fetcher.fetch("https://example.com")

    assert "The actual article text" in content
    assert "Sidebar chrome" not in content


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
        content = await fetcher.fetch("https://example.com")

    assert content.startswith("Title: Example Page\nDescription: A page about examples.\n")
    assert "Body text" in content
