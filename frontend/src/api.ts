import type { Bookmark, BookmarkCreateInput, BookmarkId, BookmarkInput, BookmarkType } from "./types";

// Falls back to the current host on port 8000 when VITE_API_URL isn't baked in at build time —
// assumes the backend is reachable on the same host the frontend was loaded from, which holds for
// the Tailscale-only prod deployment (no reverse proxy) but not for an arbitrary multi-host setup.
const BASE_URL: string =
  import.meta.env.VITE_API_URL || `${window.location.protocol}//${window.location.hostname}:8000`;

async function parseErrorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (body && typeof body.detail === "string") {
      return body.detail;
    }
  } catch {
    // body wasn't JSON, or was empty — fall back below
  }
  return response.statusText || `Request failed with status ${response.status}`;
}

async function requestRaw(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const message = await parseErrorMessage(response);
    throw new Error(message);
  }

  return response;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await requestRaw(path, init);

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export type BookmarkSortBy = "name" | "created_at";
export type BookmarkSortOrder = "asc" | "desc";

export interface ListBookmarksParams {
  tag?: string;
  type?: BookmarkType;
  sortBy?: BookmarkSortBy;
  sortOrder?: BookmarkSortOrder;
  limit?: number;
  offset?: number;
}

export interface BookmarkPage {
  items: Bookmark[];
  total: number;
}

export async function listBookmarks(params: ListBookmarksParams = {}): Promise<BookmarkPage> {
  const search = new URLSearchParams();
  if (params.tag) {
    search.set("tag", params.tag);
  }
  if (params.type) {
    search.set("type", params.type);
  }
  if (params.sortBy) {
    search.set("sort_by", params.sortBy);
  }
  if (params.sortOrder) {
    search.set("sort_order", params.sortOrder);
  }
  if (params.limit !== undefined) {
    search.set("limit", String(params.limit));
  }
  if (params.offset !== undefined) {
    search.set("offset", String(params.offset));
  }
  const query = search.toString();
  const response = await requestRaw(`/bookmarks${query ? `?${query}` : ""}`);
  const items = (await response.json()) as Bookmark[];
  const totalHeader = response.headers.get("X-Total-Count");
  const total = totalHeader !== null ? Number(totalHeader) : items.length;
  return { items, total };
}

export function getBookmark(id: BookmarkId): Promise<Bookmark> {
  return request<Bookmark>(`/bookmarks/${id}`);
}

export function createBookmark(input: BookmarkCreateInput): Promise<Bookmark> {
  return request<Bookmark>(`/bookmarks`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateBookmark(id: BookmarkId, input: BookmarkInput): Promise<Bookmark> {
  return request<Bookmark>(`/bookmarks/${id}`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export function deleteBookmark(id: BookmarkId): Promise<void> {
  return request<void>(`/bookmarks/${id}`, {
    method: "DELETE",
  });
}

export function retryEnrichment(id: BookmarkId): Promise<Bookmark> {
  return request<Bookmark>(`/bookmarks/${id}/retry-enrichment`, {
    method: "POST",
  });
}
