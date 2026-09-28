import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "bookmarks-archive:sidebar-collapsed";

/** Anything but a stored `true` means expanded — including storage that throws outright
 *  (private mode, storage disabled) or a hand-edited value. */
function readStored(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

/**
 * Whether the reader has collapsed the sidebar to its icon rail, persisted to localStorage so the
 * choice survives a reload. A display preference only, like useColumnVisibility: nothing about
 * the query depends on it.
 */
export function useSidebarCollapsed(): [boolean, () => void] {
  const [collapsed, setCollapsed] = useState(readStored);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, String(collapsed));
    } catch {
      // Storage unavailable: the preference just doesn't outlive the tab.
    }
  }, [collapsed]);

  const toggle = useCallback(() => setCollapsed((current) => !current), []);

  return [collapsed, toggle];
}
