# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

React 19 + TypeScript + Vite frontend for the bookmarks manager. See the repo-root `CLAUDE.md` for
cross-cutting concerns (Docker, the API contract, stale design docs).

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

All five are what CI runs; run them before calling a change done.

Tests are Vitest + Testing Library. The config is the `test` block inside `vite.config.ts` — don't
add a separate `vitest.config.ts`. Test files sit next to what they cover (`src/api.test.ts`,
`src/components/AddBookmarkForm.test.tsx`, …) and `src/test/setup.ts` pulls in jest-dom's matchers.

`tsconfig.json` **excludes** the test files, because `npm run build` runs `tsc -b` first and would
otherwise fail on the test globals; `tsconfig.test.json` includes them, and `npm run typecheck`
runs both, so a type error in a test still fails CI. Adding a test file needs no config change;
moving to a new suffix does.

`tsconfig.json` is strict and includes `noUnusedLocals`/`noUnusedParameters`, so dead variables
break the build, not just the editor. `eslint-plugin-react-hooks` runs in its recommended
configuration; `App.tsx`'s two deliberate `setState`-in-effect calls carry an inline disable with
the reason, so keep the rule on rather than widening those exemptions.

## Structure

```
src/
├── App.tsx                          composition root: owns list state, filters, sort,
│                                     pagination, polling, and the selected-bookmark id
├── api.ts                           fetch wrappers. No data-fetching library.
├── types.ts                         hand-written mirror of the backend's Pydantic schemas.
├── utils.ts                         parseTags/parseBulkUrls/formatDate, BOOKMARK_TYPES, PAGE_SIZE
├── index.css                        plain CSS, no framework. The whole design system: tokens
│                                     in :root, then component rules. See "Design system" below.
├── useMediaQuery.ts                 useSyncExternalStore wrapper over window.matchMedia; drives
│                                     the wide/narrow layout switch
└── components/
    ├── AddBookmarkForm.tsx          add form incl. bulk-URL mode; owns its own form state,
    │                                calls createBookmark itself, reports back via onCreated/onError
    ├── FiltersBar.tsx               tag/type filter controls (controlled by App)
    ├── SortControl.tsx              narrow-viewport sort: one select carrying field + direction
    ├── BookmarksTable.tsx           read-only table (wide): name, description, tags, type, and
    │                                one eye-icon button per row that opens the detail modal
    ├── BookmarksList.tsx            read-only card list (narrow): the same data stacked, with
    │                                the whole card opening the detail modal
    ├── Pagination.tsx               prev/next + range display (controlled by App); `compact`
    │                                renders chevrons for the sticky mobile bar
    └── BookmarkDetailModal.tsx      per-bookmark modal: status badge + retry (when FAILED),
                                     url, date added, description, tags, type, and Edit/Delete —
                                     owns its own edit-draft/saving/deleting/retrying state
```

Don't reach for a state manager, data-fetching library, or component library; the scope doesn't
justify one. Keep components presentational where possible — `App.tsx` remains the only place
that talks to `listBookmarks`/holds the polling loop, so there's one source of truth for what's
on screen.

## Design system

`index.css` implements an "ink on cold-pressed paper" system (Audyr-style): white stock, near-black
ink, hairline rules, and shadows soft enough to read as paper grain rather than elevation. Tokens
live in `:root` — colours, the Inter type scale, a 4px spacing scale, radii and the three shadows —
and every rule below consumes them, so a restyle starts there rather than in a component.

Four rules define the look:

- **No brand accent.** There is no primary colour. Hierarchy comes from type weight and four steps
  of grey: `--color-ink` for headings, links and emphasis; `--color-ash` for body copy and table
  cells; `--color-muted` for captions and metadata; `--color-fog` for placeholders. Adding a
  brand hue is the one change that would break the system outright.
