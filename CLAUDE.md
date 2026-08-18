# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Two sub-projects have their own guidance — read the relevant one before changing code there:
`backend/CLAUDE.md` and `frontend/CLAUDE.md`.

## What this is

A self-hosted bookmarks manager: FastAPI + SQLite backend, React + Vite + TypeScript frontend,
Docker Compose for dev and prod. Single `bookmarks` table, soft deletes, no auth.

`POST /bookmarks` schedules asynchronous enrichment (a FastAPI `BackgroundTask`) that fetches the
bookmark's URL and derives a description/tags for it via an LLM, appending them to whatever the
user provided. This runs after the response is returned, so the created bookmark is enriched a few
seconds later, not immediately. The LLM call goes through litellm to Gemini and needs
`GEMINI_API_KEY` set in the backend's environment in prod (`docker-compose.prod.yml` requires it);
see `backend/CLAUDE.md` for the ports/adapters involved.

## Running both services

```bash
docker compose up --build                          # dev: hot reload, :8000 + :5173
docker compose -f docker-compose.prod.yml up --build # prod: nginx static build, :8000 + :80
```

There is no database container — SQLite is a file the backend process opens directly, persisted in
the named volume `bookmarks_data` mounted at `/data`. Dev and prod share that volume name by
default, and the prod image runs as non-root while the dev image runs as root — switching modes
against the same volume produces "readonly database" errors. Run `docker compose down -v` between
modes, or use distinct project names (`docker compose -p ...`).

The dev frontend service declares an anonymous volume over `/app/node_modules` on purpose, so the
bind-mounted host `./frontend` doesn't shadow the install `npm ci` did inside the image. Don't
remove it while "cleaning up" the compose file.

Both services also run without Docker; see the per-directory CLAUDE.md files.

## The frontend/backend contract

There is no shared schema or codegen. `frontend/src/types.ts` is a hand-maintained mirror of
`backend/app/adapters/inbound/schemas.py`. **Any change to the Pydantic schemas must be mirrored
there by hand** — nothing will fail at build time if you forget.

One gap remains: `GET /bookmarks` accepts a `name` substring filter that the frontend never sends.

## Docs

`README.md` is the user-facing doc and is current as of the UUID/`json_each`/layered-tests state
of the code. An earlier `project.md` design doc described a pre-hexagonal layout and has been
folded into `README.md` and these files; don't recreate it.

When docs conflict with the code, the code wins — but prefer updating the doc over leaving new
drift behind, since nothing here is generated.
