import type { Bookmark, BookmarkId } from "../types";

interface BookmarksListProps {
  bookmarks: Bookmark[];
  onOpenDetail: (id: BookmarkId) => void;
}

/**
 * Mobile counterpart to BookmarksTable: one stacked card per bookmark instead of five columns
 * that don't fit. Same two affordances as a table row — the name opens the URL, everything else
 * opens the detail modal — but the modal target is the whole card rather than a 16px icon.
 */
export default function BookmarksList({ bookmarks, onOpenDetail }: BookmarksListProps) {
  return (
    <ul className="bookmark-cards">
      {bookmarks.map((bookmark) => (
        <li className="bookmark-card" key={bookmark.id}>
          <div className="bookmark-card-content">
            <a className="bookmark-card-name" href={bookmark.url} target="_blank" rel="noreferrer">
              {bookmark.name}
            </a>
            {bookmark.description && (
              <p className="bookmark-card-description">{bookmark.description}</p>
            )}
            <div className="bookmark-card-meta">
              <span className="type-badge">{bookmark.type}</span>
              {bookmark.tags.length > 0 && (
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
