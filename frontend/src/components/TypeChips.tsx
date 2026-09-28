import type { BookmarkType } from "../types";
import { BOOKMARK_TYPES, TYPE_LABELS } from "../utils";

interface TypeChipsProps {
  filterType: BookmarkType | "";
  onFilterTypeChange: (value: BookmarkType | "") => void;
}

/**
 * The narrow layout's stand-in for the Sidebar: the same type filter as a row of pill chips that
 * scrolls sideways, since a phone has no room for a left rail.
 */
export default function TypeChips({ filterType, onFilterTypeChange }: TypeChipsProps) {
  const options: { value: BookmarkType | ""; label: string }[] = [
    { value: "", label: "All" },
    ...BOOKMARK_TYPES.map((type) => ({ value: type, label: TYPE_LABELS[type] })),
  ];
  return (
    <div className="type-chips" role="group" aria-label="Bookmark types">
      {options.map((option) => (
        <button
          key={option.value || "all"}
          type="button"
          className={filterType === option.value ? "chip chip-active" : "chip"}
          aria-pressed={filterType === option.value}
          onClick={() => onFilterTypeChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
