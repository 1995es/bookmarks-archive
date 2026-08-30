# Bookmarks Archive

A small self-hosted bookmarks manager: list, add, edit, delete, and filter bookmarks by tag or
type. FastAPI backend, React + Vite + TypeScript frontend, SQLite storage, Docker Compose for both
dev and prod.

## What it does

You save a URL. The bookmark shows up immediately with whatever you typed — a URL on its own is
enough. In the background the backend then fetches that page, asks an LLM to read it, and fills in
what you didn't: a description, a set of tags, and a real title in place of the placeholder one.
Anything you wrote yourself is kept; the generated content is appended, not substituted.

Everything else is deliberately plain. Filtering by tag or type happens server-side against a
single SQLite table. Deletes are soft, so a URL you removed can be added again later. There is no
auth, no queue, and no database server — it's one backend process, one static frontend, and one
file on disk.

## How it works

Three parts: a single-page React frontend, a FastAPI backend laid out as ports and adapters, and a
SQLite file. Enrichment runs as a FastAPI `BackgroundTask` after the create response is sent, going
out over `httpx` and then to whatever model `LLM_MODEL` names, through litellm.

See **[ARCHITECTURE.md](ARCHITECTURE.md)** for the full picture, which links on to
[`backend/ARCHITECTURE.md`](backend/ARCHITECTURE.md) and
[`frontend/ARCHITECTURE.md`](frontend/ARCHITECTURE.md) for the details of each side.

## Stack

- **Backend**: Python 3.14, FastAPI, SQLAlchemy 2 asyncio (aiosqlite), Pydantic v2, `uv`, pytest,
  ruff. Async all the way down.
- **Frontend**: React 19, TypeScript, Vite. Plain `fetch`, no data-fetching library.
- **Database**: SQLite, a single `bookmarks` table, schema managed with Alembic.
- **Containers**: separate dev (hot reload) and prod (nginx-served static build) Compose files.

## Running it

**Setup (once, mandatory):**

```bash
cp .env.example .env
# then edit .env: fill in the API key for your chosen model (GEMINI_API_KEY by default),
# and optionally set LLM_MODEL to use a different provider/model
```

`LLM_MODEL` takes any litellm-supported `provider/model` string (e.g. `openai/gpt-4o`,
`anthropic/claude-sonnet-5`) — set that provider's API key instead of `GEMINI_API_KEY`. The backend
validates this at startup and refuses to boot if the configured model's key is missing.

**Dev** — hot reload on both services:

```bash
docker compose up --build
```

- Backend: http://localhost:8000 (interactive API docs at `/docs`)
- Frontend: http://localhost:5173

**Prod** — nginx-served static frontend, no source mounts:

```bash
docker compose -f docker-compose.prod.yml up --build
```

- Backend: http://localhost:8000
- Frontend: http://localhost:80

### Data persistence

There is no database container. SQLite isn't a server process — it's a file the backend reads and
writes directly.

In dev, that file lives at `./data/bookmarks.db` on the host, bind-mounted into the container at
`/data`. You can open it directly with any SQLite client while the stack is running:

```bash
sqlite3 ./data/bookmarks.db
```

In prod, persistence instead comes from the named Docker volume `bookmarks_data`, mounted at
`/data`, since the prod image runs as a non-root user and a host bind mount would need matching
UIDs. It survives `docker compose down`; only `docker compose down -v` or `docker volume rm`
removes it. Dev and prod no longer share storage, so switching between modes doesn't risk the
"readonly database" error a shared volume used to cause.

### Running without Docker

```bash
cd backend
uv sync
GEMINI_API_KEY=... uv run uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev   # set VITE_API_URL if the backend isn't at http://localhost:8000
```

The root `.env` is only read by `docker compose` (it substitutes `${GEMINI_API_KEY}`, `${LLM_MODEL}`
and friends into the compose files); running these directly needs the variables exported in your
shell.

## Contributing

Checks before opening a PR:

```bash
cd backend && uv run pytest && uv run ruff check . && uv run ruff format --check .
cd frontend && npm run typecheck && npm run build
```

`frontend/src/types.ts` is a hand-maintained mirror of the backend's Pydantic schemas — nothing
fails at build time if the two drift, so changes to one need mirroring in the other.

## License

MIT — see [LICENSE](LICENSE).
