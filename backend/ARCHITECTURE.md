# Backend architecture

FastAPI backend for the bookmarks manager, laid out as ports and adapters. Python 3.14, managed
with `uv`, async end to end — routes, use cases, and the repository port are all `async def`, over
SQLAlchemy asyncio + aiosqlite.

For the system-level picture see the repo-root [`ARCHITECTURE.md`](../ARCHITECTURE.md).

## Layers

Dependencies point inward. `adapters` → `application` → `domain`, and `domain` imports nothing
from the other layers and no framework at all.

The application layer is module-level functions taking a port as their first argument, not
classes. `main.py` is the only place that knows which concrete adapter is used.

## Domain model

`Bookmark` is a plain dataclass. Its state is only ever changed through its own methods —
`update()`, `delete()`, `enrich()` — each of which re-runs `validate()`, so an invalid bookmark
can't be assigned into existence. Business rules live here and in `application/`, never in
`api.py`; routes translate HTTP into use-case calls and turn a `None` result into a 404.

The domain `Bookmark` and the persisted `BookmarkRow` are deliberately separate types.
`sqlalchemy_repository.py` maps between them on every read and write, which is what keeps
SQLAlchemy and Pydantic out of the inner layers.

### Validation happens twice, on purpose

`schemas.py` enforces *wire-format* rules — absolute http(s) URL, length bounds, tag count and
length — and rejects violations with FastAPI's 422. `Bookmark.validate()` independently enforces
the *domain* invariants, so the domain stays correct even when reached without going through HTTP,
which is exactly what happens during background enrichment.

`POST` is deliberately laxer than `PUT`: on create, `url` is the only required field, and a missing
name is filled in from the URL's host as a placeholder. Editing an existing bookmark already has
real values to work with, so `PUT` keeps the stricter contract.

## HTTP API

Five routes over one resource. Interactive docs are at `/docs` when the backend is running.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/bookmarks` | Lists live bookmarks. Returns an `X-Total-Count` header with the unpaginated total. |
| `POST` | `/bookmarks` | `201`. Schedules background enrichment. `409` if the URL belongs to a live bookmark. |
| `GET` | `/bookmarks/{id}` | `404` if missing or soft-deleted. |
| `PUT` | `/bookmarks/{id}` | Full replace of the mutable fields; `id` and `created_at` are server-controlled. `409` on URL collision. |
| `DELETE` | `/bookmarks/{id}` | Soft delete — sets `deleted_at`, returns `204`. |

`GET /bookmarks` query parameters:

| Param | Default | Notes |
|---|---|---|
| `name` | — | Case-insensitive **substring** match. |
| `tag` | — | **Exact** match against one entry of the tag list. |
| `type` | — | One of `post`, `video`, `tweet`, `site`. |
| `sort_by` | `created_at` | Or `name`. |
| `sort_order` | `desc` | Or `asc`. |
| `limit` | `50` | 1–200. |
| `offset` | `0` | |

Filters combine with AND. Tag matching being exact is deliberate: the naive `LIKE '%tag%'` over the
JSON column would match `python` when you filtered by `py`, so the query expands the array with
SQLite's `json_each` and compares entries. `name` is a substring match because it backs a search
box.

Errors use FastAPI's default `{"detail": "..."}` shape. CORS is wildcard-open — this isn't meant to
be public-facing.

## Data model

One table, `bookmarks`:

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | primary key, generated server-side with uuid7 (time-ordered) |
| `name` | string | required |
| `url` | string | required; unique among live bookmarks |
| `description` | string | optional |
| `created_at` | timestamp | set at creation |
| `tags` | JSON array of strings | one column, not a join table |
| `type` | enum | `post`, `video`, `tweet`, `site` |
| `deleted_at` | timestamp, nullable | soft-delete marker; never exposed over the API |

`tags` is a JSON-encoded array in a single column rather than a join table — the simplest option
that still models tags as a real list, at the cost of a JSON query instead of a SQL join to filter
by one.

URL uniqueness is a SQLite **partial** unique index (`WHERE deleted_at IS NULL`). A plain
`UNIQUE(url)` would wrongly block re-adding a URL you had already deleted, since a soft-deleted row
keeps its URL forever. The repository relies on the index as the authority rather than a pre-read
`SELECT`, so there is no check-then-insert race; it translates the resulting `IntegrityError` into
`BookmarkUrlConflictError`, which `main.py` maps to `409`.

Two couplings are SQLite-specific and would need rewriting to move to another database: `json_each`
tag filtering, and that partial index.

### Schema changes via Alembic

Migrations live in `alembic/versions/`, applied with `alembic upgrade head`. That command runs as a
step *before* the app process starts — chained into the `CMD` in `Dockerfile`/`Dockerfile.prod`
(`alembic upgrade head && uvicorn ...`) — rather than inside `main.py`'s lifespan, per the compose
setup: `docker-compose up` is the whole deploy step, so there's no separate place to run a one-off
command before it.

The app no longer calls `Base.metadata.create_all()` at all; Alembic owns the entire schema,
including creating the `bookmarks` table in the first place.

The baseline revision (`alembic/versions/875c6f32916c_create_bookmarks_table.py`) is a plain
`create_table`, written as though the project had used Alembic from day one — it assumes an empty
database. Alembic was actually adopted after the schema had already been managed by `create_all()`
(fresh installs) plus a hand-rolled `ALTER TABLE` step for columns added later (the now-deleted
`adapters/outbound/migrations.py`), so any pre-existing database (a local `bookmarks.db`, the prod
`/data` volume) must be `alembic stamp head`'d once — not upgraded — before `alembic upgrade head`
runs against it for the first time; otherwise it fails with "table already exists".

Future schema changes are ordinary Alembic revisions (`alembic revision -m "..."`, ideally
autogenerated from the ORM) rather than another hand-rolled inspector check — the baseline revision
is a one-time adoption shim, not the pattern to keep following.

`DATABASE_URL` defaults to `sqlite:///./bookmarks.db` locally and `sqlite:////data/bookmarks.db` in
containers. A driverless `sqlite://` URL is rewritten to `sqlite+aiosqlite://` automatically, so
the compose files work unchanged.

