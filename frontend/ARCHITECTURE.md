# Frontend architecture

React 19 + TypeScript + Vite single-page app for the bookmarks manager. No state manager, no
data-fetching library, no component library, no CSS framework — the scope doesn't justify one, and
keeping it that way is a design decision rather than an unfinished migration.

For the system-level picture see the repo-root [`ARCHITECTURE.md`](../ARCHITECTURE.md).

## Commands

```bash
npm install
npm run dev        # vite --host 0.0.0.0, port 5173
npm run lint         # eslint
npm run format:check # prettier --check src
npm run typecheck    # tsc -b, plus the tests under tsconfig.test.json
npm run test         # vitest, watch mode
npm run test:run     # vitest, once
npm run build        # tsc -b && vite build → dist/
npm run preview
```

Tests are Vitest + Testing Library, configured in the `test` block of `vite.config.ts` so there is
one config to look at rather than a second toolchain. They live next to what they cover, as
`*.test.ts`/`*.test.tsx`. `tsconfig.json` excludes them — `npm run build` would otherwise typecheck
them against the app config and trip over the test globals — and `tsconfig.test.json` picks them
back up, so `npm run typecheck` still covers both. `tsconfig.json` is strict and enables
`noUnusedLocals`/`noUnusedParameters`, so a dead variable breaks the build rather than just showing
up in the editor.

## Structure

A handful of files under `src/`, and that is intended to stay small:

