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

Four files under `src/`, and that's intended to stay small:

- `App.tsx` — the entire UI as one component: table view, inline add form, inline row editing,
  delete with `window.confirm`, and tag/type filters.
- `api.ts` — `fetch` wrappers. No data-fetching library.
- `types.ts` — hand-written mirror of the backend's Pydantic schemas.
- `index.css` — plain CSS, no framework. Notion-style: quiet borders, generous whitespace.

Don't reach for a state manager, data-fetching library, or component library; the scope doesn't
justify one.

## How data flows

`App.tsx` owns all state. `refresh()` is a `useCallback` keyed on `filterTag` and `filterType`, and
a `useEffect` calls it whenever that identity changes — so **filtering is server-side**: changing a
filter re-queries `GET /bookmarks?tag=&type=`, it does not filter the loaded array. Every mutation
(`create`/`update`/`delete`) is followed by `await refresh()` rather than optimistic local updates.

`api.ts` centralizes error handling in `request<T>()`: non-2xx responses are unwrapped from
FastAPI's `{"detail": "..."}` shape and thrown as an `Error`; 204 returns `undefined`. Handlers in
`App.tsx` catch and set the `error` banner. New endpoints should go through `request<T>()` rather
than calling `fetch` directly.

## API base URL

`VITE_API_URL`, read in `api.ts`, defaulting to `http://localhost:8000`. It is **compile-time, not
runtime**: in dev the Vite dev server picks it up as an env var at startup (set on the frontend
service in `docker-compose.yml`), and in prod it's a Docker build ARG that Vite inlines into the
static bundle. Pointing prod at a real host means rebuilding the image, not restarting the
container or setting an env var on it.

## Keeping types.ts honest

`types.ts` has no automatic connection to the backend. When `backend/app/adapters/inbound/
schemas.py` changes, update `types.ts` by hand — nothing will catch the mismatch.

IDs are server-generated UUIDs, aliased as `BookmarkId` (a `string`) rather than spelled inline,
so the client can't accidentally treat them as numbers or arithmetic. Use that alias for anything
holding an id. They're opaque here — never parse, sort, or generate one client-side.

One known gap: `GET /bookmarks` supports a `name` substring filter that this app never sends.
Adding a search box means extending `ListBookmarksParams` and the `refresh()` dependency list.