## Background enrichment

`POST /bookmarks` returns as soon as the row is written, then a FastAPI `BackgroundTask` runs
`enrich_bookmark()`:

1. `ContentFetcher.fetch()` retrieves the page and returns a `FetchedContent` — the `<title>`, the
   meta description, and boilerplate-stripped body text as three separate fields, so the LLM prompt
   gets the page's own title and description as distinct signals rather than one flattened blob.
2. `BookmarkEnricherService.extract_data()` sends that to the model named by `LLM_MODEL` through
   `litellm.acompletion`, requesting structured JSON (`{description, tags}`).
3. `Bookmark.enrich()` merges the result: the description is **appended** to whatever the user
   wrote, tags are merged and deduplicated preserving order, and both are truncated to the domain's
   limits. Nothing the user typed is discarded.

The name is the one field replaced outright rather than merged — and only when the current name is
still the create-time placeholder derived from the URL's host. A name you actually typed is left
alone.

Two properties worth knowing:

- **The task opens its own database session.** The request's session is already closed by the time
  it runs, so anything scheduled with `BackgroundTasks` must compose a fresh repository.
- **Every failure is swallowed and logged.** A page that won't fetch, a model that won't answer, or
  a bookmark deleted mid-flight just leaves the bookmark un-enriched. The task boundary is the only
  place that decides what to do with a failure; `enrich_bookmark()` itself catches nothing.

There is one accepted race: a `PUT` landing between the task's read and its write can be
overwritten, or overwrite it. For a single-user local app that's not worth a locking scheme.

### Model configuration

`LLM_MODEL` takes litellm's `provider/model` form and defaults to `gemini/gemini-3.5-flash`. At
startup `llm_config.resolve_llm_model()` asks litellm which provider that names and checks the
matching `*_API_KEY` environment variable is present, raising `MissingLLMCredentialsError` if not.
A misconfigured model or a missing key therefore crashes the app on boot rather than silently
failing the first enrichment an hour later. litellm reads the key value itself at call time; this
check only confirms it exists.

## Testing

```bash
uv run pytest                              # full suite, well under a second
uv run pytest tests/domain/test_models.py  # one file
uv run pytest -k tag_filter                # by name substring
uv run ruff check . && uv run ruff format --check .
```

`tests/` mirrors `app/` by layer. The payoff of the port boundaries shows up here:

- `tests/domain/` and `tests/application/` run against an in-memory `FakeBookmarkRepository` — no
  database, no FastAPI, no network, no API key.
- `tests/repository_contract.py` holds the shared behavioral contract (soft-delete invisibility,
  live-only URL uniqueness, filter semantics). Its test functions are *imported* into each
  repository's test module, so the real SQLite adapter and the in-memory fake are held to exactly
  the same standard. A new repository implementation imports those tests rather than
  reimplementing the assertions — which is also what keeps the fake a faithful stand-in.
- `tests/adapters/inbound/test_api.py` drives the real app end to end over `httpx.AsyncClient` with
  a temp-file SQLite database. Background enrichment is stubbed out by default so ordinary CRUD
  tests never make a network call; the enrichment tests re-override it with fakes.

pytest-asyncio runs in auto mode, so async tests and fixtures need no decorator.

## Conventions

Ruff is configured in `pyproject.toml`: line length 100, rules `E,F,I,UP,B`. Two ignores are
documented inline there and are deliberate. Two rules of thumb cover most changes:

- No SQLAlchemy or Pydantic import belongs in `domain/` or `application/`. If a change seems to
  need one, it belongs in an adapter.
- When you add a field to `Bookmark`, both mapping directions in `sqlalchemy_repository.py` need
  it, and `frontend/src/types.ts` needs it too — the frontend contract is hand-maintained and
  nothing fails at build time if it drifts.
