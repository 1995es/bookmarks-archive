import { useState } from "react";
import type { Bookmark } from "../types";
import { useMediaQuery } from "../useMediaQuery";
import { useScrambleText } from "../useScrambleText";
import BookmarkFavicon from "./BookmarkFavicon";

/** Per-dot animation durations and delays, in seconds. Deliberately coprime-ish values: a
 *  shared period would make the nine dots pulse as one block instead of shimmering. */
const DOT_DURATIONS = [1.4, 1.1, 1.6, 1.3, 1.8, 1, 1.5, 1.2, 1.7];
const DOT_DELAYS = [0, 0.4, 0.2, 0.6, 0.1, 0.8, 0.3, 0.7, 0.5];

/** The 3x3 pulsing grid that stands in for the (not yet fetched) page identity. It occupies the
 *  same slot a favicon will, so resolving a bookmark doesn't shift the name sideways. */
function EnrichmentDots() {
  return (
    <span className="enrichment-dots" role="status" aria-label="Fetching page details">
      {DOT_DELAYS.map((delay, i) => (
        <span
          key={i}
          className="enrichment-dot"
          style={{ animationDuration: `${DOT_DURATIONS[i]}s`, animationDelay: `${delay}s` }}
        />
      ))}
    </span>
  );
}

interface BookmarkNameProps {
  bookmark: Bookmark;
  /** Applied to the anchor, so the card list keeps its own name styling. */
  linkClassName?: string;
}

/**
 * The bookmark's name, plus the enrichment state around it — shared by the table and the card
 * list so both tell the same story.
 *
 * While enrichment is pending the backend's name is a placeholder derived from the host, which
 * says nothing the URL doesn't; so the URL itself is shown, shimmering, next to the pulsing dot
 * grid. When the status flips to "done" the real name arrives and is revealed with the
 * arrival-board scramble (see useScrambleText).
 *
 * The animation fires only on a pending -> done transition observed *by this row*, never on
 * first render: a page of already-enriched bookmarks would otherwise scramble on every load,
 * and on every poll that remounts the list.
 */
export default function BookmarkName({ bookmark, linkClassName }: BookmarkNameProps) {
  const status = bookmark.enrichment_status;
  const isPending = status === "pending";
  const reducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)");

  // Adjusting state during render (rather than in an effect) is React's documented pattern for
  // reacting to a changed prop: the extra render happens before the browser paints, so the name
  // never appears unscrambled for a frame first.
  const [previousStatus, setPreviousStatus] = useState(status);
  const [scrambling, setScrambling] = useState<string | null>(null);
  if (previousStatus !== status) {
    setPreviousStatus(status);
    if (previousStatus === "pending" && status === "done" && !reducedMotion) {
      setScrambling(bookmark.name);
    }
  }

  const displayText = isPending ? bookmark.url : bookmark.name;
  const text = useScrambleText(displayText, !isPending && scrambling === bookmark.name);

  return (
    <span className="bookmark-name">
      <span className="bookmark-name-slot">
        {isPending ? <EnrichmentDots /> : <BookmarkFavicon bookmark={bookmark} />}
      </span>
      <a
        className={linkClassName}
        href={bookmark.url}
        target="_blank"
        rel="noreferrer"
        // The name opens the bookmark; everything around it opens the detail modal. Both
        // layouts wrap this link in a click target (the table's row handler, the card's
        // stretched button), so the link has to keep the click to itself.
        onClick={(e) => e.stopPropagation()}
        // The scrambled text is transient noise; the title attribute always holds the real one.
        title={displayText}
      >
        <span className={isPending ? "bookmark-name-text text-shimmer" : "bookmark-name-text"}>
          {text}
        </span>
      </a>
    </span>
  );
}
