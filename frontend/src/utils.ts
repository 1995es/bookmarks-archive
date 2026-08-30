import type { BookmarkType } from "./types";

export const BOOKMARK_TYPES: BookmarkType[] = ["post", "video", "tweet", "site"];
export const PAGE_SIZE = 20;

export function parseTags(input: string): string[] {
  return input
    .split(",")
    .map((tag) => tag.trim())
    .filter((tag) => tag.length > 0);
}

export function parseBulkUrls(input: string): string[] {
  return input
    .split(/\s+/)
    .map((url) => url.trim())
    .filter((url) => url.length > 0);
}

export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
