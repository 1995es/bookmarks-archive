import { useCallback, useEffect, useRef, useState } from "react";
import { listBookmarks } from "./api";
import type { BookmarkSortBy, BookmarkSortOrder } from "./api";
import type { Bookmark, BookmarkId, BookmarkType } from "./types";
import { PAGE_SIZE } from "./utils";
import AddBookmarkForm from "./components/AddBookmarkForm";
import FiltersBar from "./components/FiltersBar";
import BookmarksTable from "./components/BookmarksTable";
import Pagination from "./components/Pagination";
import BookmarkDetailModal from "./components/BookmarkDetailModal";
import ErrorBanner from "./components/ErrorBanner";

export default function App() {
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [filterTag, setFilterTag] = useState("");
  const [filterType, setFilterType] = useState<BookmarkType | "">("");

  const [sortBy, setSortBy] = useState<BookmarkSortBy>("created_at");
  const [sortOrder, setSortOrder] = useState<BookmarkSortOrder>("desc");
  const [offset, setOffset] = useState(0);

  const [selectedId, setSelectedId] = useState<BookmarkId | null>(null);

  // Monotonic counter guarding against out-of-order responses: a slow earlier
  // request must not overwrite the list rendered by a later one.
  const requestSeq = useRef(0);

  const refresh = useCallback(async () => {
    const seq = ++requestSeq.current;
    setLoading(true);
    setError(null);
    try {
      const page = await listBookmarks({
        tag: filterTag.trim() || undefined,
        type: filterType || undefined,
        sortBy,
        sortOrder,
        limit: PAGE_SIZE,
        offset,
      });
      if (seq !== requestSeq.current) {
        return;
      }
      setBookmarks(page.items);
      setTotal(page.total);
    } catch (err) {
      if (seq !== requestSeq.current) {
        return;
      }
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (seq === requestSeq.current) {
        setLoading(false);
      }
    }
  }, [filterTag, filterType, sortBy, sortOrder, offset]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    setOffset(0);
  }, [filterTag, filterType, sortBy, sortOrder]);

  const hasPendingEnrichment = bookmarks.some(
    (bookmark) => bookmark.enrichment_status === "pending",
  );

  useEffect(() => {
    if (!hasPendingEnrichment) {
      return;
    }
    const intervalId = setInterval(async () => {
      const seq = ++requestSeq.current;
      try {
        const page = await listBookmarks({
          tag: filterTag.trim() || undefined,
          type: filterType || undefined,
          sortBy,
          sortOrder,
          limit: PAGE_SIZE,
          offset,
        });
        if (seq !== requestSeq.current) {
          return;
        }
        setBookmarks(page.items);
        setTotal(page.total);
      } catch {
        // silent: this is a background poll, the next refresh() will surface errors
      }
    }, 5000);
    return () => clearInterval(intervalId);
  }, [hasPendingEnrichment, filterTag, filterType, sortBy, sortOrder, offset]);

  function toggleSort(column: BookmarkSortBy) {
    if (sortBy === column) {
      setSortOrder((order) => (order === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(column);
      setSortOrder("asc");
    }
  }

  const selectedBookmark = bookmarks.find((bookmark) => bookmark.id === selectedId) ?? null;

  return (
    <div className="page">
      <h1>Bookmarks</h1>

      {error && <ErrorBanner message={error} />}

      <AddBookmarkForm
        onCreated={refresh}
        onError={(message) => setError(message || null)}
      />

      <FiltersBar
        filterTag={filterTag}
        onFilterTagChange={setFilterTag}
        filterType={filterType}
        onFilterTypeChange={setFilterType}
      />

      {loading && <div className="status-line">Loading…</div>}

      {!loading && bookmarks.length === 0 && (
        <div className="status-line">No bookmarks yet</div>
      )}

      {!loading && bookmarks.length > 0 && (
        <BookmarksTable
          bookmarks={bookmarks}
          sortBy={sortBy}
          sortOrder={sortOrder}
          onToggleSort={toggleSort}
          onOpenDetail={setSelectedId}
        />
      )}

      {!loading && total > 0 && (
        <Pagination
          offset={offset}
          total={total}
          pageSize={PAGE_SIZE}
          onOffsetChange={setOffset}
        />
      )}

      {selectedBookmark && (
        <BookmarkDetailModal
          bookmark={selectedBookmark}
          onClose={() => setSelectedId(null)}
          onUpdated={refresh}
          onDeleted={async () => {
            setSelectedId(null);
            await refresh();
          }}
          onRetried={refresh}
        />
      )}
    </div>
  );
}
