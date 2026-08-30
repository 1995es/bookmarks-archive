# Architecture

A high-level map of how Bookmarks Archive is put together. Details that only matter when you're
editing a given layer live next to that layer's code — this file links out to them rather than
repeating them.

- Backend internals — layers, ports, API surface, data model, enrichment, testing:
  [`backend/ARCHITECTURE.md`](backend/ARCHITECTURE.md)
- Frontend internals — structure, data flow, API client, the type contract:
  [`frontend/ARCHITECTURE.md`](frontend/ARCHITECTURE.md)

## The shape of the system

```
┌──────────────┐        HTTP/JSON        ┌──────────────┐
│  React SPA   │ ──────────────────────► │   FastAPI    │
│ (Vite build) │ ◄────────────────────── │   backend    │
└──────────────┘                         └──────┬───────┘
                                                │
                                 ┌──────────────┴───────────────┐
                                 │                              │
                          SQLAlchemy async              BackgroundTask
                                 │                              │
                          ┌──────▼──────┐             ┌─────────▼─────────┐
                          │   SQLite    │             │ fetch URL (httpx) │
                          │ /data/*.db  │             │  → LLM (litellm)  │
                          └─────────────┘             └───────────────────┘
```

Three moving parts and no more: a single-page frontend, one backend process, and a SQLite file.
There is no database server, no queue, no cache, and no auth — this is a single-user, self-hosted
app, and every design decision below leans on that.

## Request flow

Reads and writes are ordinary synchronous request/response. The one asynchronous path is creation:

1. `POST /bookmarks` validates the payload, stores the bookmark, and returns `201` immediately —
   with whatever name/description/tags the user typed (a URL-only submission gets a placeholder
   name derived from the URL's host).
2. A FastAPI `BackgroundTask` then runs *after* the response is sent: it fetches the URL over
   `httpx`, asks an LLM (via litellm, model chosen by `LLM_MODEL`) to derive a description and
   tags, and merges the result into the stored bookmark.
3. The frontend sees the enrichment on its next refresh, a few seconds later.

Because that task runs after the request's DB session has closed, it opens its own session. Any
failure in it is swallowed and logged — a bookmark that can't be enriched simply stays as the user
typed it. There is no push channel back to the browser: while any row on screen is still missing a
description, the frontend polls the list every few seconds and stops once they all have one. See
[`backend/ARCHITECTURE.md`](backend/ARCHITECTURE.md#background-enrichment) for the merge rules and
the concurrency tradeoff this accepts.

## Backend: ports and adapters

The backend is a hexagonal (ports and adapters) layout. Dependencies point inward —
`adapters` → `application` → `domain` — and `domain` imports no framework at all:

```
backend/app/
├── domain/         business objects and the interfaces the outside world must satisfy
├── application/    use cases: list/get/create/update/delete, enrich
├── adapters/
│   ├── inbound/    FastAPI routes, Pydantic DTOs, the background-task edge
│   └── outbound/   SQLAlchemy repository, HTTP content fetcher, LLM enricher
└── main.py         composition root — builds the app and wires the adapters in
```

Three ports are declared as abstract base classes in `domain/ports.py`: `BookmarkRepository`,
`ContentFetcher`, and `BookmarkEnricherService`. Everything the app does to the outside world goes through one of them,
which is what makes the interesting parts testable without a database, a network, or an API key.

The domain `Bookmark` (a plain dataclass) and the persisted `BookmarkRow` (a SQLAlchemy model) are
deliberately separate types, mapped on every read and write. Swapping the database, or exercising
the business logic without one, only touches the outbound adapter.

For the rules that keep this working — where validation lives, how soft deletes and URL uniqueness
are enforced as part of the port contract, how the layers are tested — see
[`backend/ARCHITECTURE.md`](backend/ARCHITECTURE.md).

## Frontend: one component, server-side filtering

A single-page app with four files under `src/`: the UI (`App.tsx`), `fetch` wrappers (`api.ts`),
hand-written types mirroring the backend schemas (`types.ts`), and plain CSS. No state manager, no
data-fetching library, no component library — the scope doesn't justify one.

`App.tsx` owns all state. Filtering, sorting and pagination are all **server-side**: changing any
of them re-queries `GET /bookmarks` rather than reordering the array in memory. Every mutation is
followed by a refetch rather than an optimistic local update. Bulk add is a client-side loop over
`POST /bookmarks` — there is no bulk endpoint. Details in
[`frontend/ARCHITECTURE.md`](frontend/ARCHITECTURE.md).

## The frontend/backend contract

There is no shared schema and no codegen. `frontend/src/types.ts` is a hand-maintained mirror of
`backend/app/adapters/inbound/schemas.py`, and **nothing fails at build time if the two drift.**
Any change to the Pydantic schemas has to be mirrored by hand.

The API itself is five routes over one resource — list (filtered, sorted and paginated, with the
unpaginated total in an `X-Total-Count` header), get, create, replace, and soft-delete. Errors use
FastAPI's default `{"detail": "..."}` shape; CORS is wildcard-open because this isn't
public-facing. The full parameter tables are in
[`backend/ARCHITECTURE.md`](backend/ARCHITECTURE.md#http-api).

## Storage

One table, `bookmarks`, with a UUIDv7 primary key, a JSON array column for `tags`, an enum `type`
(`post`, `video`, `tweet`, `site`), and a nullable `deleted_at` that is never exposed over the API.

Two consequences of that shape are worth knowing up front:

- **Deletes are soft.** Repositories are contractually required to hide soft-deleted bookmarks
  from both `list()` and `get()`. URL uniqueness is therefore enforced by a SQLite *partial* unique
  index over live rows only, so deleting a bookmark frees its URL again.
- **Tag filtering is an exact match**, expanded with SQLite's `json_each` rather than a `LIKE` over
  the JSON text — otherwise filtering by `py` would match `python`. `name`, by contrast, is a
  case-insensitive substring match, since it backs a search box.

There is no migrations tool: `create_all()` at startup creates missing tables and nothing else — it
will not alter an existing table or add an index to one. A hand-rolled step after it adds columns
the ORM has gained since a database was created; every other schema change still means deleting the
database file or volume. See `backend/ARCHITECTURE.md` for what that covers.

## Deployment topology

Dev and prod are two Compose files over the same two services.

| | Dev (`docker-compose.yml`) | Prod (`docker-compose.prod.yml`) |
|---|---|---|
| Backend | uvicorn `--reload`, source bind-mounted, root | uvicorn, no mounts, non-root |
| Frontend | Vite dev server on `:5173` | static build served by nginx on `:80` |
| Data | named volume `bookmarks_data` at `/data` | same volume name |

Since SQLite is a file rather than a service, persistence is entirely that named volume. The two
modes sharing a volume name is a known sharp edge — see the README for how to avoid the
"readonly database" it can cause.

`VITE_API_URL` is **compile-time**, not runtime: in prod it's baked into the static bundle via a
build ARG, so pointing a deployment at a real host means rebuilding the frontend image.

## Where the limits are

- SQLite serializes writes at the file level. Fine for one backend process; it would not survive
  multiple replicas writing concurrently.
- A `PUT` racing the enrichment background task can overwrite it (or be overwritten). Accepted
  as-is for a single-user local app.
- Wildcard CORS and no auth. Tighten both before exposing this beyond localhost.
- Two SQLite-specific couplings — `json_each` and the partial unique index — would need rewriting
  to move to another database.
