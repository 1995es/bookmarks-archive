import type { Bookmark, BookmarkId } from "../types";
import type { ColumnVisibility } from "../useColumnVisibility";
import BookmarkName from "./BookmarkName";
import { TypeIcon } from "./icons";

interface BookmarksListProps {
  bookmarks: Bookmark[];
  visibility: ColumnVisibility;
  onOpenDetail: (id: BookmarkId) => void;
}

/**
 * Mobile counterpart to BookmarksTable: one stacked card per bookmark instead of five columns
 * that don't fit. Same two affordances as a table row — the name opens the URL, everything else
 * opens the detail modal — but reached with a stretched button rather than the row's own
 * click handler, since a card can hold one and a <tr> can't.
 */
export default function BookmarksList({ bookmarks, visibility, onOpenDetail }: BookmarksListProps) {
  return (
    <ul className="bookmark-cards">
      {bookmarks.map((bookmark) => (
        <li className="bookmark-card" key={bookmark.id}>
          <div className="bookmark-card-content">
            <BookmarkName bookmark={bookmark} linkClassName="bookmark-card-name" />
            {visibility.description && bookmark.description && (
              <p className="bookmark-card-description">{bookmark.description}</p>
            )}
            <div className="bookmark-card-meta">
              {visibility.type && (
                <span className="type-badge">
                  <TypeIcon type={bookmark.type} size={12} />
                  {bookmark.type}
                </span>
              )}
              {visibility.tags && bookmark.tags.length > 0 && (
                <div className="tags">
                  {bookmark.tags.map((tag) => (
                    <span className="tag-pill" key={tag}>
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
          {/* Stretched over the whole card (see .bookmark-card-open), so a tap anywhere that
              isn't the name link opens the detail modal. */}
          <button
            type="button"
            className="bookmark-card-open"
            aria-label={`View details for ${bookmark.name}`}
            onClick={() => onOpenDetail(bookmark.id)}
          />
        </li>
      ))}
    </ul>
  );
}
