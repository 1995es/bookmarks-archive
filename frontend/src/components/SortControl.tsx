import type { BookmarkSortBy, BookmarkSortOrder } from "../api";

const SORT_OPTIONS: { value: string; label: string }[] = [
  { value: "created_at:desc", label: "Newest first" },
  { value: "created_at:asc", label: "Oldest first" },
  { value: "name:asc", label: "Name A–Z" },
  { value: "name:desc", label: "Name Z–A" },
];

interface SortControlProps {
  sortBy: BookmarkSortBy;
  sortOrder: BookmarkSortOrder;
  onSortChange: (sortBy: BookmarkSortBy, sortOrder: BookmarkSortOrder) => void;
}

/**
 * Sorting for the card layout, which has no column headers to click. Field and direction are one
 * control on purpose: two taps to reverse an order is a poor trade on a phone.
 */
export default function SortControl({ sortBy, sortOrder, onSortChange }: SortControlProps) {
  return (
    <select
      aria-label="Sort by"
      value={`${sortBy}:${sortOrder}`}
      onChange={(e) => {
        const [nextBy, nextOrder] = e.target.value.split(":");
        onSortChange(nextBy as BookmarkSortBy, nextOrder as BookmarkSortOrder);
      }}
    >
      {SORT_OPTIONS.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}
