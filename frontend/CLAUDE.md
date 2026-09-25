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
├── useColumnVisibility.ts           which of description/tags/type are shown, persisted to
│                                     localStorage; also owns the column list and its labels
├── useScrambleText.ts               arrival-board reveal: resolves a string left to right while
│                                     the tail keeps shuffling. See "The enrichment effect"
└── components/
    ├── AddBookmarkForm.tsx          add form incl. bulk-URL mode; owns its own form state,
    │                                calls createBookmark itself, reports back via onCreated/onError
    ├── FiltersBar.tsx               tag/type filter controls (controlled by App), plus a
    │                                trailing `children` slot the columns menu rides in
    ├── ColumnsControl.tsx           popover of checkboxes toggling the description/tags/type
    │                                columns; owns only its own open/closed state
    ├── SortControl.tsx              narrow-viewport sort: one select carrying field + direction
    ├── BookmarkFavicon.tsx          the favicon, falling back to the host's initial on a tile —
    │                                the only place that knows that chain; used by all three surfaces
    ├── BookmarkName.tsx             the name cell shared by both layouts: pending indicator,
    │                                shimmering URL, and the scramble on pending → done
    ├── BookmarksTable.tsx           read-only table (wide): name, description, tags, type; the
    │                                whole row opens the detail modal (click, or Enter/Space)
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
button.

The table reaches the same behavior differently: a `<tr>` is no place for an absolutely positioned
overlay, so `BookmarksTable` puts the handlers on the row itself. Three things there are load-bearing:

- **`tabIndex={0}` plus an Enter/Space `onKeyDown` is the whole keyboard story.** The table used to
  carry a per-row eye button, and that button was what made the modal reachable without a mouse;
  when it was removed, the row had to take that over. A click handler alone would leave the modal
  mouse-only. `:focus-visible` on the row draws the focus ring, inset so a full-width outline isn't
  clipped at the viewport edge.
- **The key handler only fires when the row itself has focus** (`e.target !== e.currentTarget`
  bails). Enter on the focused name link belongs to the link, and its keydown bubbles through here.
- **A click that ends a text selection is ignored** (`window.getSelection()`), or copying a
  description out of a row would always pop the modal open over it.

In both layouts the name link stops propagation, so the one thing inside the click target that
isn't "open the modal" is the bookmark's own link. Changing pages scrolls back to the top (`goToOffset` in `App.tsx`); with sticky controls
you would otherwise stay stranded mid-list on a page that silently changed under you. That scroll
is instant, not smooth: a smooth scroll races the re-render that shortens the page under it.

## The enrichment effect

A freshly added bookmark is useless for a few seconds: the backend stores a placeholder name
derived from the URL's host and fetches the real one in the background. `BookmarkName` (used by
both `BookmarksTable` and `BookmarksList`, so the two layouts tell the same story) renders that
wait rather than hiding it:

- **Pending.** The URL itself is shown, not the host placeholder — the placeholder says nothing
  the URL doesn't. It carries `.text-shimmer`, a grey gradient clipped to the glyphs, beside a 3x3
  grid of pulsing dots. The dots sit in a fixed-width slot that stays reserved once the bookmark
  resolves, so nothing shifts sideways — the favicon takes their place there.
- **Done.** The real name arrives and is revealed with `useScrambleText`: one character per ~16ms
  resolves from the left while the rest keep cycling through random characters. Spaces are never
  scrambled, which is what keeps a half-resolved title reading as a title.

The favicon is `bookmark.favicon_url`, discovered by the backend during that same enrichment (see
`backend/CLAUDE.md`) — never a third-party icon service, which would hand your whole bookmark list
to someone else and break on a LAN box with no outbound route. A stored icon URL can rot, so
`onError` falls back to the host's initial on a tile. `BookmarkFavicon` tracks that failure *per
icon URL* rather than as a bare boolean, so a bookmark whose icon changes gets a fresh attempt
without callers having to remember a `key`. It's loaded with `referrerPolicy="no-referrer"`, since
the browser fetches it from the bookmarked site directly.

`BookmarkFavicon` is deliberately its own component rather than part of `BookmarkName`: the detail
modal shows the icon beside its heading too (at `bookmark-favicon-lg`, 24px), and that fallback
chain should exist once. The modal drops it while editing, where the heading is the action ("Edit
bookmark") rather than the bookmark itself. Unlike the list rows, the modal shows no pending dots —
it already reports enrichment state explicitly in its Status row.

Three things about it are easy to break:

- **The animation is gated on a transition, not on a status.** `BookmarkName` keeps the previous
  `enrichment_status` in state and starts the scramble only when *it* observes `pending → done`.
  Gating on `status === "done"` instead would scramble every row on every page load.
- **It respects `prefers-reduced-motion`.** The scramble is gated in JS on the media query, and
  the shimmer and pulse are disabled in CSS under the same one; both states stay legible as plain
  grey text. Note this makes every media query match in the narrow-layout tests, which stub
  `matchMedia` wholesale — that's why those tests never see a scramble.
- **The reveal is derived from elapsed time, not from a tick count.** Browsers clamp timers to
  ~1s in a hidden tab; counting ticks leaves a half-scrambled title sitting there for a minute
  after the reader switches back.

`App.tsx` only swaps the list for "Loading…" when there is nothing to show yet
(`loading && bookmarks.length === 0`). A refresh with rows already on screen — every poll, and
every create — keeps them rendered, because unmounting the list would both discard the transition
`BookmarkName` is watching for and make the new bookmark vanish and reappear.

## Column visibility

`useColumnVisibility` (`src/useColumnVisibility.ts`) holds which of `description`, `tags` and
`type` are rendered, and writes the object to `localStorage` under
`bookmarks-archive:visible-columns` on every change. It is a **display preference, not a query
parameter**: hidden columns are still fetched and still shown in the detail modal, so it stays out
of `refresh()`'s dependency list (see "How data flows"). The same flags drive `BookmarksTable`'s
columns and `BookmarksList`'s card fields, so a choice made on the desktop carries to the phone.

Anything stored can be absent, stale or hand-edited, so `readStored()` validates each key on its
own and falls back to visible — a malformed value must never blank the table — and both the read
and the write are wrapped in `try`/`catch` for browsers where storage throws outright (private
mode, storage disabled). Adding a toggleable column means extending `TOGGLEABLE_COLUMNS` plus
`COLUMN_LABELS`/`DEFAULT_COLUMN_VISIBILITY`, then the two list components; the menu and the stored
shape follow from the constant.

The jsdom build the tests run against ships no `Storage` at all, so `src/test/setup.ts` installs an
in-memory stand-in alongside its `matchMedia` and `scrollTo` stubs. A test that asserts on
persistence clears it in its own `beforeEach`.

## The detail modal

Clicking a row sets `App`'s `selectedId`; the modal itself is rendered as
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
