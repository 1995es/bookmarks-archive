# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

React 19 + TypeScript + Vite frontend for the bookmarks manager. See the repo-root `CLAUDE.md` for
cross-cutting concerns (Docker, the API contract, stale design docs).

## Commands

```bash
npm install
npm run dev        # vite --host 0.0.0.0, port 5173
npm run typecheck  # tsc --noEmit — the only "test" here; there is no test runner
npm run build      # tsc -b && vite build → dist/
npm run preview
```

There are no tests and no linter. `npm run typecheck` and `npm run build` are the full check.
`tsconfig.json` is strict and includes `noUnusedLocals`/`noUnusedParameters`, so dead variables
break the build, not just the editor.

## Structure

```
src/
├── App.tsx                          composition root: owns list state, filters, sort,
│                                     pagination, polling, and the selected-bookmark id
├── api.ts                           fetch wrappers. No data-fetching library.
├── types.ts                         hand-written mirror of the backend's Pydantic schemas.
├── utils.ts                         parseTags/parseBulkUrls/formatDate, BOOKMARK_TYPES, PAGE_SIZE
├── index.css                        plain CSS, no framework. Notion-style: quiet borders,
│                                     generous whitespace.
└── components/
    ├── AddBookmarkForm.tsx          add form incl. bulk-URL mode; owns its own form state,
    │                                calls createBookmark itself, reports back via onCreated/onError
    ├── FiltersBar.tsx               tag/type filter controls (controlled by App)
    ├── BookmarksTable.tsx           read-only table: name, description, tags, type, and one
    │                                eye-icon button per row that opens the detail modal
    ├── Pagination.tsx               prev/next + range display (controlled by App)
    └── BookmarkDetailModal.tsx      per-bookmark modal: status badge + retry (when FAILED),
                                     url, date added, description, tags, type, and Edit/Delete —
                                     owns its own edit-draft/saving/deleting/retrying state
```

Don't reach for a state manager, data-fetching library, or component library; the scope doesn't
justify one. Keep components presentational where possible — `App.tsx` remains the only place
that talks to `listBookmarks`/holds the polling loop, so there's one source of truth for what's
on screen.

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
  `Promise.allSettled` over the parsed URLs, then the failures (usually `409` duplicates) are
  listed with their messages and written back into the textarea so a resubmit retries only those.

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
