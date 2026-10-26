# inspo

Agent skill `/inspo`: prior art before building — similar GitHub repos, projects and X posts, with why and how each helps. Part of OneStack.

## What it does

Turns what you want to build or do into searches across GitHub (via `gh`), X posts, awesome lists, package registries and product sites, then returns a deduplicated list of useful references: type, cost, URL, why it helps, how it helps, best-practice signal. Free/OSS first; paid only on a very strong match. Every item has a real URL. It does not plan or implement.

## Usage

```text
/inspo I want a personal CRM that syncs Gmail and Calendar with local-first storage
```

Output (English): Intent → Solutions (one block each) → Gaps → Sources consulted.

## Install

From OneStack: `./sync-install.sh` — or copy this folder as `<skills dir>/inspo/`.

## Requirements

- `gh` CLI, authenticated (`gh auth login`).
- X search: pick one route.
  - **Script (free, default without a key once signed in):** `scripts/x_browse.py` runs X's own search in your installed Google Chrome through Playwright and prints the posts as JSON. No model calls. Needs [uv](https://docs.astral.sh/uv/). Sign in to X once in the plain Chrome window it opens (X refuses sign-in in an automated one), then quit that Chrome with Cmd+Q; the session stays in `~/.inspo/x-profile` (change it with `INSPO_X_PROFILE`):

    ```bash
    uv run scripts/x_browse.py --login
    ```

    It only reads and scrolls. Automated access to X may break X's terms; use it at low volume and at your own risk.
  - **Browser (free):** a browser the agent can drive (e.g. the Claude desktop app's built-in browser), signed in to X once by you. The skill only reads; it never posts, likes or follows.
  - **xAI API (paid, faster):** an xAI API key for `scripts/x_search.py`, stored once in the macOS Keychain:

    ```bash
    security add-generic-password -a "$USER" -s xai-api-key -w
    ```

    or exported as `XAI_API_KEY`. Cost: $5 per 1,000 posts fetched plus model tokens, billed by xAI. With a key set, this route runs by default.
  - Force a route per run: `/inspo --x api …`, `/inspo --x script …` or `/inspo --x browser …`. If the route fails, the skill tries the next one (API → script → browser → `site:x.com` web search) and says so. Posts from the API, browser and web routes are checked through the free FxTwitter API (`api.fxtwitter.com`).

## Layout

- `SKILL.md` — the skill.
- `scripts/x_search.py` — X search through the xAI API (standard library only).
- `scripts/x_browse.py` — X search through a local Chrome signed in to X (Playwright, run with uv).

## License

MIT — see `LICENSE`.
