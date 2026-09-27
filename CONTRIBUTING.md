# Contributing

See [RUNNING.md](RUNNING.md) to get the app running locally and [ARCHITECTURE.md](ARCHITECTURE.md)
for how it's put together.

## Stack

- **Backend**: Python 3.14, FastAPI, SQLAlchemy 2 asyncio (aiosqlite), Pydantic v2, `uv`, pytest,
  ruff. Async all the way down.
- **Frontend**: React 19, TypeScript, Vite. Plain `fetch`, no data-fetching library.
- **Database**: SQLite, a single `bookmarks` table, schema managed with Alembic.
- **Containers**: separate dev (hot reload) and prod (nginx-served static build) Compose files.

## Before opening a PR

```bash
cd backend && uv run pytest && uv run ruff check . && uv run ruff format --check .
cd frontend && npm run lint && npm run format:check && npm run typecheck && npm run test:run && npm run build
```

`frontend/src/types.ts` is a hand-maintained mirror of the backend's Pydantic schemas — nothing
fails at build time if the two drift, so changes to one need mirroring in the other.
