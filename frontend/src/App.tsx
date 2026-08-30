import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  createBookmark,
  deleteBookmark,
  listBookmarks,
  updateBookmark,
} from "./api";
import type { BookmarkSortBy, BookmarkSortOrder } from "./api";
import type {
  Bookmark,
  BookmarkCreateInput,
  BookmarkId,
  BookmarkInput,
  BookmarkType,
} from "./types";

const BOOKMARK_TYPES: BookmarkType[] = ["post", "video", "tweet", "site"];
const PAGE_SIZE = 20;

function parseTags(input: string): string[] {
  return input
    .split(",")
    .map((tag) => tag.trim())
    .filter((tag) => tag.length > 0);
}

function formatDate(iso: string): string {
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

interface NewBookmarkForm {
  name: string;
  url: string;
  description: string;
  tagsInput: string;
  type: BookmarkType;
}

const EMPTY_NEW_BOOKMARK: NewBookmarkForm = {
  name: "",
  url: "",
  description: "",
  tagsInput: "",
  type: "post",
};

interface BulkFailure {
  url: string;
  error: string;
}

interface BulkResult {
  succeeded: number;
  failed: BulkFailure[];
}

function parseBulkUrls(input: string): string[] {
  return input
    .split(/\s+/)
    .map((url) => url.trim())
    .filter((url) => url.length > 0);
}

interface EditDraft {
  name: string;
  url: string;
  description: string;
  tagsInput: string;
  type: BookmarkType;
}

function toEditDraft(bookmark: Bookmark): EditDraft {
  return {
    name: bookmark.name,
    url: bookmark.url,
    description: bookmark.description ?? "",
    tagsInput: bookmark.tags.join(", "),
    type: bookmark.type,
  };
}

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

  const [newBookmark, setNewBookmark] = useState<NewBookmarkForm>(EMPTY_NEW_BOOKMARK);
  const [submitting, setSubmitting] = useState(false);
  const [showMoreFields, setShowMoreFields] = useState(false);

  const [bulkMode, setBulkMode] = useState(false);
  const [bulkText, setBulkText] = useState("");
  const [bulkSubmitting, setBulkSubmitting] = useState(false);
  const [bulkResult, setBulkResult] = useState<BulkResult | null>(null);

  function toggleBulkMode() {
    setBulkMode(!bulkMode);
    setBulkResult(null);
    setBulkText("");
  }

  const [editingId, setEditingId] = useState<BookmarkId | null>(null);
  const [editDraft, setEditDraft] = useState<EditDraft | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);

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

  async function handleAddSubmit(e: FormEvent) {
    e.preventDefault();
    const url = newBookmark.url.trim();
    if (!url) {
      return;
    }
    setSubmitting(true);
    setError(null);
    const input: BookmarkCreateInput = {
      name: newBookmark.name.trim() || undefined,
      url,
      description: newBookmark.description.trim() || null,
      tags: parseTags(newBookmark.tagsInput),
      type: newBookmark.type,
    };
    try {
      await createBookmark(input);
      setNewBookmark(EMPTY_NEW_BOOKMARK);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleBulkSubmit(e: FormEvent) {
    e.preventDefault();
    const urls = parseBulkUrls(bulkText);
    if (urls.length === 0) {
      return;
    }
    setBulkSubmitting(true);
    setBulkResult(null);
    setError(null);
    const outcomes = await Promise.allSettled(
      urls.map((url) => createBookmark({ url, description: null, tags: [] })),
    );
    const failed: BulkFailure[] = [];
    let succeeded = 0;
    outcomes.forEach((outcome, i) => {
      if (outcome.status === "fulfilled") {
        succeeded += 1;
      } else {
        const err = outcome.reason;
        failed.push({ url: urls[i], error: err instanceof Error ? err.message : String(err) });
      }
    });
    setBulkResult({ succeeded, failed });
    setBulkText(failed.map((f) => f.url).join("\n"));
    setBulkSubmitting(false);
    await refresh();
  }

  function startEdit(bookmark: Bookmark) {
    setEditingId(bookmark.id);
    setEditDraft(toEditDraft(bookmark));
  }

  function cancelEdit() {
    setEditingId(null);
    setEditDraft(null);
  }

  async function saveEdit(id: BookmarkId) {
    if (!editDraft) return;
    if (!editDraft.name.trim() || !editDraft.url.trim()) {
      return;
    }
    setSavingEdit(true);
    setError(null);
    const input: BookmarkInput = {
      name: editDraft.name.trim(),
      url: editDraft.url.trim(),
      description: editDraft.description.trim() || null,
      tags: parseTags(editDraft.tagsInput),
      type: editDraft.type,
    };
    try {
      await updateBookmark(id, input);
      setEditingId(null);
      setEditDraft(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSavingEdit(false);
    }
  }

  async function handleDelete(id: BookmarkId) {
    if (!window.confirm("Delete this bookmark? This cannot be undone.")) {
      return;
    }
    setError(null);
    try {
      await deleteBookmark(id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  function toggleSort(column: BookmarkSortBy) {
    if (sortBy === column) {
      setSortOrder((order) => (order === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(column);
      setSortOrder("asc");
    }
  }

  function sortIndicator(column: BookmarkSortBy): string {
    if (sortBy !== column) {
      return "";
    }
    return sortOrder === "asc" ? " ▲" : " ▼";
  }

  const addDisabled = bulkMode
    ? bulkSubmitting || parseBulkUrls(bulkText).length === 0
    : submitting || !newBookmark.url.trim();
  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + PAGE_SIZE, total);
  const hasPrevPage = offset > 0;
  const hasNextPage = offset + PAGE_SIZE < total;

  return (
    <div className="page">
      <h1>Bookmarks</h1>

      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}

      <form className="add-form" onSubmit={bulkMode ? handleBulkSubmit : handleAddSubmit}>
        <div className="add-form-row">
          {bulkMode ? (
            <textarea
              className="bulk-url-input"
              placeholder="One URL per line"
              rows={4}
              value={bulkText}
              onChange={(e) => setBulkText(e.target.value)}
            />
          ) : (
            <div className="clearable-input">
              <input
                type="text"
                placeholder="URL"
                value={newBookmark.url}
                onChange={(e) => setNewBookmark({ ...newBookmark, url: e.target.value })}
              />
              {newBookmark.url && (
                <button
                  type="button"
                  className="clear-input-button"
                  aria-label="Clear URL"
                  onClick={() => setNewBookmark({ ...newBookmark, url: "" })}
                >
                  ×
                </button>
              )}
            </div>
          )}
          <button type="submit" disabled={addDisabled}>
            {bulkMode ? "Add all" : "Add"}
          </button>
        </div>

        <label className="add-form-toggle">
          <input
            type="checkbox"
            checked={bulkMode}
            onChange={toggleBulkMode}
          />
          Bulk add
        </label>

        {bulkMode && bulkSubmitting && (
          <div className="status-line">
            Adding {parseBulkUrls(bulkText).length} bookmarks…
          </div>
        )}

        {bulkMode && bulkResult && !bulkSubmitting && (
          <div className="bulk-add-summary">
            <p>
              {bulkResult.succeeded} added
              {bulkResult.failed.length > 0 && `, ${bulkResult.failed.length} failed`}.
            </p>
            {bulkResult.failed.length > 0 && (
              <ul className="bulk-add-failures">
                {bulkResult.failed.map((failure) => (
                  <li key={failure.url}>
                    <strong>{failure.url}</strong>: {failure.error}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {!bulkMode && newBookmark.url.trim() !== "" && (
          <label className="add-form-toggle">
            <input
              type="checkbox"
              checked={showMoreFields}
              onChange={(e) => setShowMoreFields(e.target.checked)}
            />
            Add more details
          </label>
        )}

        {!bulkMode && newBookmark.url.trim() !== "" && showMoreFields && (
          <div className="add-form-row">
            <input
              type="text"
              placeholder="Name (optional, taken from URL otherwise)"
              value={newBookmark.name}
              onChange={(e) => setNewBookmark({ ...newBookmark, name: e.target.value })}
            />
            <input
              type="text"
              placeholder="Description"
              value={newBookmark.description}
              onChange={(e) => setNewBookmark({ ...newBookmark, description: e.target.value })}
            />
            <input
              type="text"
              placeholder="Tags (comma separated)"
              value={newBookmark.tagsInput}
              onChange={(e) => setNewBookmark({ ...newBookmark, tagsInput: e.target.value })}
            />
            <select
              value={newBookmark.type}
              onChange={(e) =>
                setNewBookmark({ ...newBookmark, type: e.target.value as BookmarkType })
              }
            >
              {BOOKMARK_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </div>
        )}
      </form>

      <div className="filters">
        <input
          type="text"
          placeholder="Filter by tag"
          value={filterTag}
          onChange={(e) => setFilterTag(e.target.value)}
        />
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value as BookmarkType | "")}
        >
          <option value="">All types</option>
          {BOOKMARK_TYPES.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </div>

      {loading && <div className="status-line">Loading…</div>}

      {!loading && bookmarks.length === 0 && (
        <div className="status-line">No bookmarks yet</div>
      )}

      {!loading && bookmarks.length > 0 && (
        <table className="bookmarks-table">
          <thead>
            <tr>
              <th className="sortable" onClick={() => toggleSort("name")}>
                Name{sortIndicator("name")}
              </th>
              <th>Description</th>
              <th>Tags</th>
              <th>Type</th>
              <th className="sortable" onClick={() => toggleSort("created_at")}>
                Date added{sortIndicator("created_at")}
              </th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {bookmarks.map((bookmark) => {
              const isEditing = editingId === bookmark.id;

              if (isEditing && editDraft) {
                return (
                  <tr key={bookmark.id}>
                    <td>
                      <input
                        type="text"
                        value={editDraft.name}
                        onChange={(e) =>
                          setEditDraft({ ...editDraft, name: e.target.value })
                        }
                      />
                      <input
                        type="text"
                        value={editDraft.url}
                        onChange={(e) =>
                          setEditDraft({ ...editDraft, url: e.target.value })
                        }
                      />
                    </td>
                    <td>
                      <input
                        type="text"
                        value={editDraft.description}
                        onChange={(e) =>
                          setEditDraft({ ...editDraft, description: e.target.value })
                        }
                      />
                    </td>
                    <td>
                      <input
                        type="text"
                        value={editDraft.tagsInput}
                        onChange={(e) =>
                          setEditDraft({ ...editDraft, tagsInput: e.target.value })
                        }
                      />
                    </td>
                    <td>
                      <select
                        value={editDraft.type}
                        onChange={(e) =>
                          setEditDraft({
                            ...editDraft,
                            type: e.target.value as BookmarkType,
                          })
                        }
                      >
                        {BOOKMARK_TYPES.map((type) => (
                          <option key={type} value={type}>
                            {type}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>{formatDate(bookmark.created_at)}</td>
                    <td className="row-actions">
                      <button
                        type="button"
                        disabled={savingEdit}
                        onClick={() => saveEdit(bookmark.id)}
                      >
                        Save
                      </button>
                      <button type="button" disabled={savingEdit} onClick={cancelEdit}>
                        Cancel
                      </button>
                    </td>
                  </tr>
                );
              }

              return (
                <tr key={bookmark.id}>
                  <td>
                    <a href={bookmark.url} target="_blank" rel="noreferrer">
                      {bookmark.name}
                    </a>
                  </td>
                  <td>{bookmark.description ?? ""}</td>
                  <td>
                    <div className="tags">
                      {bookmark.tags.map((tag) => (
                        <span className="tag-pill" key={tag}>
                          {tag}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td>{bookmark.type}</td>
                  <td>{formatDate(bookmark.created_at)}</td>
                  <td className="row-actions">
                    <button type="button" onClick={() => startEdit(bookmark)}>
                      Edit
                    </button>
                    <button type="button" onClick={() => handleDelete(bookmark.id)}>
                      Delete
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {!loading && total > 0 && (
        <div className="pagination">
          <span className="pagination-status">
            {pageStart}–{pageEnd} of {total}
          </span>
          <button
            type="button"
            disabled={!hasPrevPage}
            onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))}
          >
            Previous
          </button>
          <button
            type="button"
            disabled={!hasNextPage}
            onClick={() => setOffset((current) => current + PAGE_SIZE)}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
