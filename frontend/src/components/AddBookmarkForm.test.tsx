import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AddBookmarkForm from "./AddBookmarkForm";
import { createBookmark } from "../api";
import type { Bookmark } from "../types";
import { BULK_CONCURRENCY } from "../utils";

vi.mock("../api", () => ({ createBookmark: vi.fn() }));

const createBookmarkMock = vi.mocked(createBookmark);

function created(url: string): Bookmark {
  return {
    id: url,
    name: url,
    url,
    description: null,
    tags: [],
    type: "post",
    created_at: "2026-03-14T12:00:00Z",
    enrichment_status: "pending",
  };
}

function renderForm() {
  const onCreated = vi.fn().mockResolvedValue(undefined);
  const onError = vi.fn();
  render(<AddBookmarkForm onCreated={onCreated} onError={onError} />);
  return { onCreated, onError, user: userEvent.setup() };
}

async function enterBulkMode(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByLabelText(/bulk add/i));
  return screen.getByPlaceholderText(/one url per line/i);
}

beforeEach(() => {
  createBookmarkMock.mockReset();
});

describe("single add", () => {
  it("posts the trimmed url and clears the field", async () => {
    createBookmarkMock.mockResolvedValue(created("https://example.com"));
    const { user, onCreated } = renderForm();

    const input = screen.getByPlaceholderText("URL");
    await user.type(input, "  https://example.com  ");
    await user.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    expect(createBookmarkMock).toHaveBeenCalledWith(
      expect.objectContaining({ url: "https://example.com" }),
    );
    expect(input).toHaveValue("");
  });

  it("reports a failure through onError and keeps the typed url", async () => {
    createBookmarkMock.mockRejectedValue(new Error("Bookmark URL already exists"));
    const { user, onError, onCreated } = renderForm();

    await user.type(screen.getByPlaceholderText("URL"), "https://dupe.example");
    await user.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => expect(onError).toHaveBeenCalledWith("Bookmark URL already exists"));
    expect(onCreated).not.toHaveBeenCalled();
    expect(screen.getByPlaceholderText("URL")).toHaveValue("https://dupe.example");
  });

  it("disables Add until a url is typed", async () => {
    const { user } = renderForm();

    expect(screen.getByRole("button", { name: "Add" })).toBeDisabled();
    await user.type(screen.getByPlaceholderText("URL"), "https://example.com");
    expect(screen.getByRole("button", { name: "Add" })).toBeEnabled();
  });
});

describe("bulk add", () => {
  it("posts every url and reports the count when all succeed", async () => {
    createBookmarkMock.mockImplementation(({ url }) => Promise.resolve(created(url)));
    const { user, onCreated } = renderForm();

    const textarea = await enterBulkMode(user);
    await user.type(textarea, "https://a.example\nhttps://b.example\nhttps://c.example");
    await user.click(screen.getByRole("button", { name: "Add all" }));

    expect(await screen.findByText(/3 added/)).toBeInTheDocument();
    expect(createBookmarkMock).toHaveBeenCalledTimes(3);
    expect(onCreated).toHaveBeenCalled();
    expect(textarea).toHaveValue("");
  });

  it("lists each failure and keeps only the failed urls in the textarea", async () => {
    createBookmarkMock.mockImplementation(({ url }) =>
      url.includes("bad")
        ? Promise.reject(new Error("A bookmark with this URL already exists"))
        : Promise.resolve(created(url)),
    );
    const { user } = renderForm();

    const textarea = await enterBulkMode(user);
    await user.type(
      textarea,
      "https://ok1.example\nhttps://bad1.example\nhttps://ok2.example\nhttps://bad2.example",
    );
    await user.click(screen.getByRole("button", { name: "Add all" }));

    expect(await screen.findByText(/2 added, 2 failed/)).toBeInTheDocument();

    const failures = screen.getAllByRole("listitem").map((li) => li.textContent);
    expect(failures).toEqual([
      "https://bad1.example: A bookmark with this URL already exists",
      "https://bad2.example: A bookmark with this URL already exists",
    ]);

    // The retention behaviour: a resubmit retries only what failed.
    expect(textarea).toHaveValue("https://bad1.example\nhttps://bad2.example");
  });

  it("splits on any whitespace, so space-separated urls work too", async () => {
    createBookmarkMock.mockImplementation(({ url }) => Promise.resolve(created(url)));
    const { user } = renderForm();

    const textarea = await enterBulkMode(user);
    await user.type(textarea, "https://a.example https://b.example");
    await user.click(screen.getByRole("button", { name: "Add all" }));

    expect(await screen.findByText(/2 added/)).toBeInTheDocument();
  });

  it("disables the button on an empty textarea and while submitting", async () => {
    const inFlight: Array<(bookmark: Bookmark) => void> = [];
    createBookmarkMock.mockImplementation(
      ({ url }) => new Promise((resolve) => inFlight.push(() => resolve(created(url)))),
    );
    const { user } = renderForm();

    const textarea = await enterBulkMode(user);
    const button = screen.getByRole("button", { name: "Add all" });
    expect(button).toBeDisabled();

    await user.type(textarea, "   \n  ");
    expect(button).toBeDisabled();

    await user.clear(textarea);
    await user.type(textarea, "https://a.example");
    expect(button).toBeEnabled();

    await user.click(button);
    await waitFor(() => expect(button).toBeDisabled());
    expect(screen.getByText(/Adding 1 bookmarks…/)).toBeInTheDocument();

    inFlight.forEach((resolve) => resolve(created("https://a.example")));
    expect(await screen.findByText(/1 added/)).toBeInTheDocument();
  });

  it("caps how many creates are in flight at once", async () => {
    let inFlight = 0;
    let peak = 0;
    const release: Array<() => void> = [];
    createBookmarkMock.mockImplementation(({ url }) => {
      inFlight += 1;
      peak = Math.max(peak, inFlight);
      return new Promise((resolve) =>
        release.push(() => {
          inFlight -= 1;
          resolve(created(url));
        }),
      );
    });
    const { user } = renderForm();

    const urls = Array.from({ length: 40 }, (_, i) => `https://site-${i}.example`);
    const textarea = await enterBulkMode(user);
    await user.click(textarea);
    await user.paste(urls.join("\n"));
    await user.click(screen.getByRole("button", { name: "Add all" }));

    await waitFor(() => expect(createBookmarkMock).toHaveBeenCalledTimes(BULK_CONCURRENCY));
    while (release.length > 0) {
      release.shift()!();
      await waitFor(() => expect(inFlight).toBeLessThanOrEqual(BULK_CONCURRENCY));
    }

    expect(await screen.findByText(/40 added/)).toBeInTheDocument();
    expect(peak).toBe(BULK_CONCURRENCY);
  });

  it("clears a previous result when bulk mode is toggled off and on", async () => {
    createBookmarkMock.mockImplementation(({ url }) => Promise.resolve(created(url)));
    const { user } = renderForm();

    const textarea = await enterBulkMode(user);
    await user.type(textarea, "https://a.example");
    await user.click(screen.getByRole("button", { name: "Add all" }));
    expect(await screen.findByText(/1 added/)).toBeInTheDocument();

    await user.click(screen.getByLabelText(/bulk add/i));
    await user.click(screen.getByLabelText(/bulk add/i));

    expect(screen.queryByText(/1 added/)).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText(/one url per line/i)).toHaveValue("");
  });
});
