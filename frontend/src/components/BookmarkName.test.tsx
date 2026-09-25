import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import BookmarkName from "./BookmarkName";
import { SCRAMBLE_TICK_MS } from "../useScrambleText";
import type { Bookmark } from "../types";

const NAME = "Cosas que he aprendido sobre IA";
const URL = "https://jesuslc.com/2026/04/13/cosas-que-he-aprendido/";

function bookmark(overrides: Partial<Bookmark> = {}): Bookmark {
  return {
    id: "id-1",
    name: NAME,
    url: URL,
    description: null,
    tags: [],
    type: "post",
    created_at: "2026-03-14T12:00:00Z",
    enrichment_status: "done",
    favicon_url: null,
    ...overrides,
  };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("BookmarkName", () => {
  it("shows the url and a pending indicator while enrichment is pending", () => {
    render(
      <BookmarkName bookmark={bookmark({ enrichment_status: "pending", name: "jesuslc.com" })} />,
    );

    expect(screen.getByRole("link")).toHaveTextContent(URL);
    expect(screen.getByRole("status", { name: /fetching page details/i })).toBeInTheDocument();
    expect(screen.queryByText("jesuslc.com")).not.toBeInTheDocument();
  });

  it("shows the name with no indicator once enrichment is done", () => {
    render(<BookmarkName bookmark={bookmark()} />);

    expect(screen.getByRole("link", { name: NAME })).toHaveAttribute("href", URL);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("does not animate a bookmark that is already done on first render", () => {
    vi.useFakeTimers();
    render(<BookmarkName bookmark={bookmark()} />);

    expect(screen.getByRole("link")).toHaveTextContent(NAME);
  });

  it("scrambles into the real name when the status flips from pending to done", () => {
    vi.useFakeTimers();
    const { rerender } = render(
      <BookmarkName bookmark={bookmark({ enrichment_status: "pending", name: "jesuslc.com" })} />,
    );

    rerender(<BookmarkName bookmark={bookmark()} />);

    // Mid-flight: the right length, the leading characters correct, but not yet the real name.
    const midFlight = screen.getByRole("link").textContent ?? "";
    expect(midFlight).toHaveLength(NAME.length);
    expect(midFlight).not.toBe(NAME);

    act(() => {
      vi.advanceTimersByTime(NAME.length * SCRAMBLE_TICK_MS);
    });

    expect(screen.getByRole("link")).toHaveTextContent(NAME);
  });

  it("keeps the real name in the title attribute while the text is scrambling", () => {
    vi.useFakeTimers();
    const { rerender } = render(
      <BookmarkName bookmark={bookmark({ enrichment_status: "pending", name: "jesuslc.com" })} />,
    );

    rerender(<BookmarkName bookmark={bookmark()} />);

    expect(screen.getByRole("link")).toHaveAttribute("title", NAME);
  });

  describe("favicon", () => {
    const ICON = "https://jesuslc.com/favicon.ico";

    it("renders the stored favicon once enrichment is done", () => {
      const { container } = render(<BookmarkName bookmark={bookmark({ favicon_url: ICON })} />);

      const img = container.querySelector(".bookmark-favicon");
      expect(img).toHaveAttribute("src", ICON);
      // The bookmarked site shouldn't learn which page the reader is on.
      expect(img).toHaveAttribute("referrerpolicy", "no-referrer");
    });

    it("falls back to the host's initial when the page declares no icon", () => {
      const { container } = render(<BookmarkName bookmark={bookmark({ favicon_url: null })} />);

      expect(container.querySelector(".bookmark-favicon")).not.toBeInTheDocument();
      expect(container.querySelector(".bookmark-favicon-letter")).toHaveTextContent("j");
    });

    it("falls back to the host's initial when the icon fails to load", () => {
      // A stored icon URL rots when a site redesigns or starts blocking hotlinks.
      const { container } = render(<BookmarkName bookmark={bookmark({ favicon_url: ICON })} />);

      fireEvent.error(container.querySelector(".bookmark-favicon")!);

      expect(container.querySelector(".bookmark-favicon")).not.toBeInTheDocument();
      expect(container.querySelector(".bookmark-favicon-letter")).toHaveTextContent("j");
    });

    it("shows the pending dots instead of any icon while enrichment is pending", () => {
      const { container } = render(
        <BookmarkName bookmark={bookmark({ enrichment_status: "pending", favicon_url: ICON })} />,
      );

      expect(container.querySelector(".bookmark-favicon")).not.toBeInTheDocument();
      expect(container.querySelector(".enrichment-dots")).toBeInTheDocument();
    });
  });
});
