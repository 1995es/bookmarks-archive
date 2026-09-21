import { useCallback, useEffect, useState } from "react";

/**
 * The bookmark fields the reader can hide. `name` and the detail button are not toggleable —
 * a row with neither would have nothing to click.
 */
export const TOGGLEABLE_COLUMNS = ["description", "tags", "type"] as const;

export type ToggleableColumn = (typeof TOGGLEABLE_COLUMNS)[number];

export type ColumnVisibility = Record<ToggleableColumn, boolean>;

export const COLUMN_LABELS: Record<ToggleableColumn, string> = {
  description: "Description",
  tags: "Tags",
  type: "Type",
};

export const DEFAULT_COLUMN_VISIBILITY: ColumnVisibility = {
  description: true,
  tags: true,
  type: true,
};

const STORAGE_KEY = "bookmarks-archive:visible-columns";

/**
 * Reads the stored preference, falling back to "everything visible" for anything missing or
 * malformed. localStorage itself can throw (Safari private browsing, storage disabled), and a
 * hand-edited or stale value must not be able to blank out the table, so every key is validated
 * individually rather than trusting the parsed shape.
 */
function readStored(): ColumnVisibility {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return DEFAULT_COLUMN_VISIBILITY;
    }
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) {
      return DEFAULT_COLUMN_VISIBILITY;
    }
    const stored = parsed as Partial<Record<ToggleableColumn, unknown>>;
    const visibility = { ...DEFAULT_COLUMN_VISIBILITY };
    for (const column of TOGGLEABLE_COLUMNS) {
      if (typeof stored[column] === "boolean") {
        visibility[column] = stored[column];
      }
    }
    return visibility;
  } catch {
    return DEFAULT_COLUMN_VISIBILITY;
  }
}

/**
 * Which bookmark columns are shown, persisted to localStorage so the choice survives a reload.
 * This is a display preference only — hidden columns are still fetched and still visible in the
 * detail modal, so nothing about the query in App.tsx depends on it.
 */
export function useColumnVisibility(): [ColumnVisibility, (column: ToggleableColumn) => void] {
  const [visibility, setVisibility] = useState<ColumnVisibility>(readStored);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(visibility));
    } catch {
      // Storage unavailable (private mode, quota): the preference just doesn't outlive the tab.
    }
  }, [visibility]);

  const toggleColumn = useCallback((column: ToggleableColumn) => {
    setVisibility((current) => ({ ...current, [column]: !current[column] }));
  }, []);

  return [visibility, toggleColumn];
}
