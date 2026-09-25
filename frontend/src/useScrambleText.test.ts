import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SCRAMBLE_TICK_MS, useScrambleText } from "./useScrambleText";

const TEXT = "Cosas que he aprendido";

afterEach(() => {
  vi.useRealTimers();
});

/** Advance `ticks` animation frames inside act(), so React flushes the resulting renders. */
function advance(ticks: number) {
  act(() => {
    vi.advanceTimersByTime(ticks * SCRAMBLE_TICK_MS);
  });
}

describe("useScrambleText", () => {
  it("returns the text unchanged when not animating", () => {
    const { result } = renderHook(() => useScrambleText(TEXT, false));

    expect(result.current).toBe(TEXT);
  });

  it("scrambles immediately when animating, without a frame of the plain text", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useScrambleText(TEXT, true));

    expect(result.current).not.toBe(TEXT);
    expect(result.current).toHaveLength(TEXT.length);
  });

  it("resolves one more character per tick, from the left", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useScrambleText(TEXT, true));

    advance(3);
    expect(result.current.startsWith(TEXT.slice(0, 3))).toBe(true);
    expect(result.current).not.toBe(TEXT);

    advance(3);
    expect(result.current.startsWith(TEXT.slice(0, 6))).toBe(true);
  });

  it("never scrambles the spaces, so the word shapes survive", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useScrambleText(TEXT, true));

    advance(2);
    const spaceIndexes = [...TEXT].flatMap((char, i) => (char === " " ? [i] : []));
    expect(spaceIndexes.length).toBeGreaterThan(0);
    for (const i of spaceIndexes) {
      expect(result.current[i]).toBe(" ");
    }
  });

  it("settles on the exact text once every character has resolved", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useScrambleText(TEXT, true));

    advance(TEXT.length);

    expect(result.current).toBe(TEXT);
  });

  it("restarts on a new text rather than finishing the old one", () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(
      ({ text }: { text: string }) => useScrambleText(text, true),
      { initialProps: { text: TEXT } },
    );

    advance(TEXT.length);
    expect(result.current).toBe(TEXT);

    rerender({ text: "Another title entirely" });
    expect(result.current).not.toBe("Another title entirely");

    advance("Another title entirely".length);
    expect(result.current).toBe("Another title entirely");
  });
});
