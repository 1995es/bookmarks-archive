import { describe, expect, it } from "vitest";
import { formatDate, mapSettledWithLimit, parseBulkUrls, parseTags } from "./utils";

describe("parseTags", () => {
  it("splits on commas and trims each tag", () => {
    expect(parseTags("react, testing ,vite")).toEqual(["react", "testing", "vite"]);
  });

  it("returns an empty list for empty input", () => {
    expect(parseTags("")).toEqual([]);
    expect(parseTags("   ")).toEqual([]);
  });

  it("drops empty segments left by stray commas", () => {
    expect(parseTags("a, ,b")).toEqual(["a", "b"]);
    expect(parseTags(",,a,,")).toEqual(["a"]);
  });
});

describe("parseBulkUrls", () => {
  it("splits newline-separated input", () => {
    expect(parseBulkUrls("https://a.example\nhttps://b.example")).toEqual([
      "https://a.example",
      "https://b.example",
    ]);
  });

  it("splits space-separated input too", () => {
    expect(parseBulkUrls("https://a.example https://b.example")).toEqual([
      "https://a.example",
      "https://b.example",
    ]);
  });

  it("ignores blank lines and surrounding whitespace", () => {
    expect(parseBulkUrls("\n  https://a.example  \n\n\thttps://b.example\n")).toEqual([
      "https://a.example",
      "https://b.example",
    ]);
  });

  it("returns an empty list for whitespace-only input", () => {
    expect(parseBulkUrls("   \n \t ")).toEqual([]);
  });
});

describe("formatDate", () => {
  it("formats a valid ISO timestamp", () => {
    // Locale-dependent, so assert on the parts rather than an exact string.
    const formatted = formatDate("2026-03-14T12:00:00Z");
    expect(formatted).toContain("2026");
    expect(formatted).not.toEqual("2026-03-14T12:00:00Z");
  });

  it("returns the input unchanged when it isn't a parseable date", () => {
    expect(formatDate("not a date")).toBe("not a date");
    expect(formatDate("")).toBe("");
  });
});

describe("mapSettledWithLimit", () => {
  /** A worker that records how many calls are in flight at any moment. */
  function trackingWorker() {
    let inFlight = 0;
    let peak = 0;
    const release: Array<() => void> = [];
    const worker = (item: string) => {
      inFlight += 1;
      peak = Math.max(peak, inFlight);
      return new Promise<string>((resolve) => {
        release.push(() => {
          inFlight -= 1;
          resolve(item.toUpperCase());
        });
      });
    };
    return { worker, release, peak: () => peak };
  }

  it("never runs more than `limit` workers at once", async () => {
    const items = Array.from({ length: 50 }, (_, i) => `url-${i}`);
    const { worker, release, peak } = trackingWorker();

    const pending = mapSettledWithLimit(items, 5, worker);

    // Drain the queue one settled call at a time, checking the cap as we go.
    while (release.length > 0) {
      expect(peak()).toBeLessThanOrEqual(5);
      release.shift()!();
      await Promise.resolve();
    }
    await pending;

    expect(peak()).toBe(5);
  });

  it("keeps results in input order regardless of completion order", async () => {
    const delays: Record<string, number> = { a: 30, b: 0, c: 10 };
    const results = await mapSettledWithLimit(
      ["a", "b", "c"],
      3,
      (item) => new Promise<string>((resolve) => setTimeout(() => resolve(item), delays[item])),
    );

    expect(results).toEqual([
      { status: "fulfilled", value: "a" },
      { status: "fulfilled", value: "b" },
      { status: "fulfilled", value: "c" },
    ]);
  });

  it("reports rejections instead of aborting the remaining work", async () => {
    const seen: string[] = [];
    const results = await mapSettledWithLimit(["a", "boom", "c"], 1, async (item) => {
      seen.push(item);
      if (item === "boom") {
        throw new Error("nope");
      }
      return item;
    });

    expect(seen).toEqual(["a", "boom", "c"]);
    expect(results.map((r) => r.status)).toEqual(["fulfilled", "rejected", "fulfilled"]);
    expect((results[1] as PromiseRejectedResult).reason).toEqual(new Error("nope"));
  });

  it("handles an empty list and a list shorter than the limit", async () => {
    expect(await mapSettledWithLimit([], 5, async (item) => item)).toEqual([]);
    expect(await mapSettledWithLimit(["a"], 5, async (item) => item)).toEqual([
      { status: "fulfilled", value: "a" },
    ]);
  });
});
