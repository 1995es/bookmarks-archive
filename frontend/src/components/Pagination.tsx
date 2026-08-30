interface PaginationProps {
  offset: number;
  total: number;
  pageSize: number;
  onOffsetChange: (offset: number) => void;
}

export default function Pagination({ offset, total, pageSize, onOffsetChange }: PaginationProps) {
  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + pageSize, total);
  const hasPrevPage = offset > 0;
  const hasNextPage = offset + pageSize < total;

  return (
    <div className="pagination">
      <span className="pagination-status">
        {pageStart}–{pageEnd} of {total}
      </span>
      <button
        type="button"
        disabled={!hasPrevPage}
        onClick={() => onOffsetChange(Math.max(0, offset - pageSize))}
      >
        Previous
      </button>
      <button
        type="button"
        disabled={!hasNextPage}
        onClick={() => onOffsetChange(offset + pageSize)}
      >
        Next
      </button>
    </div>
  );
}
