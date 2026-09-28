import type { ReactNode } from "react";
import { SearchIcon } from "./icons";

interface FiltersBarProps {
  filterTag: string;
  onFilterTagChange: (value: string) => void;
  /** Trailing slot on the same row — the columns menu rides here in both layouts. */
  children?: ReactNode;
}

/** The tag filter. The type filter lives in the Sidebar (wide) or TypeChips (narrow). */
export default function FiltersBar({ filterTag, onFilterTagChange, children }: FiltersBarProps) {
  return (
    <div className="filters">
      <label className="search-field">
        <SearchIcon className="search-field-icon" />
        <input
          type="text"
          placeholder="Filter by tag"
          value={filterTag}
          onChange={(e) => onFilterTagChange(e.target.value)}
        />
      </label>
      {children}
    </div>
  );
}
