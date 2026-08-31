import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import BookmarkDetailModal from "./BookmarkDetailModal";
import { deleteBookmark, retryEnrichment, updateBookmark } from "../api";
import type { Bookmark } from "../types";

vi.mock("../api", () => ({
  deleteBookmark: vi.fn(),
  retryEnrichment: vi.fn(),
  updateBookmark: vi.fn(),
}));

const deleteBookmarkMock = vi.mocked(deleteBookmark);
const retryEnrichmentMock = vi.mocked(retryEnrichment);
const updateBookmarkMock = vi.mocked(updateBookmark);

function bookmark(overrides: Partial<Bookmark> = {}): Bookmark {
  return {
    id: "abc",
    name: "Example",
    url: "https://example.com",
    description: "A description",
    tags: ["react", "testing"],
    type: "post",
    created_at: "2026-03-14T12:00:00Z",
    enrichment_status: "done",
    ...overrides,
  };
}

function renderModal(overrides: Partial<Bookmark> = {}) {
  const props = {
    bookmark: bookmark(overrides),
    onClose: vi.fn(),
    onUpdated: vi.fn().mockResolvedValue(undefined),
    onDeleted: vi.fn().mockResolvedValue(undefined),
    onRetried: vi.fn().mockResolvedValue(undefined),
  };
  const view = render(<BookmarkDetailModal {...props} />);
  return { ...props, ...view, user: userEvent.setup() };
}

beforeEach(() => {
  deleteBookmarkMock.mockReset();
  retryEnrichmentMock.mockReset();
  updateBookmarkMock.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("retry", () => {
  it("offers Retry only when enrichment failed", () => {
    const { unmount } = renderModal({ enrichment_status: "done" });
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    unmount();

    renderModal({ enrichment_status: "pending" });
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("calls retryEnrichment and refreshes when it did fail", async () => {
    retryEnrichmentMock.mockResolvedValue(bookmark({ enrichment_status: "pending" }));
    const { user, onRetried } = renderModal({ enrichment_status: "failed" });

    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(retryEnrichmentMock).toHaveBeenCalledWith("abc");
    await waitFor(() => expect(onRetried).toHaveBeenCalled());
  });

  it("shows the failure inline rather than closing", async () => {
    retryEnrichmentMock.mockRejectedValue(new Error("Enrichment is already running"));
    const { user, onClose } = renderModal({ enrichment_status: "failed" });

    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Enrichment is already running");
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe("closing", () => {
  it("closes on Escape", async () => {
    const { user, onClose } = renderModal();

    await user.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("removes its keydown listener on unmount", async () => {
    const { user, onClose, unmount } = renderModal();
    unmount();

    await user.keyboard("{Escape}");

    expect(onClose).not.toHaveBeenCalled();
  });

  it("closes on an overlay click but not on a click inside the panel", async () => {
    const { user, onClose, container } = renderModal();

    await user.click(container.querySelector(".modal-panel")!);
    expect(onClose).not.toHaveBeenCalled();

    await user.click(container.querySelector(".modal-overlay")!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("delete", () => {
  it("does nothing when the confirm is declined", async () => {
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(false));
    const { user, onDeleted } = renderModal();

    await user.click(screen.getByRole("button", { name: "Delete" }));

    expect(deleteBookmarkMock).not.toHaveBeenCalled();
    expect(onDeleted).not.toHaveBeenCalled();
  });

  it("deletes and notifies the parent when confirmed", async () => {
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
    deleteBookmarkMock.mockResolvedValue(undefined);
    const { user, onDeleted } = renderModal();

    await user.click(screen.getByRole("button", { name: "Delete" }));

    expect(deleteBookmarkMock).toHaveBeenCalledWith("abc");
    await waitFor(() => expect(onDeleted).toHaveBeenCalled());
  });
});

describe("editing", () => {
  it("sends the trimmed draft with tags parsed out of the comma list", async () => {
    updateBookmarkMock.mockResolvedValue(bookmark({ name: "Renamed" }));
    const { user, onUpdated } = renderModal();

    await user.click(screen.getByRole("button", { name: "Edit" }));

    const name = screen.getByLabelText(/^name$/i);
    await user.clear(name);
    await user.type(name, "  Renamed  ");

    const tags = screen.getByLabelText(/tags/i);
    await user.clear(tags);
    await user.type(tags, "react, ,vite");

    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(updateBookmarkMock).toHaveBeenCalledWith("abc", {
      name: "Renamed",
      url: "https://example.com",
      description: "A description",
      tags: ["react", "vite"],
      type: "post",
    });
    await waitFor(() => expect(onUpdated).toHaveBeenCalled());
  });

  it("refuses to save an empty name or url", async () => {
    const { user } = renderModal();

    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.clear(screen.getByLabelText(/^name$/i));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(updateBookmarkMock).not.toHaveBeenCalled();
  });

  it("stays in edit mode and shows the error when the save fails", async () => {
    updateBookmarkMock.mockRejectedValue(new Error("URL already in use"));
    const { user, onUpdated } = renderModal();

    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("URL already in use");
    expect(onUpdated).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
  });
});
