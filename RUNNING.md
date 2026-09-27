# Running Bookmarks Archive

Everything you need to run the app beyond the quick start in the [README](README.md). For how it
works internally, see [ARCHITECTURE.md](ARCHITECTURE.md).

## What's in the box

A single-page React frontend, a FastAPI backend, and a SQLite file — one backend process, one
static frontend, one file on disk. Docker Compose files are provided for both dev (hot reload) and
prod (nginx-served static build). There is no auth: it's meant for a single user on a machine or
network they trust.

## Setup (once, mandatory)

```bash
cp .env.example .env
# then edit .env: fill in the API key for your chosen model (GEMINI_API_KEY by default),
# and optionally set LLM_MODEL to use a different provider/model
```

### Choosing a model

Bookmarks are enriched (description, tags, title) by an LLM called through litellm. `LLM_MODEL`
takes any litellm-supported `provider/model` string (e.g. `openai/gpt-4o`,
`anthropic/claude-sonnet-5`) — set that provider's API key instead of `GEMINI_API_KEY`. The backend
validates this at startup and refuses to boot if the configured model's key is missing.

OpenRouter works too, with the underlying model as a third segment — e.g.
`openrouter/anthropic/claude-sonnet-4.5`, with `OPENROUTER_API_KEY` set. Enrichment asks for
structured JSON output, so pick a model that supports it; ones that don't will fail every
enrichment rather than degrading.

## Dev

Hot reload on both services:

```bash
docker compose up --build
```

- Backend: http://localhost:8000 (interactive API docs at `/docs`)
- Frontend: http://localhost:5173

## Prod

nginx-served static frontend, no source mounts:

```bash
docker compose -f docker-compose.prod.yml up --build
```

- Backend: http://localhost:8000
- Frontend: http://localhost:80

## Your data

There is no database container. SQLite isn't a server process — it's a file the backend reads and
writes directly.

In dev, that file lives at `./data/bookmarks.db` on the host, bind-mounted into the container at
`/data`. You can open it directly with any SQLite client while the stack is running:

```bash
sqlite3 ./data/bookmarks.db
```

In prod, the database lives at `/srv/bookmarks-archive/data/bookmarks.db` on the host (set
`BOOKMARKS_DATA_DIR` to put it elsewhere), bind-mounted at `/data`. Create that directory before
the first start and give it to the non-root user the prod image runs as:

```bash
sudo mkdir -p /srv/bookmarks-archive/data && sudo chown -R 999:999 /srv/bookmarks-archive/data
```

Without that `chown` the backend fails with a "readonly database" error. The file is a plain path
on the host, so backups and `sqlite3` can reach it directly, and nothing in `docker compose down`
removes it.

## Running without Docker

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
