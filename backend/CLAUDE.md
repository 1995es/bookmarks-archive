# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

FastAPI backend for the bookmarks manager. Python 3.14, managed with `uv`. Async end to end:
routes, use cases, and the repository port are all `async def`, over SQLAlchemy asyncio +
aiosqlite — a prerequisite for FastAPI background tasks, which now run asynchronous bookmark
enrichment after `POST /bookmarks`. See the repo-root `CLAUDE.md` for cross-cutting concerns
(Docker, the frontend contract, stale design docs).

## Commands

```bash
uv sync                                            # install deps (incl. dev group)
uv run uvicorn app.main:app --reload --port 8000   # run locally
uv run pytest                                      # full suite (fast — a couple of seconds)
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
├── domain/          models.py (Bookmark dataclass, BookmarkType, FetchedContent,
│                    ExtractedData), ports.py (BookmarkRepository, ContentFetcher,
│                    BookmarkEnricherService — all ABC with @abstractmethod), exceptions.py
├── application/     bookmark_service.py (list/count/get/create/update/delete),
│                    enrich_bookmark.py — use cases, module-level functions taking a repo
│                    (+ fetcher/enricher for enrichment)
├── adapters/
│   ├── inbound/     api.py (FastAPI routes), schemas.py (Pydantic DTOs), background.py
│   │                (BackgroundTask edge that runs enrich_bookmark after POST)
│   └── outbound/    database.py (engine/session), orm.py (BookmarkRow),
│                    sqlalchemy_repository.py (implements BookmarkRepository),
│                    http_content_fetcher.py (implements ContentFetcher over httpx),
│                    llm_bookmark_enricher.py (implements BookmarkEnricherService via
│                    litellm.acompletion), llm_config.py (resolves/validates LLM_MODEL)
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
- **Enrich a `Bookmark` only through `enrich()`.** Same rule as `update()`/`delete()`: it appends
  the generated description/tags onto whatever the user already provided (deduplicating tags,
  preserving order, truncating to `_MAX_TAGS`) and re-runs `validate()`.
- **`_MAX_TAGS`/`_MAX_TAG_LENGTH` live in `domain/models.py`, not `schemas.py`.** `schemas.py`
  imports them. The domain needs its own copy of the limit because `enrich()` runs outside any
  HTTP request — the LLM-generated tags never pass through Pydantic validation.

### Listing: filters, sorting, pagination

`repo.list()` and `bookmark_service.list_bookmarks()` take `name`/`type`/`tag` filters plus
`sort_by` (`name` | `created_at`, default `created_at`), `sort_order` (default `desc`), `limit`
(default 50, the route caps it at 1–200) and `offset`. `repo.count()` takes the same filters and
**ignores limit/offset** — it is the total the page is a window into.

`GET /bookmarks` calls both: the body is the page, and the count goes out in an `X-Total-Count`
response header. Adding a filter therefore means adding it in three places — `list()`, `count()`,
and the route — or the total will disagree with the page. `SortField`/`SortOrder` are `Literal`
aliases in `domain/ports.py`; a new sort field needs the alias, `_SORT_COLUMNS` in the real
adapter, and the fake's sort key.

**Known divergence: `sort_by="name"` is case-sensitive in the real adapter and case-insensitive in
the fake.** SQLite's default BINARY collation puts `Banana` before `apple`; `FakeBookmarkRepository`
sorts on `name.lower()` and puts `apple` first. `tests/repository_contract.py` only sorts same-case
names, so nothing catches it. Fixing it means either a `collate("NOCASE")` in the real adapter or
dropping `.lower()` from the fake — pick one, then add a mixed-case sort test to the contract so
they can't drift again.

### Validation happens in two places, deliberately

`schemas.py` enforces *wire-format* rules (absolute http(s) URL, length bounds, tag count/length)
and rejects violations with FastAPI's own 422. `Bookmark.validate()` enforces the *domain*
invariants (non-empty name and url) independently, so the domain stays correct even when reached
without going through HTTP. `main.py` maps `BookmarkInvalidError` → 422 to match.

`BookmarkCreate` diverges from `BookmarkBase` (which `BookmarkUpdate`/`BookmarkRead` still use):
`url` is the only required field. A blank or omitted `name` is turned into `None` by
`BookmarkCreate`'s own validator, and `bookmark_service.create_bookmark` derives a fallback from
the URL's host (`_derive_name_from_url`, stripping a leading `www.`) only when `name is None` — an
explicit empty string still fails `Bookmark.validate()`, which is what
`test_create_rejects_empty_name` pins down. An omitted `type` defaults to `BookmarkType.POST` in
both the schema and the service function. This asymmetry is deliberate: editing an existing
bookmark already has real values, so `PUT` keeps the stricter `BookmarkBase` contract.

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

### URL uniqueness

`url` is unique **among live (non-deleted) bookmarks** — also part of the port's contract, proven
by `tests/repository_contract.py` against both the real adapter and the fake. `add()` and `save()`
raise `BookmarkUrlConflictError` when another visible bookmark holds the url; `main.py` maps that
to `409`. A soft-deleted bookmark keeps its row (and url) forever, so a plain `UNIQUE(url)` would
wrongly block re-adding a url the user already deleted — the constraint is therefore a **SQLite
partial unique index** (`uq_bookmarks_url_active` in `orm.py`, `sqlite_where="deleted_at IS NULL"`),
same dialect coupling as the `json_each` tag filter. The real adapter enforces it in the database
and translates `IntegrityError` (the only unique constraint besides the uuid7 PK) into the domain
exception; the fake mirrors the *live-only* rule in memory so it stays a faithful contract stand-in.
The real adapter relies on the DB index as the authority rather than a pre-read `SELECT`, so
there's no check-then-insert race.

### Background enrichment

`POST /bookmarks` schedules a `BackgroundTask` (`background.py::run_enrichment`) that runs
`enrich_bookmark()` after the response is returned: it fetches the bookmark's URL
(`ContentFetcher`, returning a `FetchedContent`), derives a description/tags from it
(`BookmarkEnricherService`), and persists the merge via `Bookmark.enrich()` + `repo.save()`.

- **`ContentFetcher.fetch()` returns a `FetchedContent`** (`domain/models.py`) — `name`
  (`<title>`), `description` (meta description), and `content` (boilerplate-stripped body text) as
  separate fields, rather than one flattened string. `BookmarkEnricherService.extract_data()` takes
  the whole `FetchedContent` (as `fetched`, alongside `url`) so the LLM prompt gets the page's own
  title/description as distinct signals from its body, not just body text.
- **`enrich_bookmark()` also updates the bookmark's name from `fetched.name`, conditionally.** It
  only overwrites when the bookmark's current name still equals
  `bookmark_service.derive_name_from_url(bookmark.url)` — i.e. still the create-time placeholder
  from the url-only fast path — and `fetched.name` is non-empty. A name the user actually typed (at
  creation or via a later edit) is left alone. `Bookmark.enrich(data, *, name=...)` does the
  replacement outright (not merged like description) and truncates to `_MAX_NAME_LENGTH`, same
  reasoning as the description/tags truncation below.
- **The background task opens its own `AsyncSession` via `SessionLocal`, never the route's.**
  `get_db` closes its session when the request ends, before the task runs, so the route's injected
  `repo` is unusable by then. `background.py` composes a fresh `SqlAlchemyBookmarkRepository` for
  this reason — anything scheduled with `BackgroundTasks` in this codebase must do the same.
- **`run_enrichment` swallows every exception.** `BookmarkNotFoundError` and `BookmarkInvalidError`
  are logged at `warning`; anything else is logged at `exception`. Nothing propagates past this
  function. `enrich_bookmark()` itself does *not* catch anything; the task boundary is deliberately
  the only place that decides what to do with a failure.
- **`Bookmark.enrichment_status` (`pending | done | failed`) makes a permanent failure visible and
  stoppable, instead of indistinguishable from "still running".** A bookmark is born `pending`;
  `Bookmark.enrich()` sets it to `done`; `background.py::_mark_enrichment_failed()` sets it to
  `failed` once retries are exhausted. The frontend's poll (see `frontend/CLAUDE.md`) stops on
  either terminal state — this is what fixes the pre-existing bug where a permanently-failed
  enrichment (network down, LLM error, an exceeded free-tier rate limit) left the frontend polling
  `GET /bookmarks` every 5s forever, since `!description` never became true. There is currently no
  way to move a `failed` bookmark back to `pending` — a manual retry (per-bookmark or bulk) is a
  deliberately deferred follow-up, not yet implemented.
- **`ContentFetchError`/`EnrichmentError` are retried with backoff before being treated as a
  failure**, via `tenacity`: `background.py::enrich_bookmark_with_retry` wraps `enrich_bookmark()`
  with `stop_after_attempt(5)` and `wait_exponential(multiplier=1, min=1, max=30)`, and
  `reraise=True` so the final attempt's exception is what `run_enrichment` catches.
  `BookmarkNotFoundError`/`BookmarkInvalidError` are *not* retried — the bookmark being deleted or
  invalid won't change on a second attempt. Only after all 5 attempts fail does
  `_mark_enrichment_failed()` run: it re-`get()`s the bookmark (the one `enrich_bookmark` held may
  be stale after multiple attempts on the same session) and calls
  `Bookmark.mark_enrichment_failed()` + `repo.save()`, itself tolerating a concurrent delete via
  `BookmarkNotFoundError`. Tests that need to exercise the retry path without five real backoffs
  monkeypatch `enrich_bookmark_with_retry.retry.wait` (tenacity exposes the `Retrying`/
  `AsyncRetrying` instance as `.retry` on the decorated function) — see
  `tests/adapters/inbound/test_background.py`.
- **Only one repo read.** A concurrent `PUT` between the task's `get()` and `save()` can be
  overwritten by the enrichment write, or vice versa. Accepted as-is — single-user, local app.
- **`LLMBookmarkEnricherService`** (`app/adapters/outbound/llm_bookmark_enricher.py`) calls
  `litellm.acompletion` against whatever model `LLM_MODEL` resolves to (default:
  `gemini/gemini-3.5-flash`), requesting structured JSON output (`{description, tags}`) via
  `response_format`, truncating `fetched.content` to `max_content_chars` first. Any `litellm`
  exception, or a response that doesn't parse into that shape, is wrapped in `EnrichmentError`.
- **`LLM_MODEL` and its API key are resolved and validated once, at startup**, not per
  enrichment. `app/adapters/outbound/llm_config.py::resolve_llm_model()` reads `LLM_MODEL`
  (litellm's `provider/model` form), asks `litellm.get_llm_provider()` which provider that is,
  and checks the matching `*_API_KEY` env var is set (own explicit map, since litellm doesn't
  expose a "which env var does this provider need" lookup) — raising
  `MissingLLMCredentialsError` if not. `main.py`'s `lifespan` calls this before `yield` and stores
  the result on `background.llm_model`, a module-level var that `run_enrichment` reads when
  constructing `LLMBookmarkEnricherService`, so a misconfigured model/key crashes the app on boot
  instead of only failing the first background enrichment. `litellm` still reads the actual key
  value from the environment itself when `acompletion` runs — this module only validates it's
  present, it doesn't pass it explicitly.

## Tests

`tests/` mirrors `app/` by layer: `domain/`, `application/`, `adapters/inbound/`,
`adapters/outbound/`.

`tests/repository_contract.py` holds the shared behavioral contract every `BookmarkRepository`
implementation must satisfy (including the soft-delete rule above). Its test functions are
*imported* into each repository's test module — pytest collects imported `test_*` functions in the
importing module, binding them to that module's `repo` fixture. **Any new repository
implementation must import those tests into its own module** (with `# noqa: F401`) rather than
re-implementing the assertions.

