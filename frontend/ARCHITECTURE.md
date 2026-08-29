# Frontend architecture

React 19 + TypeScript + Vite single-page app for the bookmarks manager. No state manager, no
data-fetching library, no component library, no CSS framework — the scope doesn't justify one, and
keeping it that way is a design decision rather than an unfinished migration.

For the system-level picture see the repo-root [`ARCHITECTURE.md`](../ARCHITECTURE.md).

## Commands

```bash
npm install
npm run dev        # vite --host 0.0.0.0, port 5173
npm run typecheck  # tsc --noEmit
npm run build      # tsc -b && vite build → dist/
npm run preview
```

There is no test runner and no linter here. `npm run typecheck` and `npm run build` are the full
check. `tsconfig.json` is strict and enables `noUnusedLocals`/`noUnusedParameters`, so a dead
variable breaks the build rather than just showing up in the editor.

## Structure

Four files under `src/`, and that is intended to stay small:

| File | Role |
|---|---|
| `App.tsx` | The entire UI as one component: table view, add form, bulk add, inline row editing, delete, filters, sorting, pagination. |
| `api.ts` | `fetch` wrappers, one per endpoint, plus shared error handling. |
| `types.ts` | Hand-written mirror of the backend's Pydantic schemas. |
| `index.css` | Plain CSS. Notion-style: quiet borders, generous whitespace. |

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
on the backend: it fires one `POST /bookmarks` per URL through `Promise.allSettled` and reports how
many succeeded. Failures are listed with their error message and left in the textarea, so a retry
resubmits only what didn't land — usually the duplicates the server rejected with a `409`.

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
