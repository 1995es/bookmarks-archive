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
