import { useEffect, useState } from "react";
import { deleteBookmark, retryEnrichment, updateBookmark } from "../api";
import type { Bookmark, BookmarkInput, BookmarkType } from "../types";
import { BOOKMARK_TYPES, formatDate, parseTags } from "../utils";

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

interface BookmarkDetailModalProps {
  bookmark: Bookmark;
  onClose: () => void;
  onUpdated: () => Promise<void>;
  onDeleted: () => Promise<void>;
  onRetried: () => Promise<void>;
}

export default function BookmarkDetailModal({
  bookmark,
  onClose,
  onUpdated,
  onDeleted,
  onRetried,
}: BookmarkDetailModalProps) {
  const [editing, setEditing] = useState(false);
  const [editDraft, setEditDraft] = useState<EditDraft>(() => toEditDraft(bookmark));
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  function startEdit() {
    setEditDraft(toEditDraft(bookmark));
    setLocalError(null);
    setEditing(true);
  }

  function cancelEdit() {
    setEditing(false);
  }

  async function saveEdit() {
    if (!editDraft.name.trim() || !editDraft.url.trim()) {
      return;
    }
    setSaving(true);
    setLocalError(null);
    const input: BookmarkInput = {
      name: editDraft.name.trim(),
      url: editDraft.url.trim(),
      description: editDraft.description.trim() || null,
      tags: parseTags(editDraft.tagsInput),
      type: editDraft.type,
    };
    try {
      await updateBookmark(bookmark.id, input);
      setEditing(false);
      await onUpdated();
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!window.confirm("Delete this bookmark? This cannot be undone.")) {
      return;
    }
    setDeleting(true);
    setLocalError(null);
    try {
      await deleteBookmark(bookmark.id);
      await onDeleted();
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : String(err));
      setDeleting(false);
    }
  }

  async function handleRetry() {
    setRetrying(true);
    setLocalError(null);
    try {
      await retryEnrichment(bookmark.id);
      await onRetried();
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : String(err));
    } finally {
      setRetrying(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{editing ? "Edit bookmark" : bookmark.name}</h2>
          <button type="button" className="icon-button" aria-label="Close" onClick={onClose}>
            ×
          </button>
        </div>

        {localError && (
          <div className="error-banner" role="alert">
            {localError}
          </div>
        )}

        {editing ? (
          <div className="modal-body">
            <label className="modal-field">
              Name
              <input
                type="text"
                value={editDraft.name}
                onChange={(e) => setEditDraft({ ...editDraft, name: e.target.value })}
              />
            </label>
            <label className="modal-field">
              URL
              <input
                type="text"
                value={editDraft.url}
                onChange={(e) => setEditDraft({ ...editDraft, url: e.target.value })}
              />
            </label>
            <label className="modal-field">
              Description
              <input
                type="text"
                value={editDraft.description}
                onChange={(e) => setEditDraft({ ...editDraft, description: e.target.value })}
              />
            </label>
            <label className="modal-field">
              Tags (comma separated)
              <input
                type="text"
                value={editDraft.tagsInput}
                onChange={(e) => setEditDraft({ ...editDraft, tagsInput: e.target.value })}
              />
            </label>
            <label className="modal-field">
              Type
              <select
                value={editDraft.type}
                onChange={(e) =>
                  setEditDraft({ ...editDraft, type: e.target.value as BookmarkType })
                }
              >
                {BOOKMARK_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </label>

            <div className="modal-actions">
              <button type="button" disabled={saving} onClick={saveEdit}>
                Save
              </button>
              <button type="button" disabled={saving} onClick={cancelEdit}>
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div className="modal-body">
            <div className="detail-row">
              <span className="detail-label">Status</span>
              <span className={`status-badge status-${bookmark.enrichment_status}`}>
                {bookmark.enrichment_status}
              </span>
              {bookmark.enrichment_status === "failed" && (
                <button type="button" disabled={retrying} onClick={handleRetry}>
                  {retrying ? "Retrying…" : "Retry"}
                </button>
              )}
            </div>

            <div className="detail-row">
              <span className="detail-label">URL</span>
              <a href={bookmark.url} target="_blank" rel="noreferrer">
                {bookmark.url}
              </a>
            </div>

            <div className="detail-row">
              <span className="detail-label">Date added</span>
              <span>{formatDate(bookmark.created_at)}</span>
            </div>

            <div className="detail-row">
              <span className="detail-label">Description</span>
              <span>{bookmark.description || "—"}</span>
            </div>

            <div className="detail-row">
              <span className="detail-label">Tags</span>
              <div className="tags">
                {bookmark.tags.length === 0 && "—"}
                {bookmark.tags.map((tag) => (
                  <span className="tag-pill" key={tag}>
                    {tag}
                  </span>
                ))}
              </div>
            </div>

            <div className="detail-row">
              <span className="detail-label">Type</span>
              <span>{bookmark.type}</span>
            </div>

            <div className="modal-actions">
              <button type="button" onClick={startEdit}>
                Edit
              </button>
              <button type="button" disabled={deleting} onClick={handleDelete}>
                {deleting ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
