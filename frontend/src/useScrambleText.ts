import { useEffect, useState } from "react";

/** The alphabet the unresolved characters cycle through. Digits included, so a title that
 *  contains numbers doesn't visibly "settle" early on them. */
const SCRAMBLE_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";

/** One character resolves per tick; ~16ms is a frame, so a 60-char title takes about a second. */
export const SCRAMBLE_TICK_MS = 16;

/**
 * One frame of the effect: the first `revealed` characters are final, the rest are noise.
 * Spaces are never scrambled — keeping the word shapes intact is what makes a half-resolved
 * title read as a title rather than as a block of line noise.
 */
function scrambleFrame(text: string, revealed: number): string {
  let frame = text.slice(0, revealed);
  for (let i = revealed; i < text.length; i++) {
    frame +=
      text[i] === " " ? " " : SCRAMBLE_CHARS[Math.floor(Math.random() * SCRAMBLE_CHARS.length)];
  }
  return frame;
}

/**
 * Airport-arrival-board effect: while `animate` is true, `text` is revealed one character per
 * tick from the left while the remaining characters keep shuffling.
 *
 * Returns `text` unchanged when `animate` is false, so the caller can gate the whole effect on
 * a status transition (and on `prefers-reduced-motion`) without branching on the return value.
 *
 * The rendered frame is derived rather than mirrored into state on mount: state holds the frame
 * *and the text it belongs to*, so a caller whose `text` changes mid-animation gets a correct
 * first frame in the same render instead of one tick of the previous title.
 */
export function useScrambleText(text: string, animate: boolean): string {
  const [frame, setFrame] = useState<{ text: string; value: string } | null>(null);

  useEffect(() => {
    if (!animate) {
      return;
    }
    const startedAt = Date.now();
    const intervalId = setInterval(() => {
      // How much is revealed is derived from elapsed time rather than from a count of ticks:
      // browsers clamp timers to ~1s in a hidden tab, and counting ticks would leave a
      // half-scrambled title sitting there for a minute after the reader comes back. Off
      // elapsed time, a throttled tab simply catches up.
      const revealed = Math.floor((Date.now() - startedAt) / SCRAMBLE_TICK_MS);
      if (revealed >= text.length) {
        clearInterval(intervalId);
        setFrame({ text, value: text });
        return;
      }
      setFrame({ text, value: scrambleFrame(text, revealed) });
    }, SCRAMBLE_TICK_MS);
    return () => clearInterval(intervalId);
  }, [text, animate]);

  if (!animate) {
    return text;
  }
  return frame?.text === text ? frame.value : scrambleFrame(text, 0);
}
