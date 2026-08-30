export type BookmarkType = "post" | "video" | "tweet" | "site";

/** Where a bookmark stands in the background enrichment pipeline (read-only,
 * server-derived). "pending" is worth polling for; "done"/"failed" are final. */
export type EnrichmentStatus = "pending" | "done" | "failed";

/** Server-generated UUID (uuid7), serialized as a string. Opaque to the client. */
export type BookmarkId = string;

export interface Bookmark {
  id: BookmarkId;
  name: string;
  url: string;
  description: string | null;
  tags: string[];
  type: BookmarkType;
  created_at: string;
  enrichment_status: EnrichmentStatus;
}

export interface BookmarkInput {
  name: string;
  url: string;
  description: string | null;
  tags: string[];
  type: BookmarkType;
}

/** POST /bookmarks only requires `url`: a blank/omitted `name` is derived server-side
 * from the URL's host, and an omitted `type` defaults to 'post'. */
export interface BookmarkCreateInput {
  name?: string | null;
  url: string;
  description: string | null;
  tags: string[];
  type?: BookmarkType;
}
