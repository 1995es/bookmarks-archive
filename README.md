# Bookmarks Archive

A small self-hosted bookmarks manager: list, add, edit, delete, and filter bookmarks by tag or
type. FastAPI backend, React + Vite + TypeScript frontend, SQLite storage, Docker Compose for
both dev and prod.

After you add a bookmark it shows up immediately with whatever you typed. The backend then kicks
off a background task that fetches the URL and asks Gemini (via litellm) to summarize it, appending
the result to your description and merging in any suggested tags you didn't already have — see
`backend/app/adapters/outbound/llm_bookmark_enricher.py`.

**Before running the project**, copy `.env.example` to `.env` in the repo root and fill in
`GEMINI_API_KEY` — this is mandatory. `docker-compose.prod.yml` refuses to start the backend
without it; in dev, without it enrichment silently fails and bookmarks are never enriched.

## Stack

- **Backend**: Python 3.14, FastAPI, SQLAlchemy 2 asyncio (aiosqlite), Pydantic v2, `uv` for
  dependency management, pytest + pytest-asyncio, ruff. Routes, use cases, and the repository
  are async all the way down.
- **Frontend**: React 19, TypeScript, Vite. Plain `fetch`, no data-fetching library.
- **Database**: SQLite, a single `bookmarks` table, no migrations tool — the schema is created at
  startup and isn't expected to change often.
- **Containers**: separate dev (hot reload) and prod (nginx-served static build) Docker Compose
  files.

## Running it

**Setup (once, mandatory):**

```bash
cp .env.example .env
# then edit .env and fill in GEMINI_API_KEY
```

**Dev** — hot reload on both services:

```bash
docker compose up --build
```

- Backend: http://localhost:8000
- Frontend: http://localhost:5173

**Prod** — nginx-served static frontend, no source mounts:

```bash
docker compose -f docker-compose.prod.yml up --build
```

- Backend: http://localhost:8000
- Frontend: http://localhost:80

There is no database container. SQLite isn't a server process — it's a file the backend process
reads and writes directly through SQLAlchemy. Persistence comes from the named Docker volume
`bookmarks_data`, mounted at `/data` in the backend container, holding `bookmarks.db`. It survives
`docker compose down`; only `docker compose down -v` or `docker volume rm` removes it.

> Dev and prod share that same volume name by default. If you run both against this same
> directory without removing the volume in between, the prod image's non-root user can hit a
> "readonly database" error against files the dev image's root user created. Run
> `docker compose down -v` when switching modes, or give each mode its own project name
> (`docker compose -p bookmarks-dev ...` / `-p bookmarks-prod ...`).

### What each compose file mounts

Dev (`docker-compose.yml`) bind-mounts `./backend/app` and `./frontend` into the containers so
both dev servers reload on edits. The frontend service also declares an anonymous volume over
`/app/node_modules`, which keeps the host's `node_modules` from shadowing the one `npm ci` built
inside the image — without it, a host install for a different platform breaks the container.

Prod (`docker-compose.prod.yml`) bind-mounts no source: the backend runs uvicorn without
`--reload` as a non-root user, and the frontend is a multi-stage build where `npm run build`
output is served as static files by nginx. Both use `restart: unless-stopped`.

### Running the backend without Docker

```bash
cd backend
uv sync
GEMINI_API_KEY=... uv run uvicorn app.main:app --reload --port 8000
```

The root `.env` is only read by `docker compose` (it substitutes `${GEMINI_API_KEY}` in the compose
files); running uvicorn directly needs the variable exported in your shell instead.

### Running the frontend without Docker

```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_URL` if the backend isn't at `http://localhost:8000`.

## API

| Method | Path | Query params | Notes |
|--------|------|---------------|-------|
| `GET` | `/bookmarks` | `name`, `tag`, `type` | Lists active (non-deleted) bookmarks. All filters are optional and combine with AND. |
| `POST` | `/bookmarks` | — | Creates a bookmark, `201`. |
| `GET` | `/bookmarks/{id}` | — | `404` if missing or soft-deleted. |
| `PUT` | `/bookmarks/{id}` | — | Full replace of the mutable fields. `id`/`created_at` are server-controlled. |
| `DELETE` | `/bookmarks/{id}` | — | Soft delete — sets `deleted_at`, `204`, no body. |

`type` is one of `post`, `video`, `tweet`, `site`. Errors use FastAPI's default shape,
`{"detail": "..."}`. CORS is wildcard (`allow_origins=["*"]`) since this isn't public-facing.

`tag` filtering is an **exact match** against one entry in the bookmark's tag list, not a
substring match — filtering by `py` will not match a bookmark tagged `python`. This is a
deliberate choice: the naive approach (SQL `LIKE '%tag%'` over the JSON column) gives wrong
results whenever one tag is a substring of another, so the query instead expands the tag array
with SQLite's `json_each` and matches entries exactly. `name`, by contrast, *is* a
case-insensitive substring match, since it's meant as a search box.

## Data model

Single table, `bookmarks`:

