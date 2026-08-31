import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  createBookmark,
  deleteBookmark,
  listBookmarks,
  retryEnrichment,
  updateBookmark,
} from "./api";
import type { Bookmark } from "./types";

const BASE_URL = `${window.location.protocol}//${window.location.hostname}:8000`;

function bookmark(overrides: Partial<Bookmark> = {}): Bookmark {
  return {
    id: "0198f0c0-0000-7000-8000-000000000001",
    name: "Example",
    url: "https://example.com",
    description: null,
    tags: [],
    type: "post",
    created_at: "2026-03-14T12:00:00Z",
    enrichment_status: "done",
    ...overrides,
  };
}

/** A minimal stand-in for the parts of Response api.ts actually touches. */
function jsonResponse(
  body: unknown,
  { status = 200, headers = {} }: { status?: number; headers?: Record<string, string> } = {},
): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
});

function lastRequest(): { url: URL; init: RequestInit } {
  const [input, init] = fetchMock.mock.calls.at(-1)!;
  return { url: new URL(String(input)), init: init ?? {} };
}

function headerOf(init: RequestInit, name: string): string | undefined {
  return new Headers(init.headers).get(name) ?? undefined;
}

describe("listBookmarks", () => {
  it("reads the unpaginated total out of X-Total-Count", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse([bookmark()], { headers: { "X-Total-Count": "137" } }),
    );

    const page = await listBookmarks();

    expect(page.items).toHaveLength(1);
    expect(page.total).toBe(137);
  });

  it("falls back to items.length when the header is absent", async () => {
    fetchMock.mockResolvedValue(jsonResponse([bookmark(), bookmark({ id: "b" })]));

    const page = await listBookmarks();

    expect(page.total).toBe(2);
  });

  it("omits absent params from the query string entirely", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));

    await listBookmarks();

    const { url } = lastRequest();
    expect(url.pathname).toBe("/bookmarks");
    expect(url.search).toBe("");
  });

  it("maps camelCase params onto the backend's snake_case query keys", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));

    await listBookmarks({
      tag: "react",
      type: "video",
      sortBy: "created_at",
      sortOrder: "desc",
      limit: 20,
      offset: 40,
    });

    const { url } = lastRequest();
    expect(Object.fromEntries(url.searchParams)).toEqual({
      tag: "react",
      type: "video",
      sort_by: "created_at",
      sort_order: "desc",
      limit: "20",
      offset: "40",
    });
  });

  it("sends offset=0 rather than dropping it as falsy", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));

    await listBookmarks({ offset: 0, limit: 20 });

    expect(lastRequest().url.searchParams.get("offset")).toBe("0");
  });
});

describe("error handling", () => {
  it("unwraps FastAPI's {detail: ...} shape — including the 409 duplicate", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: "A bookmark with this URL already exists" }, { status: 409 }),
    );

    await expect(
      createBookmark({ url: "https://dupe.example", description: null, tags: [] }),
    ).rejects.toThrow("A bookmark with this URL already exists");
  });

  it("falls back to statusText when the body isn't JSON", async () => {
    fetchMock.mockResolvedValue(
      new Response("<html>bad gateway</html>", { status: 502, statusText: "Bad Gateway" }),
    );

    await expect(listBookmarks()).rejects.toThrow("Bad Gateway");
  });

  it("falls back to the status code when statusText is empty too", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 500, statusText: "" }));

    await expect(listBookmarks()).rejects.toThrow("Request failed with status 500");
  });
});

describe("request plumbing", () => {
  it("resolves a 204 without trying to parse a body", async () => {
    const response = jsonResponse(null, { status: 204 });
    const jsonSpy = vi.spyOn(response, "json");
    fetchMock.mockResolvedValue(response);

    await expect(deleteBookmark("abc")).resolves.toBeUndefined();
    expect(jsonSpy).not.toHaveBeenCalled();
    expect(lastRequest().init.method).toBe("DELETE");
  });

  it("keeps Content-Type set alongside the caller's init (the f6f7303 regression)", async () => {
    fetchMock.mockResolvedValue(jsonResponse(bookmark()));

    await createBookmark({ url: "https://example.com", description: null, tags: ["a"] });

    const { init } = lastRequest();
    expect(headerOf(init, "Content-Type")).toBe("application/json");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      url: "https://example.com",
      description: null,
      tags: ["a"],
    });
  });

  it("PUTs the full body to the bookmark's own path", async () => {
    fetchMock.mockResolvedValue(jsonResponse(bookmark({ name: "Renamed" })));

    const updated = await updateBookmark("abc", {
      name: "Renamed",
      url: "https://example.com",
      description: null,
      tags: [],
      type: "post",
    });

    const { url, init } = lastRequest();
    expect(url.pathname).toBe("/bookmarks/abc");
    expect(init.method).toBe("PUT");
    expect(headerOf(init, "Content-Type")).toBe("application/json");
    expect(updated.name).toBe("Renamed");
  });

  it("POSTs retry-enrichment to the right path", async () => {
    fetchMock.mockResolvedValue(jsonResponse(bookmark({ enrichment_status: "pending" })));

    const retried = await retryEnrichment("abc");

    const { url, init } = lastRequest();
    expect(url.pathname).toBe("/bookmarks/abc/retry-enrichment");
    expect(init.method).toBe("POST");
    expect(retried.enrichment_status).toBe("pending");
  });

  it("targets the backend on port 8000 of the current host", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));

    await listBookmarks();

    expect(String(fetchMock.mock.calls[0][0])).toBe(`${BASE_URL}/bookmarks`);
  });
});
