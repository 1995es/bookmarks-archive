# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

FastAPI backend for the bookmarks manager. Python 3.14, managed with `uv`. Async end to end:
routes, use cases, and the repository port are all `async def`, over SQLAlchemy asyncio +
aiosqlite — a prerequisite for adding FastAPI background tasks. See the repo-root
`CLAUDE.md` for cross-cutting concerns (Docker, the frontend contract, stale design docs).

## Commands

```bash
uv sync                                            # install deps (incl. dev group)
uv run uvicorn app.main:app --reload --port 8000   # run locally
uv run pytest                                      # full suite (50 tests, <1s)
uv run pytest tests/domain/test_models.py          # one file
uv run pytest -k tag_filter                        # one test by name substring
uv run ruff check . && uv run ruff format --check . # lint + format check
uv run ruff check --fix . && uv run ruff format .   # apply fixes
```

Ruff is configured in `pyproject.toml`: line length 100, rules `E,F,I,UP,B`. Two deliberate
ignores are documented inline there (`B008` for `Depends(...)` defaults, `UP042` for the explicit
`BookmarkType(str, Enum)`) — don't "fix" the code those cover.

## Architecture: ports and adapters

Dependencies point inward. `adapters` → `application` → `domain`; `domain` imports nothing from
this project's other layers and no frameworks at all.

```
app/
├── domain/          models.py (Bookmark dataclass, BookmarkType), ports.py
│                    (BookmarkRepository Protocol), exceptions.py
├── application/     bookmark_service.py — use cases, module-level functions taking a repo
├── adapters/
│   ├── inbound/     api.py (FastAPI routes), schemas.py (Pydantic DTOs)
│   └── outbound/    database.py (engine/session), orm.py (BookmarkRow),
│                    sqlalchemy_repository.py (implements the port)
└── main.py          composition root: app, CORS, exception handlers, create_all at lifespan
```

Rules that keep this working, in rough order of how easy they are to break:

- **No SQLAlchemy or Pydantic imports in `domain/` or `application/`.** If a change seems to
  require one, it belongs in an adapter instead.
- **`Bookmark` (domain dataclass) and `BookmarkRow` (ORM) are separate types on purpose.**
  `sqlalchemy_repository.py` maps between them on every read and write via `_to_domain` /
  `_copy_into_row`. When you add a field, both mapping functions need it.
- **Mutate a `Bookmark` only through its methods.** `update()` and `delete()` are the sanctioned
  paths; `update()` re-runs `validate()` so an invalid state can't be assigned. Setting attributes
  directly bypasses invariants.
- **Business rules live in `domain`/`application`, never in `api.py`.** Routes translate HTTP into
  use-case calls and turn `None` into a 404 — nothing more.

### Validation happens in two places, deliberately

`schemas.py` enforces *wire-format* rules (absolute http(s) URL, length bounds, tag count/length)
and rejects violations with FastAPI's own 422. `Bookmark.validate()` enforces the *domain*
invariants (non-empty name and url) independently, so the domain stays correct even when reached
without going through HTTP. `main.py` maps `BookmarkInvalidError` → 422 to match.

### Error handling

- Everyday "not found" is expressed as `None` returned from the service layer; `api.py` raises
  `HTTPException(404)`.
- `BookmarkNotFoundError` is raised only by `repo.save()` when the row vanished between get and
  save (a concurrent-delete race). `main.py` has a handler for it; the comment there explains why
  it's normally unreachable.

### Soft deletes

`deleted_at` is set by `Bookmark.delete()` and never exposed over the API. Repositories are
required to hide soft-deleted bookmarks from both `list()` and `get()` — this is part of the port's
contract, not an implementation choice.

## Tests

`tests/` mirrors `app/` by layer: `domain/`, `application/`, `adapters/inbound/`,
`adapters/outbound/`.

`tests/repository_contract.py` holds the shared behavioral contract every `BookmarkRepository`
implementation must satisfy (including the soft-delete rule above). Its test functions are
*imported* into each repository's test module — pytest collects imported `test_*` functions in the
importing module, binding them to that module's `repo` fixture. **Any new repository
implementation must import those tests into its own module** (with `# noqa: F401`) rather than
re-implementing the assertions.

`tests/application/test_bookmark_service.py` runs against an in-memory `FakeBookmarkRepository` —
no database, no FastAPI. That fake also satisfies the contract, so it must stay in sync with the
real adapter's filtering behavior (`name` is a case-insensitive substring match; `tag` is an
**exact** match against one entry in the list, not a substring).

`tests/adapters/inbound/test_api.py` goes through the real app with a temp-file SQLite database,
overriding the `get_db` dependency. It drives the app with `httpx.AsyncClient` over
`ASGITransport` rather than `TestClient`: the overridden async session must live on the same event
loop as the test, which `TestClient`'s worker thread would not give it.

pytest-asyncio runs in `asyncio_mode = "auto"` (set in `pyproject.toml`), so async tests and async
fixtures need no `@pytest.mark.asyncio` decorator. **A repository test helper that forgets `await`
gets a coroutine object, not a result** — assertions on it fail in confusing ways.

## Storage notes

- `DATABASE_URL` defaults to `sqlite:///./bookmarks.db` locally, `sqlite:////data/bookmarks.db` in
  containers. `database.py` rewrites a driverless `sqlite://` URL to `sqlite+aiosqlite://`, so the
  compose files and `Dockerfile.prod` keep working unchanged; `create_async_engine` would otherwise
  reject the sync pysqlite dialect. `check_same_thread` is only passed for `sqlite://` URLs — other
  dialects reject it.
- No migrations tool. `create_all` runs at startup via `conn.run_sync()` (it is sync DDL) and only
  creates missing tables; it will not alter an existing one. **Changing a column means deleting the dev database file (or
  the Docker volume) — or introducing Alembic, which is the right move if the schema starts
  evolving.**
- `tags` is a JSON array in one column, not a join table — chosen as the simplest thing that still
  models tags as a real list, accepting a JSON query instead of a SQL join as the cost. Tag
  filtering therefore uses SQLite's `json_each` table-valued function for an exact match on a list
  entry; a `LIKE '%tag%'` over the JSON column would wrongly match `python` when filtering by `py`.
  `json_each` is SQLite-specific — switching dialects means rewriting that branch.
- `orm.py` must be imported before `create_all()` so `BookmarkRow` is registered on
  `Base.metadata`; `main.py` does this with a `# noqa: F401` import.
