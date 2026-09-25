import type { KeyboardEvent } from "react";
import type { Bookmark, BookmarkId } from "../types";
import type { BookmarkSortBy } from "../api";
import type { ColumnVisibility } from "../useColumnVisibility";
import BookmarkName from "./BookmarkName";

interface BookmarksTableProps {
  bookmarks: Bookmark[];
  visibility: ColumnVisibility;
  sortBy: BookmarkSortBy;
  sortOrder: "asc" | "desc";
  onToggleSort: (column: BookmarkSortBy) => void;
  onOpenDetail: (id: BookmarkId) => void;
}

export default function BookmarksTable({
  bookmarks,
  visibility,
  sortBy,
  sortOrder,
  onToggleSort,
  onOpenDetail,
}: BookmarksTableProps) {
  function sortIndicator(column: BookmarkSortBy): string {
    if (sortBy !== column) {
      return "";
    }
    return sortOrder === "asc" ? " ▲" : " ▼";
  }

  function handleRowClick(id: BookmarkId) {
    // A click that ends a drag-selection is someone copying a description, not asking for the
    // modal. Without this, selecting text in a row always pops the modal open over it.
    if (window.getSelection()?.toString()) {
      return;
    }
    onOpenDetail(id);
  }

  function handleRowKeyDown(e: KeyboardEvent<HTMLTableRowElement>, id: BookmarkId) {
    if (e.key !== "Enter" && e.key !== " ") {
      return;
    }
    // Only when the row itself has focus: Enter on the name link inside it belongs to the link,
    // and its keydown bubbles up here.
    if (e.target !== e.currentTarget) {
      return;
    }
    // Space would otherwise scroll the page.
    e.preventDefault();
    onOpenDetail(id);
  }

  return (
    <table className="bookmarks-table">
      <thead>
        <tr>
          <th className="sortable" onClick={() => onToggleSort("name")}>
            Name{sortIndicator("name")}
          </th>
          {visibility.description && <th className="col-description">Description</th>}
          {visibility.tags && <th>Tags</th>}
          {visibility.type && <th>Type</th>}
        </tr>
      </thead>
      <tbody>
        {bookmarks.map((bookmark) => (
          // The whole row opens the modal, matching the card list. A table can't use that
          // layout's stretched-button trick (a <tr> is no place for an absolutely positioned
          // overlay), so the row carries the handlers itself — including `tabIndex`, which is
          // what keeps the modal reachable without a mouse now that there's no button.
          <tr
            key={bookmark.id}
            tabIndex={0}
            onClick={() => handleRowClick(bookmark.id)}
            onKeyDown={(e) => handleRowKeyDown(e, bookmark.id)}
          >
            <td>
              <BookmarkName bookmark={bookmark} />
            </td>
            {visibility.description && (
              <td className="col-description">{bookmark.description ?? ""}</td>
            )}
            {visibility.tags && (
              <td>
                <div className="tags">
                  {bookmark.tags.map((tag) => (
                    <span className="tag-pill" key={tag}>
                      {tag}
                    </span>
                  ))}
                </div>
              </td>
            )}
            {visibility.type && (
              <td>
                <span className="type-badge">{bookmark.type}</span>
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