- **One fill.** `--color-ink` (#262626) is the only filled button background — the Add action's
  `.button-primary`. Every other button is the ghost outline default. That single dark rectangle
  is the page's only visual anchor.
- **Hairlines carry structure.** `--color-soft-mist` (#ededed) at 1px is every border, divider,
  input outline and table rule. Cards are white-on-white, separated only by that hairline, a 14px
  radius and `--shadow-card`.
- **One tracking value.** `--tracking` (-0.025em) is set once on `body` and inherited everywhere,
  so a 12px label and a 30px heading share the same optical compression. Do not override it per
  component — that uniformity is what makes the system feel cohesive rather than merely consistent.

Radii are a closed set: 4px inputs and buttons, 8px images, 14px cards, 18px large panels, pill
badges. No intermediate values — a 6px or 12px radius reads as a different system.

Shadows are likewise closed: `--shadow-card` on cards, `--shadow-button` (an inset highlight plus a
1px drop) on the filled button only, and `--shadow-panel` on the modal. Nothing heavier.

Two additions to the reference palette were unavoidable. `--color-rose-whisper`/`--color-rose-ink`
carry destructive and error states (error banner, failed enrichment, bulk-add failures), built as
the mint badge's mirror image so they stay inside the badge vocabulary. And the 48px display size
is unused: this is a tool, not a landing page, so `h1` takes `--text-heading-lg` (30px) and drops
to 24px under 640px.

Inter is loaded from Google Fonts in `index.html` with `cv11`/`ss01` enabled globally via
`font-feature-settings` on `body`. The stack falls back to the system sans, which matters for a
self-hosted LAN install with no outbound network.

## Two layouts

Under 640px the table's five columns overflow the viewport and the pagination ends up thousands of
pixels below the fold, so `App.tsx` swaps layouts on `useMediaQuery("(max-width: 640px)")`:
`BookmarksList` cards instead of `BookmarksTable`, a `SortControl` select instead of the clickable
`Name` header, and the filters + sort + a `compact` `Pagination` together in a sticky bar above the
list.

Both layouts are never in the DOM at once — the choice is made in JS, not by rendering both and
hiding one with CSS, so there is exactly one copy of each bookmark for accessibility and test
queries to find. The cost is that `window.matchMedia` must exist wherever `App` renders;
`src/test/setup.ts` stubs it for jsdom and defaults to the wide layout, so a test that wants cards
stubs `window.matchMedia` itself (see the `narrow-viewport layout` block in `App.test.tsx`).

`BookmarksList`'s cards use a stretched transparent button (`.bookmark-card-open`) covering the
card, with `pointer-events: none` on the content and the name link opting back in — so a tap
anywhere opens the modal while the name still opens the URL, without nesting a link inside a
button. Changing pages scrolls back to the top (`goToOffset` in `App.tsx`); with sticky controls
you would otherwise stay stranded mid-list on a page that silently changed under you. That scroll
is instant, not smooth: a smooth scroll races the re-render that shortens the page under it.

## The detail modal

Clicking a row's eye button sets `App`'s `selectedId`; the modal itself is rendered as
`bookmarks.find(b => b.id === selectedId)`, not a copy fetched separately. That means the same
5s enrichment poll that refreshes the table also keeps an open modal's status badge current (e.g.
`pending` flipping to `done`), and a bookmark deleted through another path (or no longer matching
the active filters after a refresh) makes the modal disappear on its own rather than showing stale
data — there is no separate "close on delete" special case to maintain beyond clearing `selectedId`
in `onDeleted`.

Editing, deleting, and retrying enrichment all live inside `BookmarkDetailModal` and call
`api.ts` directly, then invoke a callback prop (`onUpdated`/`onDeleted`/`onRetried`) that's just
`App`'s `refresh`. There's no optimistic local update — same pattern as the rest of the app.

Retry only renders when `enrichment_status === "failed"` and calls
`POST /bookmarks/{id}/retry-enrichment` (`api.ts::retryEnrichment`); the backend resets the status
to `pending` and reschedules the background task, so the poll above picks it up the same way a
freshly-created bookmark's enrichment does — see `backend/CLAUDE.md`.

Name, url, description, tags and type are no longer editable inline in the table — that inline-row
editing was removed when Edit moved into the modal. The table also no longer renders a "date
added" column; that value only appears in the modal now, alongside the enrichment status.

## How data flows

`App.tsx` owns all list state. `refresh()` is a `useCallback` keyed on `filterTag`, `filterType`,
`sortBy`, `sortOrder` and `offset`, and a `useEffect` calls it whenever that identity changes — so
**filtering, sorting and pagination are all server-side**: changing any of them re-queries
`GET /bookmarks`, it does not reorder or slice the loaded array. **Anything new that affects the
query must go in that dependency list**, or `refresh()` keeps its old identity, the effect never
re-runs, and the control renders as changed while the table still shows the previous query. A separate
`useEffect` resets `offset` to 0 whenever a filter or sort changes.

Every mutation (`create`/`update`/`delete`) is followed by `await refresh()` rather than optimistic
local updates.

Three behaviors are easy to break by accident:

- **Out-of-order responses are guarded by a monotonic `requestSeq` ref.** Each request takes a
  sequence number on the way out; a response whose number is stale is dropped instead of rendered,
  including in the `catch` and `finally` branches (a stale failure must not clear a fresh
  `loading`). Any new request path that writes to `bookmarks`/`total` needs the same guard.
- **Enrichment is polled, not pushed.** `hasPendingEnrichment` is
  `bookmarks.some(b => b.enrichment_status === "pending")`; while true, a 5s `setInterval`
  re-fetches the current page and the effect tears it down once no row is still pending. Backend
  enrichment retries transient failures itself (see `backend/CLAUDE.md`); once it gives up, the
  bookmark's `enrichment_status` becomes `"failed"`, which this predicate treats as finished, not
  pending — so a permanent failure stops the poll instead of running it forever. That poll
  deliberately swallows its errors — it must not clobber the error banner with a transient failure
  the user didn't cause.
- **Bulk add loops `POST /bookmarks` client-side.** There is no bulk endpoint and shouldn't be one.
  The parsed URLs go through `mapSettledWithLimit` (`utils.ts`), a worker pool capped at
  `BULK_CONCURRENCY` (5) with `Promise.allSettled`'s semantics — every create schedules a
  background LLM call against one SQLite file, so an unbounded fan-out is a real hazard, not a
  hypothetical one. The failures (usually `409` duplicates) are then listed with their messages and
  written back into the textarea so a resubmit retries only those.

`api.ts` centralizes error handling in `request<T>()`: non-2xx responses are unwrapped from
FastAPI's `{"detail": "..."}` shape and thrown as an `Error`; 204 returns `undefined`. Handlers in
`App.tsx` catch and set the `error` banner. New endpoints should go through `request<T>()` rather
than calling `fetch` directly.

`listBookmarks()` is the one exception: it uses `requestRaw()` because it needs the response
headers. `GET /bookmarks` returns a bare array plus the unpaginated total in `X-Total-Count`, and
`listBookmarks()` recombines them into a `BookmarkPage` (`{ items, total }`), falling back to
`items.length` when the header is absent. Keep that assembly in `api.ts` — `App.tsx` should never
see the header.

## API base URL

`VITE_API_URL`, read in `api.ts`, is **compile-time, not runtime** when set: in dev the Vite dev
server picks it up as an env var at startup (set on the frontend service in `docker-compose.yml`),
and in prod it's a Docker build ARG that Vite inlines into the static bundle. Pointing prod at a
real host by setting it means rebuilding the image, not restarting the container or setting an env
var on it.

In prod (`docker-compose.prod.yml`), `VITE_API_URL` is left **unset by default**, and `api.ts`
falls back to deriving the backend URL from the browser's own `window.location.hostname` at
runtime, on port 8000. This is what makes the single-host Tailscale deployment work without baking
in a specific Tailscale hostname/IP at build time — the frontend and backend are assumed to be
reachable on the same host, so whatever address the browser used to load the page also reaches the
backend on `:8000`. That assumption breaks for a reverse-proxied or multi-host deployment, which is
exactly when you'd set `VITE_API_URL` explicitly to override the runtime fallback.

## Keeping types.ts honest

`types.ts` has no automatic connection to the backend. When `backend/app/adapters/inbound/
schemas.py` changes, update `types.ts` by hand — nothing will catch the mismatch.

IDs are server-generated UUIDs, aliased as `BookmarkId` (a `string`) rather than spelled inline,
so the client can't accidentally treat them as numbers or arithmetic. Use that alias for anything
holding an id. They're opaque here — never parse, sort, or generate one client-side.

One known gap: `GET /bookmarks` supports a `name` substring filter that this app never sends.
`ListBookmarksParams` covers `tag`, `type`, `sortBy`, `sortOrder`, `limit` and `offset` but not
`name`. Adding a search box means extending that interface, threading it through `refresh()`, and
adding it to the `useCallback` dependency list.
