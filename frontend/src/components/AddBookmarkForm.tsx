import { useState } from "react";
import type { FormEvent } from "react";
import { createBookmark } from "../api";
import type { BookmarkCreateInput, BookmarkType } from "../types";
import {
  BOOKMARK_TYPES,
  BULK_CONCURRENCY,
  mapSettledWithLimit,
  parseBulkUrls,
  parseTags,
} from "../utils";

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

interface AddBookmarkFormProps {
  onCreated: () => Promise<void>;
  onError: (message: string) => void;
}

export default function AddBookmarkForm({ onCreated, onError }: AddBookmarkFormProps) {
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

  async function handleAddSubmit(e: FormEvent) {
    e.preventDefault();
    const url = newBookmark.url.trim();
    if (!url) {
      return;
    }
    setSubmitting(true);
    onError("");
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
      await onCreated();
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
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
    onError("");
    const outcomes = await mapSettledWithLimit(urls, BULK_CONCURRENCY, (url) =>
      createBookmark({ url, description: null, tags: [] }),
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
    await onCreated();
  }

  const addDisabled = bulkMode
    ? bulkSubmitting || parseBulkUrls(bulkText).length === 0
    : submitting || !newBookmark.url.trim();

  return (
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
        <input type="checkbox" checked={bulkMode} onChange={toggleBulkMode} />
        Bulk add
      </label>

      {bulkMode && bulkSubmitting && (
        <div className="status-line">Adding {parseBulkUrls(bulkText).length} bookmarks…</div>
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
  );
}
