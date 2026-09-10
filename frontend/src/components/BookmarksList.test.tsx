import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import BookmarksList from "./BookmarksList";
import type { Bookmark } from "../types";

function bookmark(overrides: Partial<Bookmark> = {}): Bookmark {
  return {
    id: "id-1",
    name: "Example post",
    url: "https://example.com/post",
    description: "A description",
    tags: ["ai", "tools"],
    type: "post",
    created_at: "2026-03-14T12:00:00Z",
    enrichment_status: "done",
    ...overrides,
  };
}

describe("BookmarksList", () => {
  it("renders the name as a link to the bookmark's url", () => {
    render(<BookmarksList bookmarks={[bookmark()]} onOpenDetail={vi.fn()} />);

    expect(screen.getByRole("link", { name: "Example post" })).toHaveAttribute(
      "href",
      "https://example.com/post",
    );
  });

  it("renders the description, type and tags", () => {
    render(<BookmarksList bookmarks={[bookmark()]} onOpenDetail={vi.fn()} />);

    expect(screen.getByText("A description")).toBeInTheDocument();
    expect(screen.getByText("post")).toBeInTheDocument();
    expect(screen.getByText("ai")).toBeInTheDocument();
    expect(screen.getByText("tools")).toBeInTheDocument();
  });

  it("omits the description paragraph when there is none", () => {
    render(<BookmarksList bookmarks={[bookmark({ description: null })]} onOpenDetail={vi.fn()} />);

    expect(screen.queryByText("A description")).not.toBeInTheDocument();
  });

  it("opens the detail modal from the card-wide button", async () => {
    const onOpenDetail = vi.fn();
    const user = userEvent.setup();
    render(<BookmarksList bookmarks={[bookmark()]} onOpenDetail={onOpenDetail} />);

    await user.click(screen.getByRole("button", { name: /view details for example post/i }));

    expect(onOpenDetail).toHaveBeenCalledWith("id-1");
  });
});
