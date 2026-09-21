import type { ReactNode } from "react";
import type { BookmarkType } from "../types";
import { BOOKMARK_TYPES } from "../utils";

interface FiltersBarProps {
  filterTag: string;
  onFilterTagChange: (value: string) => void;
  filterType: BookmarkType | "";
  onFilterTypeChange: (value: BookmarkType | "") => void;
  /** Trailing slot on the same row — the columns menu rides here in both layouts. */
  children?: ReactNode;
}

export default function FiltersBar({
  filterTag,
  onFilterTagChange,
  filterType,
  onFilterTypeChange,
  children,
}: FiltersBarProps) {
  return (
    <div className="filters">
      <input
        type="text"
        placeholder="Filter by tag"
        value={filterTag}
        onChange={(e) => onFilterTagChange(e.target.value)}
      />
      <select
        value={filterType}
        onChange={(e) => onFilterTypeChange(e.target.value as BookmarkType | "")}
      >
        <option value="">All types</option>
        {BOOKMARK_TYPES.map((type) => (
          <option key={type} value={type}>
            {type}
          </option>
        ))}
      </select>
      {children}
    </div>
  );
}
