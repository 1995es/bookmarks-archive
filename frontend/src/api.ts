import type { Bookmark, BookmarkId, BookmarkInput, BookmarkType } from "./types";

const BASE_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    const message = await parseErrorMessage(response);
    throw new Error(message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export interface ListBookmarksParams {
  tag?: string;
  type?: BookmarkType;
}

export function listBookmarks(params: ListBookmarksParams = {}): Promise<Bookmark[]> {
  const search = new URLSearchParams();
  if (params.tag) {
    search.set("tag", params.tag);
  }
  if (params.type) {
    search.set("type", params.type);
  }
  const query = search.toString();
  return request<Bookmark[]>(`/bookmarks${query ? `?${query}` : ""}`);
}

export function getBookmark(id: BookmarkId): Promise<Bookmark> {
  return request<Bookmark>(`/bookmarks/${id}`);
}

export function createBookmark(input: BookmarkInput): Promise<Bookmark> {
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
