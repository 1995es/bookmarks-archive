# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`ARCHITECTURE.md` is the high-level map of how the system fits together, linking to
`backend/ARCHITECTURE.md` and `frontend/ARCHITECTURE.md`. Two sub-projects also have their own
agent guidance — read the relevant one before changing code there: `backend/CLAUDE.md` and
`frontend/CLAUDE.md`.

## What this is

A self-hosted bookmarks manager: FastAPI + SQLite backend, React + Vite + TypeScript frontend,
Docker Compose for dev and prod. Single `bookmarks` table, soft deletes, no auth.

`POST /bookmarks` schedules asynchronous enrichment (a FastAPI `BackgroundTask`) that fetches the
bookmark's URL and derives a description/tags for it via an LLM, appending them to whatever the
user provided. This runs after the response is returned, so the created bookmark is enriched a few
seconds later, not immediately. The LLM call goes through litellm to whatever model `LLM_MODEL`
names (default: Gemini); the backend validates at startup that the env var matching that model's
provider (e.g. `GEMINI_API_KEY`, `OPENAI_API_KEY`) is set, and refuses to boot otherwise — see
`backend/CLAUDE.md` for the ports/adapters involved.

## Running both services

```bash
docker compose up --build                          # dev: hot reload, :8000 + :5173
docker compose -f docker-compose.prod.yml up --build # prod: nginx static build, :8000 + :80
```

There is no database container — SQLite is a file the backend process opens directly. Dev bind-mounts
the host directory `./data` at `/data`, so `./data/bookmarks.db` is a real file you can query with a
local `sqlite3` or a GUI tool while the stack is running. Prod bind-mounts a fixed host path
(`/srv/bookmarks/data` by default, overridable with `BOOKMARKS_DATA_DIR`) at `/data`, so the
database file sits at a stable, predictable location a backup job can target. The prod image runs
as non-root, so that host directory must be owned by uid:gid `999:999` or the backend gets
"readonly database" errors. The two modes still point at different paths, so switching between
them can't make them fight over one file.

The dev frontend service declares an anonymous volume over `/app/node_modules` on purpose, so the
bind-mounted host `./frontend` doesn't shadow the install `npm ci` did inside the image. Don't
remove it while "cleaning up" the compose file.

Both services also run without Docker; see the per-directory CLAUDE.md files.

## The frontend/backend contract

There is no shared schema or codegen. `frontend/src/types.ts` is a hand-maintained mirror of
`backend/app/adapters/inbound/schemas.py`. **Any change to the Pydantic schemas must be mirrored
there by hand** — nothing will fail at build time if you forget.

`GET /bookmarks` is the one route whose contract isn't fully in the body: it returns a bare array
and puts the unpaginated total in an `X-Total-Count` header, which `api.ts` reassembles into a
`BookmarkPage`. A new list filter has to land in `repo.list()`, `repo.count()`, the route, and the
frontend's `ListBookmarksParams`.

One gap remains: `GET /bookmarks` accepts a `name` substring filter that the frontend never sends.

## Docs

`README.md` is the user-facing doc: what the project does and how to run it. It deliberately does
*not* document the API surface, data model, or layer-by-layer architecture — that lives in
`ARCHITECTURE.md`, which stays high-level and links out to `backend/ARCHITECTURE.md` and
`frontend/ARCHITECTURE.md` for detail. Don't grow the README back into a reference doc.

The `ARCHITECTURE.md` files are for humans reading the project; the `CLAUDE.md` files are agent
instructions. Never link a reader-facing doc at a `CLAUDE.md`. They overlap in subject matter, so
a change to how the code is structured usually needs both updated.

An earlier `project.md` design doc described a pre-hexagonal layout and has been folded into these
files; don't recreate it.

When docs conflict with the code, the code wins — but prefer updating the doc over leaving new
drift behind, since nothing here is generated.
