import { useState } from "react";
import type { Bookmark } from "../types";
import { hostOf } from "../utils";

interface BookmarkFaviconProps {
  bookmark: Bookmark;
  /** Extra class for the size/shape a particular surface wants. */
  className?: string;
}

/**
 * The bookmark's favicon, falling back to the first letter of its host on a tile.
 *
 * Shared by the table, the card list and the detail modal so all three degrade the same way —
 * this is the only place that knows the fallback chain.
 *
 * A stored icon URL can rot (the site redesigns, or starts blocking hotlinks), so a failed load
 * is an expected state rather than an error. The failure is tracked per icon URL: adjusting that
 * state during render, rather than making callers remember to pass a `key`, means a bookmark
 * whose icon changes gets a fresh attempt automatically.
 */
export default function BookmarkFavicon({ bookmark, className }: BookmarkFaviconProps) {
  const faviconUrl = bookmark.favicon_url;
  const [failedUrl, setFailedUrl] = useState<string | null>(null);

  if (faviconUrl && failedUrl !== faviconUrl) {
    return (
      <img
        className={className ? `bookmark-favicon ${className}` : "bookmark-favicon"}
        src={faviconUrl}
        alt=""
        loading="lazy"
        // The browser fetches this straight from the bookmarked site; don't tell that site
        // which page the reader is looking at while it happens.
        referrerPolicy="no-referrer"
        onError={() => setFailedUrl(faviconUrl)}
      />
    );
  }

  return (
    <span
      className={className ? `bookmark-favicon-letter ${className}` : "bookmark-favicon-letter"}
      aria-hidden="true"
    >
      {hostOf(bookmark.url).slice(0, 1)}
    </span>
  );
}
