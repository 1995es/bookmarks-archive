import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import {
  createBookmark,
  deleteBookmark,
  listBookmarks,
  updateBookmark,
} from "./api";
import type {
  Bookmark,
  BookmarkCreateInput,
  BookmarkId,
  BookmarkInput,
  BookmarkType,
} from "./types";

const BOOKMARK_TYPES: BookmarkType[] = ["post", "video", "tweet", "site"];

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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [filterTag, setFilterTag] = useState("");
  const [filterType, setFilterType] = useState<BookmarkType | "">("");

  const [newBookmark, setNewBookmark] = useState<NewBookmarkForm>(EMPTY_NEW_BOOKMARK);
  const [submitting, setSubmitting] = useState(false);
  const [showMoreFields, setShowMoreFields] = useState(false);

  const [editingId, setEditingId] = useState<BookmarkId | null>(null);
  const [editDraft, setEditDraft] = useState<EditDraft | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listBookmarks({
        tag: filterTag.trim() || undefined,
        type: filterType || undefined,
      });
      setBookmarks(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [filterTag, filterType]);

  useEffect(() => {
    refresh();
  }, [refresh]);

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

  const addDisabled = submitting || !newBookmark.url.trim();

  return (
    <div className="page">
      <h1>Bookmarks</h1>

      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}

      <form className="add-form" onSubmit={handleAddSubmit}>
        <div className="add-form-row">
          <input
            type="text"
            placeholder="URL"
            value={newBookmark.url}
            onChange={(e) => setNewBookmark({ ...newBookmark, url: e.target.value })}
          />
          <button type="submit" disabled={addDisabled}>
            Add bookmark
          </button>
        </div>

        <label className="add-form-toggle">
          <input
            type="checkbox"
            checked={showMoreFields}
            onChange={(e) => setShowMoreFields(e.target.checked)}
          />
          Add more details
        </label>

        {showMoreFields && (
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
              <th>Name</th>
              <th>Description</th>
              <th>Tags</th>
              <th>Type</th>
              <th>Date added</th>
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
    </div>
  );
}
