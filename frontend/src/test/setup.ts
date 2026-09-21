import "@testing-library/jest-dom/vitest";

// jsdom has no matchMedia, and useMediaQuery (the desktop/mobile layout switch) calls it during
// render. Default to "no query matches", i.e. the desktop layout, for tests that don't care;
// a test that wants the mobile layout stubs window.matchMedia itself.
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
}

// jsdom doesn't implement scrolling; App calls scrollTo when the page changes.
window.scrollTo = () => {};

// This jsdom build ships no Storage implementation, and the column-visibility preference reads
// window.localStorage during the first render. An in-memory stand-in keeps that path exercised;
// tests that care about persistence clear it themselves.
if (!window.localStorage) {
  const store = new Map<string, string>();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => void store.set(key, String(value)),
      removeItem: (key: string) => void store.delete(key),
      clear: () => store.clear(),
      key: (index: number) => [...store.keys()][index] ?? null,
      get length() {
        return store.size;
      },
    } satisfies Storage,
  });
}
