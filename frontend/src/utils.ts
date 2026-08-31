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

/**
 * How many bulk-add POSTs may be in flight at once. Each one spawns a background
 * enrichment task on the backend that fetches a page and calls an LLM, all writing
 * to a single SQLite file — so pasting a few hundred URLs must not become a few
 * hundred simultaneous requests.
 */
export const BULK_CONCURRENCY = 5;

/**
 * `Promise.allSettled(items.map(worker))` with a cap on how many workers run at
 * once. Results keep the input order, and — like `allSettled` — a rejection is
 * reported rather than aborting the rest.
 */
export async function mapSettledWithLimit<T, R>(
  items: T[],
  limit: number,
  worker: (item: T) => Promise<R>,
): Promise<PromiseSettledResult<R>[]> {
  const results = new Array<PromiseSettledResult<R>>(items.length);
  let next = 0;

  async function runWorker(): Promise<void> {
    while (next < items.length) {
      const index = next++;
      try {
        results[index] = { status: "fulfilled", value: await worker(items[index]) };
      } catch (reason) {
        results[index] = { status: "rejected", reason };
      }
    }
  }

  const workers = Array.from({ length: Math.min(limit, items.length) }, runWorker);
  await Promise.all(workers);
  return results;
}