| File | Role |
|---|---|
| `App.tsx` | Composition root: owns the list, filters, sort, pagination, the enrichment poll, and the selected-bookmark id. |
| `components/` | `Sidebar`, `TypeChips`, `AddBookmarkForm`, `FiltersBar`, `ColumnsControl`, `SortControl`, `BookmarkName`, `BookmarkFavicon`, `BookmarksTable`, `BookmarksList`, `Pagination`, `BookmarkDetailModal`, `ErrorBanner`, plus `icons.tsx` (inline line icons). |
| `useMediaQuery.ts` | Subscribes to a CSS media query; drives the table/card layout switch below. |
| `useColumnVisibility.ts` | Which of the description/tags/type columns are shown, persisted in `localStorage`. |
| `useSidebarCollapsed.ts` | Whether the sidebar is collapsed to its icon rail, persisted in `localStorage`. |
| `useScrambleText.ts` | Reveals a string left to right while the tail keeps shuffling — see [The enrichment effect](#the-enrichment-effect). |
| `api.ts` | `fetch` wrappers, one per endpoint, plus shared error handling. |
| `types.ts` | Hand-written mirror of the backend's Pydantic schemas. |
| `utils.ts` | Input parsing (`parseTags`, `parseBulkUrls`), `formatDate`, `hostOf`, the type labels, and the bulk-add worker pool. |
| `index.css` | Plain CSS, no framework. Design tokens in `:root` plus every component rule — see [Design system](#design-system). |

### Design system

The interface follows a "scholar's parchment" language: a warm off-white canvas, warm ink-dark
text, hairline warm-grey rules, and one restrained teal. Type is a single family (Inter) at two
weights, 400 and 500 — hierarchy comes from size, colour and spacing rather than from bold.

The page is a two-pane app: a left sidebar holding the brand and the type filter as navigation,
and a main column with the add form as its focal "hero" block, then the filters, the list and
pagination. Structure comes from tone and spacing rather than outlines: controls are soft fills,
the list sits directly on the canvas divided by hairline rules, and corners are small.

The defining choice is **one colour, used only to say where you are** — the active sidebar item, a
selected chip, the focus glow:

| Token | Value | Where it is used |
|---|---|---|
| `--color-parchment` | `#faf8f5` | The page canvas |
| `--color-soft-paper` | `#fdfbfa` | What lifts off the page: a focused field, the popover, the modal |
| `--color-sand` | `#f3f1ec` | The sidebar, control fills, the add form, hovers |
| `--color-ink` | `#27251e` | Headings, names, links — and the one filled button |
| `--color-graphite` | `#72706b` | Body copy, table cells, nav labels |
| `--color-ash` | `#92918b` | Captions, placeholders, hosts |
| `--color-rule` | `#e7e4de` | Row dividers — the only lines at rest |
| `--color-teal` | `#016a71` | Active nav item, selected chips, the `done` dot, focus glow |
| `--color-rose-ink` | `#a8321f` | Errors, failed enrichment, Delete (an addition — the reference palette has no negative state) |

A border appears only as a focus state, and a shadow only on what floats (the columns popover and
the modal). Radii are a small closed set (4 / 6 / 8 / 12), with pills kept for the toggle chips.

Tokens are defined once in `:root` and consumed by every rule below, so restyling starts there.
`frontend/CLAUDE.md` carries the working rules for staying inside the system.

### Two layouts

Under 640px the five-column table does not fit — it overflowed the viewport and pushed the page
controls thousands of pixels below the fold. `App.tsx` therefore picks a layout with
`useMediaQuery("(max-width: 640px)")`:

| | Wide | Narrow |
|---|---|---|
| List | `BookmarksTable` | `BookmarksList` (one card per bookmark, description clamped to two lines) |
| Sort | click the `Name` column header | `SortControl`, a field+direction select |
| Pagination | `Pagination` in the list panel's footer | `Pagination compact` inside a sticky control bar above it |
| Type filter | `Sidebar` nav items — collapsible to an icon rail, and always a rail between 641px and 1024px | `TypeChips`, a sideways-scrolling row of pills in the sticky bar |

The `ColumnsControl` menu in the filters row hides the description, tags and type columns (and the
matching card fields). It is a view preference stored in `localStorage`, not a query parameter:
hidden values are still fetched and still shown in the detail modal.

The switch is made in JS rather than by rendering both and hiding one with CSS: two copies of every
bookmark would double the markup and make accessibility and test queries ambiguous. The trade-off
is that `window.matchMedia` must exist wherever `App` renders — `src/test/setup.ts` stubs it for
jsdom, defaulting to the wide layout.

Tests sit beside the file they cover, as `*.test.ts`/`*.test.tsx`; the heaviest are on `api.ts`
(the whole backend contract), the out-of-order guard below, and bulk add.

### The enrichment effect

A bookmark is created before anything is known about it: the backend stores a placeholder name
taken from the URL's host, then fetches the page and derives the real name in the background.
`BookmarkName` — used by the table and the card list alike — shows that wait instead of hiding it.

| | Pending | Done |
|---|---|---|
| Leading slot | 3x3 grid of dots, each pulsing on its own period | the page's favicon, or the host's initial on a tile |
| Text | the URL, under a grey gradient that sweeps across it | the real name, revealed one character per ~16ms while the rest keep cycling |

The reveal starts only when a row observes its own `pending → done` transition, so a page of
already-enriched bookmarks doesn't scramble on load. Under `prefers-reduced-motion` all three
animations are skipped and both states stay legible as plain grey text.

## Data flow

`App.tsx` owns all state. `refresh()` is a `useCallback` keyed on every parameter that affects the
query — tag filter, type filter, sort field, sort order, offset — and a `useEffect` re-runs it
whenever that identity changes.

The consequence: **filtering, sorting and pagination are all server-side.** Changing a filter
re-queries `GET /bookmarks`; it does not sort or filter the array already in memory. Changing any
of them also resets `offset` to 0, so you don't land on page 4 of a result set with two pages.

Mutations are not optimistic. Every create, update and delete is followed by `await refresh()`, so
the table always shows what the server actually stored.

### Out-of-order responses

Filter changes can fire several overlapping requests, and they can come back in any order. A
monotonic counter in a `useRef` guards against this: each request takes a sequence number on the
way out, and a response whose number is no longer the latest is dropped rather than rendered. Any
new request path needs the same guard, or a slow early response will clobber a newer list.

### Waiting for enrichment

A bookmark created from a bare URL arrives with no description, because the backend fills that in
asynchronously. When any row on screen is still missing one, the app polls the list every 5 seconds
until they all have one, then stops. The poll is silent — it does not touch the error banner, since
the next real `refresh()` will surface anything genuinely broken.

### Bulk add

The add form has a bulk mode that takes a newline-separated list of URLs. There is no bulk endpoint
on the backend: it fires one `POST /bookmarks` per URL and reports how many succeeded. Failures are
listed with their error message and left in the textarea, so a retry resubmits only what didn't
land — usually the duplicates the server rejected with a `409`.

The requests go through `mapSettledWithLimit` (`utils.ts`), a small worker pool that keeps at most
`BULK_CONCURRENCY` (5) POSTs in flight while preserving `Promise.allSettled`'s semantics. Each
create schedules a background enrichment task that fetches a page and calls an LLM against a single
SQLite file, so a pasted list of a few hundred URLs must not arrive as a few hundred simultaneous
requests.

## Talking to the API

`api.ts` centralizes error handling in `request<T>()`: a non-2xx response is unwrapped from
FastAPI's `{"detail": "..."}` shape and thrown as an `Error`, and a `204` resolves to `undefined`.
Handlers in `App.tsx` catch and set the error banner. New endpoints should go through `request<T>()`
rather than calling `fetch` directly.

The list endpoint is the one exception: it uses `requestRaw()` because it needs the response
headers. `GET /bookmarks` returns a plain array with the unpaginated total in `X-Total-Count`, and
`listBookmarks()` recombines the two into a `BookmarkPage` (`{ items, total }`) so the pagination
controls have a total to work from.

### Base URL

`VITE_API_URL`, read in `api.ts`, defaulting to `http://localhost:8000`. It is **compile-time, not
runtime**: in dev the Vite dev server picks it up as an env var at startup, and in prod it is a
Docker build ARG that Vite inlines into the static bundle. Pointing a production deployment at a
real host means rebuilding the image — not restarting the container or setting an env var on it.

## Keeping `types.ts` honest

`types.ts` has no automatic connection to the backend: no shared schema, no codegen. When
`backend/app/adapters/inbound/schemas.py` changes, `types.ts` has to be updated by hand, and
**nothing will catch the mismatch at build time.**

Two things it encodes deliberately:

- `BookmarkId` is an alias for `string`, not spelled inline, so IDs can't be confused with numbers.
  They are server-generated UUIDs and opaque here — never parse, sort, or generate one client-side.
- `BookmarkCreateInput` is separate from `BookmarkInput` because `POST` and `PUT` genuinely differ:
  creating only requires a `url`, while editing sends the full record.

One known gap: `GET /bookmarks` supports a `name` substring filter that this app never sends.
Adding a search box means extending `ListBookmarksParams`, threading it through `refresh()`, and
adding it to that callback's dependency list.
