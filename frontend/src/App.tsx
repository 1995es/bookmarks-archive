import { useCallback, useEffect, useRef, useState } from "react";
import { listBookmarks } from "./api";
import type { BookmarkSortBy, BookmarkSortOrder } from "./api";
import type { Bookmark, BookmarkId, BookmarkType } from "./types";
import { PAGE_SIZE } from "./utils";
import { useMediaQuery } from "./useMediaQuery";
import AddBookmarkForm from "./components/AddBookmarkForm";
import FiltersBar from "./components/FiltersBar";
import BookmarksTable from "./components/BookmarksTable";
import BookmarksList from "./components/BookmarksList";
import SortControl from "./components/SortControl";
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

  // Below this width the five-column table overflows the viewport; cards replace it.
  const isNarrow = useMediaQuery("(max-width: 640px)");

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
    // Deliberate: refresh() is the app's single fetch path and setting `loading`/`bookmarks`
    // from it is the point. There is no external store to subscribe to instead.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh();
  }, [refresh]);

  useEffect(() => {
    // Deliberate: pagination is server-side, so a changed filter/sort must rewind to the first
    // page before the refresh() effect above re-queries.
    // eslint-disable-next-line react-hooks/set-state-in-effect
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

  function goToOffset(nextOffset: number) {
    setOffset(nextOffset);
    // The controls are sticky, so paging from halfway down the list would otherwise leave the
    // reader in the middle of a fresh page with no cue that anything changed. Instant rather
    // than smooth: a smooth scroll races the re-render that shortens the page under it.
    window.scrollTo(0, 0);
  }

  function setSort(nextSortBy: BookmarkSortBy, nextSortOrder: BookmarkSortOrder) {
    setSortBy(nextSortBy);
    setSortOrder(nextSortOrder);
  }

  const selectedBookmark = bookmarks.find((bookmark) => bookmark.id === selectedId) ?? null;

  return (
    <div className="page">
      <h1>Bookmarks</h1>

      {error && <ErrorBanner message={error} />}

      <AddBookmarkForm onCreated={refresh} onError={(message) => setError(message || null)} />

      {/* On a phone the filters, sort and pagination ride together in a sticky bar: the list is
          thousands of pixels tall, and page controls parked at the bottom of it are unreachable. */}
      <div className={isNarrow ? "controls controls-sticky" : "controls"}>
        <FiltersBar
          filterTag={filterTag}
          onFilterTagChange={setFilterTag}
          filterType={filterType}
          onFilterTypeChange={setFilterType}
        />
        {isNarrow && (
          <div className="controls-row">
            <SortControl sortBy={sortBy} sortOrder={sortOrder} onSortChange={setSort} />
            {total > 0 && (
              <Pagination
                compact
                offset={offset}
                total={total}
                pageSize={PAGE_SIZE}
                onOffsetChange={goToOffset}
              />
            )}
          </div>
        )}
      </div>

      {loading && <div className="status-line">Loading…</div>}

      {!loading && bookmarks.length === 0 && <div className="status-line">No bookmarks yet</div>}

      {!loading &&
        bookmarks.length > 0 &&
        (isNarrow ? (
          <BookmarksList bookmarks={bookmarks} onOpenDetail={setSelectedId} />
        ) : (
          <BookmarksTable
            bookmarks={bookmarks}
            sortBy={sortBy}
            sortOrder={sortOrder}
            onToggleSort={toggleSort}
            onOpenDetail={setSelectedId}
          />
        ))}

      {!loading && !isNarrow && total > 0 && (
        <Pagination
          offset={offset}
          total={total}
          pageSize={PAGE_SIZE}
          onOffsetChange={goToOffset}
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
