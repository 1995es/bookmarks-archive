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
| `components/` | `AddBookmarkForm`, `FiltersBar`, `SortControl`, `BookmarksTable`, `BookmarksList`, `Pagination`, `BookmarkDetailModal`, `ErrorBanner`. |
| `useMediaQuery.ts` | Subscribes to a CSS media query; drives the table/card layout switch below. |
| `api.ts` | `fetch` wrappers, one per endpoint, plus shared error handling. |
| `types.ts` | Hand-written mirror of the backend's Pydantic schemas. |
| `utils.ts` | Input parsing (`parseTags`, `parseBulkUrls`), `formatDate`, and the bulk-add worker pool. |
| `index.css` | Plain CSS, no framework. Design tokens in `:root` plus every component rule — see [Design system](#design-system). |

### Design system

The interface follows an "ink on cold-pressed paper" language: a white canvas, near-black ink,
1px hairline rules in a single light grey, and shadows soft enough to read as paper grain. Type is
a single family (Inter) at three weights, tracked -0.025em at every size.

The defining choice is the **absence of a brand colour** — hierarchy is carried by type weight and
four steps of grey:

| Token | Value | Where it is used |
|---|---|---|
| `--color-pure-paper` | `#ffffff` | Page and card surfaces alike |
| `--color-ink` | `#262626` | Headings, links, emphasis — and the one filled button |
| `--color-ash` | `#686868` | Body copy, table cells |
| `--color-muted` | `#737373` | Captions, metadata, pagination status |
| `--color-fog` | `#929292` | Placeholders, disabled labels |
| `--color-soft-mist` | `#ededed` | Every border, divider, input outline and table rule |
| `--color-mint-whisper` | `#ecfdf5` | The `done` status badge only |
| `--color-rose-whisper` | `#fef2f2` | Errors and failed enrichment (an addition — the reference palette has no negative state) |

Cards are white on a white page, distinguished only by a 1px hairline, a 14px radius and a 1px
shadow. Radii are a closed set (4 / 8 / 14 / 18 / pill), as are the three shadows; values outside
those sets read as a different system.

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
| Pagination | `Pagination` below the list | `Pagination compact` inside a sticky control bar above it |

The switch is made in JS rather than by rendering both and hiding one with CSS: two copies of every
bookmark would double the markup and make accessibility and test queries ambiguous. The trade-off
is that `window.matchMedia` must exist wherever `App` renders — `src/test/setup.ts` stubs it for
jsdom, defaulting to the wide layout.

Tests sit beside the file they cover, as `*.test.ts`/`*.test.tsx`; the heaviest are on `api.ts`
(the whole backend contract), the out-of-order guard below, and bulk add.

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
