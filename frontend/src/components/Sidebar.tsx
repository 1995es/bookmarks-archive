import type { ReactNode } from "react";
import type { BookmarkType } from "../types";
import { BOOKMARK_TYPES, TYPE_LABELS } from "../utils";
import { BookmarkIcon, LayersIcon, PanelCollapseIcon, PanelExpandIcon, TypeIcon } from "./icons";

interface SidebarProps {
  filterType: BookmarkType | "";
  onFilterTypeChange: (value: BookmarkType | "") => void;
  /** Rendered as the icon rail: labels visually hidden, nav items reduced to their icons. */
  collapsed: boolean;
  /** Omitted when the viewport forces the rail, so there is no toggle that can't take effect. */
  onToggleCollapsed?: () => void;
}

/**
 * The wide layout's left rail: the brand, then the type filter as navigation. It is the same
 * state the narrow layout's TypeChips drive (App's `filterType`), just laid out as places to go
 * rather than a control to set — which is what turns a single long page into an app.
 */
export default function Sidebar({
  filterType,
  onFilterTypeChange,
  collapsed,
  onToggleCollapsed,
}: SidebarProps) {
  return (
    <aside className={collapsed ? "sidebar sidebar-collapsed" : "sidebar"}>
      <div className="sidebar-brand">
        <span className="brand-mark">
          <BookmarkIcon size={14} />
        </span>
        <span className="sidebar-brand-name">Bookmarks</span>
      </div>

      <nav className="sidebar-nav" aria-label="Bookmark types">
        <NavItem
          label="All bookmarks"
          icon={<LayersIcon />}
          active={filterType === ""}
          onClick={() => onFilterTypeChange("")}
        />
        <p className="sidebar-section-label">Types</p>
        {BOOKMARK_TYPES.map((type) => (
          <NavItem
            key={type}
            label={TYPE_LABELS[type]}
            icon={<TypeIcon type={type} />}
            active={filterType === type}
            onClick={() => onFilterTypeChange(type)}
          />
        ))}
      </nav>

      {onToggleCollapsed && (
        <button
          type="button"
          className="sidebar-toggle"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          onClick={onToggleCollapsed}
        >
          {collapsed ? <PanelExpandIcon /> : <PanelCollapseIcon />}
        </button>
      )}
    </aside>
  );
}

interface NavItemProps {
  label: string;
  icon: ReactNode;
  active: boolean;
  onClick: () => void;
}

function NavItem({ label, icon, active, onClick }: NavItemProps) {
  return (
    <button
      type="button"
      className={active ? "nav-item nav-item-active" : "nav-item"}
      aria-current={active ? "page" : undefined}
      // The label is visually hidden when the rail collapses to icons, so it can't be the only
      // place the name lives for a hover.
      title={label}
      onClick={onClick}
    >
      {icon}
      <span className="nav-item-label">{label}</span>
    </button>
  );
}
