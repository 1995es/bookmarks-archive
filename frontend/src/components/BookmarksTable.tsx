import type { Bookmark, BookmarkId } from "../types";
import type { BookmarkSortBy } from "../api";

interface BookmarksTableProps {
  bookmarks: Bookmark[];
  sortBy: BookmarkSortBy;
  sortOrder: "asc" | "desc";
  onToggleSort: (column: BookmarkSortBy) => void;
  onOpenDetail: (id: BookmarkId) => void;
}

export default function BookmarksTable({
  bookmarks,
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

  return (
    <table className="bookmarks-table">
      <thead>
        <tr>
          <th className="sortable" onClick={() => onToggleSort("name")}>
            Name{sortIndicator("name")}
          </th>
          <th>Description</th>
          <th>Tags</th>
          <th>Type</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {bookmarks.map((bookmark) => (
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
            <td>
              <span className="type-badge">{bookmark.type}</span>
            </td>
            <td className="row-actions">
              <button
                type="button"
                className="icon-button"
                aria-label={`View details for ${bookmark.name}`}
                onClick={() => onOpenDetail(bookmark.id)}
              >
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M1.5 12S5 5 12 5s10.5 7 10.5 7-3.5 7-10.5 7S1.5 12 1.5 12Z" />
                  <circle cx="12" cy="12" r="3" />
                </svg>
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
