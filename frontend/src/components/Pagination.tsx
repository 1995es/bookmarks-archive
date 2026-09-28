import { ChevronLeftIcon, ChevronRightIcon } from "./icons";

interface PaginationProps {
  offset: number;
  total: number;
  pageSize: number;
  onOffsetChange: (offset: number) => void;
  /** Bare chevrons instead of labelled buttons, for the sticky mobile control bar. */
  compact?: boolean;
}

export default function Pagination({
  offset,
  total,
  pageSize,
  onOffsetChange,
  compact = false,
}: PaginationProps) {
  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + pageSize, total);
  const hasPrevPage = offset > 0;
  const hasNextPage = offset + pageSize < total;

  return (
    <div className={compact ? "pagination pagination-compact" : "pagination"}>
      <span className="pagination-status">
        {pageStart}–{pageEnd} of {total}
      </span>
      <button
        type="button"
        aria-label="Previous page"
        disabled={!hasPrevPage}
        onClick={() => onOffsetChange(Math.max(0, offset - pageSize))}
      >
        <ChevronLeftIcon size={14} />
        {!compact && "Previous"}
      </button>
      <button
        type="button"
        aria-label="Next page"
        disabled={!hasNextPage}
        onClick={() => onOffsetChange(offset + pageSize)}
      >
        {!compact && "Next"}
        <ChevronRightIcon size={14} />
      </button>
    </div>
  );
}
