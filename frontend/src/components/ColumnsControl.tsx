import { useEffect, useRef, useState } from "react";
import type { ColumnVisibility, ToggleableColumn } from "../useColumnVisibility";
import { COLUMN_LABELS, TOGGLEABLE_COLUMNS } from "../useColumnVisibility";
import { ChevronDownIcon, ColumnsIcon } from "./icons";

interface ColumnsControlProps {
  visibility: ColumnVisibility;
  onToggleColumn: (column: ToggleableColumn) => void;
}

/**
 * Popover of checkboxes choosing which columns the table (and, on a phone, which fields the
 * cards) show. A menu rather than three inline checkboxes because it has to fit the sticky
 * mobile control bar next to the filters and pagination.
 */
export default function ColumnsControl({ visibility, onToggleColumn }: ColumnsControlProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    function onPointerDown(event: PointerEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className="columns-control" ref={containerRef}>
      <button
        type="button"
        className="columns-trigger"
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((isOpen) => !isOpen)}
      >
        <ColumnsIcon className="columns-icon" />
        Columns
        <ChevronDownIcon className="columns-chevron" size={12} />
      </button>
      {open && (
        <div className="columns-menu">
          {/* The heading carries the meaning, which is what lets the trigger stay one word. */}
          <p className="columns-menu-label">Toggle columns</p>
          {TOGGLEABLE_COLUMNS.map((column) => (
            <label className="columns-menu-item" key={column}>
              <input
                type="checkbox"
                checked={visibility[column]}
                onChange={() => onToggleColumn(column)}
              />
              {COLUMN_LABELS[column]}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
