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