`tests/application/test_bookmark_service.py` and `tests/application/test_enrich_bookmark.py` run
against an in-memory `FakeBookmarkRepository` (defined once in `tests/fakes.py`) — no database, no
FastAPI. That fake also satisfies the contract, so it must stay in sync with the real adapter's
filtering, sorting and pagination behavior (`name` is a case-insensitive substring match; `tag` is
an **exact** match against one entry in the list, not a substring; sorting by name currently
diverges on case — see "Listing" above) — and its `save()` raises `BookmarkNotFoundError`
for an untracked id, matching `SqlAlchemyBookmarkRepository.save()`, so the enrichment
concurrent-delete race is testable without a database.

`tests/adapters/inbound/test_api.py` goes through the real app with a temp-file SQLite database,
overriding the `get_db` dependency. It drives the app with `httpx.AsyncClient` over
`ASGITransport` rather than `TestClient`: the overridden async session must live on the same event
loop as the test, which `TestClient`'s worker thread would not give it. The `client` fixture also
overrides `get_enrichment_runner` with a no-op by default, so ordinary CRUD tests never trigger a
real background task; enrichment-specific tests re-override it with a spy or a runner built from
fakes. `ASGITransport` is constructed with `raise_app_exceptions=False`, mirroring a real server:
`BackgroundTasks` run *after* the HTTP response bytes are already sent, so a background failure
can no longer change a response the client already received — without this flag, `ASGITransport`
would re-raise even a post-completion background exception, which a real socket has no way to do.

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
  creates missing tables; it will not alter an existing one — and, importantly, **it will not add a
  new index (like `uq_bookmarks_url_active`) to a table that already exists.** A database created
  before the url-uniqueness index was added therefore won't get the constraint until it's recreated.
  **Changing a column or adding an index means deleting the dev database file (or the Docker volume)
  — or introducing Alembic, which is the right move if the schema starts evolving.**
- `tags` is a JSON array in one column, not a join table — chosen as the simplest thing that still
  models tags as a real list, accepting a JSON query instead of a SQL join as the cost. Tag
  filtering therefore uses SQLite's `json_each` table-valued function for an exact match on a list
  entry; a `LIKE '%tag%'` over the JSON column would wrongly match `python` when filtering by `py`.
  `json_each` is SQLite-specific — switching dialects means rewriting that branch.
- `orm.py` must be imported before `create_all()` so `BookmarkRow` is registered on
  `Base.metadata`; `main.py` does this with a `# noqa: F401` import.
- `httpx` and `litellm` are production dependencies (not `dev`) — `HttpContentFetcher` and
  `LLMBookmarkEnricherService` need them at runtime for enrichment, not just in tests. Whichever
  `*_API_KEY` matches `LLM_MODEL`'s provider must be set wherever the backend actually runs; see
  "Background enrichment" above for how that's validated at startup.
