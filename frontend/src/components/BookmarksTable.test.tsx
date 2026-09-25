import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import BookmarksTable from "./BookmarksTable";
import { DEFAULT_COLUMN_VISIBILITY } from "../useColumnVisibility";
import type { Bookmark } from "../types";

function bookmark(overrides: Partial<Bookmark> = {}): Bookmark {
  return {
    id: "id-1",
    name: "Example post",
    url: "https://example.com/post",
    description: "A description",
    tags: ["ai"],
    type: "post",
    created_at: "2026-03-14T12:00:00Z",
    enrichment_status: "done",
    favicon_url: null,
    ...overrides,
  };
}

function renderTable(onOpenDetail = vi.fn()) {
  const view = render(
    <BookmarksTable
      bookmarks={[bookmark()]}
      visibility={DEFAULT_COLUMN_VISIBILITY}
      sortBy="created_at"
      sortOrder="desc"
      onToggleSort={vi.fn()}
      onOpenDetail={onOpenDetail}
    />,
  );
  return { ...view, onOpenDetail, user: userEvent.setup() };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("opening the detail modal", () => {
  it("opens it from a click anywhere in the row", async () => {
    const { user, onOpenDetail } = renderTable();

    await user.click(screen.getByText("A description"));

    expect(onOpenDetail).toHaveBeenCalledWith("id-1");
  });

  it("opens it from the keyboard, the row being the only control now", () => {
    const { onOpenDetail } = renderTable();

    // [0] is the header row.
    fireEvent.keyDown(screen.getAllByRole("row")[1], { key: "Enter" });

    expect(onOpenDetail).toHaveBeenCalledWith("id-1");
  });

  it("leaves Enter on the focused name link to the link", () => {
    const { onOpenDetail } = renderTable();

    fireEvent.keyDown(screen.getByRole("link", { name: "Example post" }), { key: "Enter" });

    expect(onOpenDetail).not.toHaveBeenCalled();
  });

  it("leaves the name link alone: it opens the bookmark, not the modal", async () => {
    const { user, onOpenDetail } = renderTable();

    const link = screen.getByRole("link", { name: "Example post" });
    expect(link).toHaveAttribute("href", "https://example.com/post");
    await user.click(link);

    expect(onOpenDetail).not.toHaveBeenCalled();
  });

  it("ignores the click that ends a text selection", async () => {
    // Copying a description out of a row shouldn't pop the modal open over it.
    vi.spyOn(window, "getSelection").mockReturnValue({
      toString: () => "A description",
    } as unknown as Selection);
    const { user, onOpenDetail } = renderTable();

    await user.click(screen.getByText("A description"));

    expect(onOpenDetail).not.toHaveBeenCalled();
  });
});
