import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { listBookmarks } from "./api";
import type { BookmarkPage, ListBookmarksParams } from "./api";
import type { Bookmark } from "./types";

vi.mock("./api", () => ({
  listBookmarks: vi.fn(),
  createBookmark: vi.fn(),
  updateBookmark: vi.fn(),
  deleteBookmark: vi.fn(),
  retryEnrichment: vi.fn(),
}));

const listBookmarksMock = vi.mocked(listBookmarks);

function bookmark(name: string): Bookmark {
  return {
    id: name,
    name,
    url: `https://example.com/${name}`,
    description: null,
    tags: [],
    type: "post",
    created_at: "2026-03-14T12:00:00Z",
    enrichment_status: "done",
  };
}

function page(names: string[]): BookmarkPage {
  return { items: names.map(bookmark), total: names.length };
}

/** A promise plus the handles to settle it later. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

beforeEach(() => {
  listBookmarksMock.mockReset();
});

describe("stale-response guard", () => {
  it("does not let a slow earlier response overwrite a later one", async () => {
    const slow = deferred<BookmarkPage>();
    listBookmarksMock.mockReturnValueOnce(slow.promise).mockResolvedValue(page(["fresh"]));

    const user = userEvent.setup();
    render(<App />);

    // The first (slow) request is in flight; typing a filter fires a second one.
    await user.type(screen.getByPlaceholderText(/filter by tag/i), "x");
    await screen.findByText("fresh");

    // The earlier request now comes back with different data — it must be dropped.
    slow.resolve(page(["stale"]));
    await waitFor(() => expect(listBookmarksMock).toHaveBeenCalled());

    expect(screen.queryByText("stale")).not.toBeInTheDocument();
    expect(screen.getByText("fresh")).toBeInTheDocument();
  });

  it("does not let a superseded request clear loading or raise its error", async () => {
    const slow = deferred<BookmarkPage>();
    const pending = deferred<BookmarkPage>();
    listBookmarksMock.mockReturnValueOnce(slow.promise).mockReturnValueOnce(pending.promise);

    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByPlaceholderText(/filter by tag/i), "x");
    expect(screen.getByText("Loading…")).toBeInTheDocument();

    // The superseded request fails; neither the banner nor `loading` may react.
    slow.reject(new Error("stale failure"));
    await waitFor(() => expect(listBookmarksMock).toHaveBeenCalledTimes(2));

    expect(screen.queryByText("stale failure")).not.toBeInTheDocument();
    expect(screen.getByText("Loading…")).toBeInTheDocument();

    pending.resolve(page(["fresh"]));
    await screen.findByText("fresh");
    expect(screen.queryByText("Loading…")).not.toBeInTheDocument();
  });

  it("surfaces the error of the request that is actually current", async () => {
    listBookmarksMock.mockRejectedValue(new Error("backend is down"));

    render(<App />);

    expect(await screen.findByRole("alert")).toHaveTextContent("backend is down");
  });
});

describe("filters", () => {
  it("resets offset to 0 when a filter changes", async () => {
    listBookmarksMock.mockResolvedValue({
      items: Array.from({ length: 20 }, (_, i) => bookmark(`b${i}`)),
      total: 60,
    });

    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("b0");

    await user.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() => expect(lastParams().offset).toBe(20));

    await user.type(screen.getByPlaceholderText(/filter by tag/i), "react");

    await waitFor(() => {
      const params = lastParams();
      expect(params.tag).toBe("react");
      expect(params.offset).toBe(0);
    });
  });

  it("sends the trimmed tag, and omits it entirely when blank", async () => {
    listBookmarksMock.mockResolvedValue(page(["a"]));

    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("a");

    await user.type(screen.getByPlaceholderText(/filter by tag/i), "  react  ");
    await waitFor(() => expect(lastParams().tag).toBe("react"));

    await user.clear(screen.getByPlaceholderText(/filter by tag/i));
    await waitFor(() => expect(lastParams().tag).toBeUndefined());
  });
});

function lastParams(): ListBookmarksParams {
  return listBookmarksMock.mock.calls.at(-1)![0] ?? {};
}
