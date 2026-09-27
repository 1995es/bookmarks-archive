# Bookmarks Archive

[![CI](https://github.com/1995es/bookmarks-archive/actions/workflows/ci.yml/badge.svg)](https://github.com/1995es/bookmarks-archive/actions/workflows/ci.yml)

**Close those tabs. Keep the links.**

You know the drill: a dozen tabs left open "to read later", slowly piling up until the browser
crawls. Or a note titled *links* in whatever notes app you're using this year, full of bare URLs
you'll never recognise again. Neither is a place to *find* something — they're just places things
go to be forgotten.

Bookmarks Archive is a small, self-hosted place to put those links instead.

## How it helps

- **Saving takes a second.** Paste a URL and you're done — no title, no description, no tags
  required. Close the tab with a clear conscience.
- **It fills in the rest for you.** A few seconds later the bookmark has a proper title (if you
  didn't give one), a short description of what the page is about, and a set of tags — read and
  written by an LLM from the page itself. Anything you typed yourself is kept; the generated bits
  are added alongside.
- **You can find things again.** Filter by tag or by kind (post, video, tweet, site), sort, and
  page through your archive instead of scrolling a wall of URLs.
- **It's yours.** It runs on your own machine or server, and everything lives in a single SQLite
  file you can back up, copy, or open with any SQLite tool. No account, no sync service, no
  lock-in.

## Try it

You need Docker and an API key for an LLM provider (Gemini by default; OpenAI, Anthropic,
OpenRouter and others work too).

```bash
git clone https://github.com/1995es/bookmarks-archive.git
cd bookmarks-archive
cp .env.example .env        # then put your key in GEMINI_API_KEY
docker compose up --build
```

Open http://localhost:5173, paste the first link from that pile of tabs, and close the tab.

## Going further

- **[RUNNING.md](RUNNING.md)** — choosing a different model, the production setup, where your data
  lives and how to back it up, and running without Docker.
- **[ARCHITECTURE.md](ARCHITECTURE.md)** — how it works under the hood.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — the checks to run before opening a PR.

## License

MIT — see [LICENSE](LICENSE).