| column | type | notes |
|--------|------|-------|
| `id` | UUID | primary key, generated server-side with `uuid7` (time-ordered) |
| `name` | string | required |
| `url` | string | required |
| `description` | string | optional |
| `created_at` | timestamp | set at creation |
| `tags` | JSON array of strings | one column, not a join table |
| `type` | enum | `post`, `video`, `tweet`, `site` |
| `deleted_at` | timestamp, nullable | soft-delete marker; never exposed over the API |

`tags` is a JSON-encoded array of strings in a single column (SQLAlchemy's `JSON` type) rather
than a separate join table — the simplest option that still models tags as a real list, at the
cost of needing a JSON query to filter by one instead of a SQL join. `type` is a Python `Enum`,
enforced by Pydantic on the way in and stored as its string value.

No migrations tool — `Base.metadata.create_all()` runs once at startup and only ever creates
missing tables; it will not alter an existing one. Changing a column today means deleting the
database file or volume. If the schema starts evolving, that's the point to introduce Alembic —
noted here so it reads as a deliberate decision rather than an oversight.

## Backend architecture: ports and adapters

The backend follows a hexagonal (ports and adapters) layout. The dependency direction points
inward — `adapters` depend on `application`, which depends on `domain`; `domain` depends on
nothing in this project:

```
backend/app/
├── domain/
│   ├── models.py            # Bookmark (dataclass), BookmarkType, ExtractedData — no framework imports
│   ├── ports.py              # BookmarkRepository, ContentFetcher, BookmarkEnricherService (Protocols)
│   └── exceptions.py         # ContentFetchError, EnrichmentError, BookmarkNotFoundError, BookmarkInvalidError
├── application/
│   ├── bookmark_service.py   # use cases: list/get/create/update/delete, depend only on the port
│   └── enrich_bookmark.py    # fetches a bookmark's URL, derives description/tags, persists the merge
├── adapters/
│   ├── inbound/
│   │   ├── api.py             # FastAPI routes — translate HTTP into use-case calls
│   │   ├── schemas.py          # Pydantic request/response DTOs
│   │   └── background.py       # BackgroundTask edge: opens its own DB session, runs enrich_bookmark
│   └── outbound/
│       ├── database.py         # SQLAlchemy async engine/session/Base
│       ├── orm.py              # BookmarkRow — the SQLAlchemy table mapping
│       ├── sqlalchemy_repository.py  # implements BookmarkRepository against SQLite
│       ├── http_content_fetcher.py   # implements ContentFetcher over httpx
│       └── llm_bookmark_enricher.py  # implements BookmarkEnricherService via litellm + Gemini
└── main.py                    # composition root — builds the FastAPI app, wires the adapter in
```

The domain `Bookmark` (a plain dataclass) and the persistence `BookmarkRow` (a SQLAlchemy model)
are deliberately separate types; `sqlalchemy_repository.py` maps between them on every read and
write. This keeps the domain and application layers free of any SQLAlchemy or Pydantic import —
swapping the database, or testing the business logic without one, only touches the outbound
adapter.

`POST /bookmarks` returns as soon as the bookmark is created; enrichment runs afterwards in a
`BackgroundTask`. Because that task runs after the request's DB session has already closed, it
opens its own (`background.py`) rather than reusing the route's — see `backend/CLAUDE.md` for the
full rationale and the concurrency tradeoff this makes (a `PUT` racing the background write can
overwrite it, accepted as-is for a single-user local app).

`tests/` mirrors that structure. `tests/application/test_bookmark_service.py` demonstrates the
payoff: it exercises `bookmark_service` against an in-memory fake repository, with no database and
no FastAPI involved. `tests/adapters/inbound/test_api.py` covers the same behavior end-to-end
through the HTTP layer, and `tests/repository_contract.py` holds the shared behavioral contract
that every repository implementation — fake and real alike — is made to satisfy.

## Frontend

A single-page app (`App.tsx`) — table view (name linking out, description, tags as pills, type,
date), an inline add form, inline row editing, delete with confirmation, and tag/type filters that
query the backend directly rather than filtering client-side. Notion-style: quiet borders,
generous whitespace, no UI framework. `api.ts` holds the `fetch` wrappers; `types.ts` mirrors the
API's request/response shapes.

## Testing and linting

```bash
cd backend
uv run pytest         # 87 tests: domain and application unit tests + adapter integration tests
uv run ruff check .
uv run ruff format --check .
```

```bash
cd frontend
npm run typecheck
npm run build
```

## Known caveats

- SQLite serializes writes at the file level — fine at this app's scale (single backend
  instance), but it wouldn't scale to multiple backend replicas writing concurrently.
- `VITE_API_URL` is compile-time, not runtime. In dev the Vite dev server reads it as an env var
  at startup; in prod it's baked into the static bundle via a Docker build ARG, defaulting to
  `http://localhost:8000`. Deploying beyond localhost means rebuilding the frontend image with the
  real host, not just restarting the container.
- CORS is wildcard-open; tighten `allow_origins` before exposing this to the internet.
