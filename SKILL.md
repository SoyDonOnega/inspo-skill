---
name: inspo
description: >-
  Finds similar GitHub repos, projects and X posts as starting context for something the
  user wants to build or do, and explains why and how each one helps. Does not implement
  the idea. Use when the user runs /inspo <what they want to do>.
license: MIT
compatibility: Requires the gh CLI (authenticated) and network access. X search runs through the xAI API (paid, key required) or a browser signed in to X (free).
argument-hint: "[--x api|browser] <what you want to build or do>"
disable-model-invocation: true
---

# Inspo

**Slash-only.** Run only when the user explicitly invokes `/inspo`. Never
start from ambient mentions of inspiration, prior art, or similar ideas.

Given what the user wants to do, search for **similar real-world solutions**
(repos, projects, X posts) that are useful starting context and lean toward
best practice. Deliver a structured list — do not implement the idea.

Domain: **generic** — product, code, research workflow, tooling, content, ops.

Paths in this file are relative to the skill root (the folder that contains this SKILL.md).

## When invoked

1. Confirm this turn is a `/inspo` invoke. If not, do nothing with this skill.
2. Read the full user input after `/inspo` (or the attached brief). If empty,
   ask once what they want to do.
3. Extract intent: goal, constraints, stack hints, must-haves, nice-to-haves.
4. Search per **Source playbook** below. Prefer **breadth of useful matches**
   over a short curated top-N — include every find that adds real context;
   drop noise, duplicates, and dead ends.
5. Produce **only** the output template (English). Stop. Do not plan, design,
   or build unless the user asks in a later turn.

## Source playbook (search order)

Run independent searches in parallel. Record each kept item with a URL.

1. **GitHub repos** (always) — GitHub CLI, already authenticated:
   - `gh search repos "<terms>" --sort stars --limit 30 --json fullName,description,stargazersCount,pushedAt,license,url`
   - 2–4 queries with different wordings of the problem, not only buzzwords.
   - For the promising ones: `gh api repos/<owner>/<repo>/readme --jq .content | base64 -d | head -80`.
   - `gh search code "<terms>"` only when the useful thing is a pattern inside repos.
   - Prefer: clear README, pushed in the last 12 months, a license, matching problem shape. Stars are a weak signal only.
2. **X posts** (always) — two routes; the user picks one. Say in Sources which one ran.
   - **Pick the route:** `--x api` or `--x browser` at the start of the input forces one. Otherwise: an xAI key is set → `api`; no key → `browser`. If the chosen route fails, fall to the next one in this list and say so in Gaps.
   1. **`api`** (paid, fastest) — `python3 scripts/x_search.py "<what the user wants to do>" [--from YYYY-MM-DD] [--handles a,b]`. It calls the xAI API's `x_search` tool and returns post URLs. Cost: billed by xAI, not by the agent's own model provider. Exit 2 = no key, exit 3 = API error.
   2. **`browser`** (free) — open `https://x.com/search?q=<terms>&f=top` (`&f=live` for recent posts; X operators such as `since:`, `from:`, `min_faves:` work in `q`). Prefer a browser the agent owns (e.g. the Claude desktop app's built-in browser) over the user's own browser; use the user's browser only when no agent browser exists. Read page text, not screenshots. Read only: never like, post, follow or reply.
      - Not signed in → stop and ask the user to sign in to X in that browser once. Never type credentials.
   3. **`web`** (free, no login, last resort) — web search `site:x.com <terms>`. Weak coverage: say so in Gaps.
   - **Check each post before keeping it** (all routes): `curl -s https://api.fxtwitter.com/<handle>/status/<id>` returns the post as JSON (`.tweet.text`, `.tweet.author.screen_name`, `.tweet.likes`) — free, no account. Drop posts it cannot return.
   Keep posts with demos, linked repos or credible practitioners.
3. **Awesome lists / curated indexes** — `awesome-<topic>`, topic hubs (`gh search repos "awesome <topic>"`).
4. **Package ecosystems** when relevant — npm, PyPI, crates, Hugging Face (libraries/models as solutions, not only apps).
5. **Projects / products** — web search: Show HN, Product Hunt free tiers, "open source alternative to …", official docs of stacks the user already uses.
6. **Optional extras** only if they add context — GitLab/Codeberg, technical blogs with working examples. Skip low-signal Medium/listicle spam.

Also check the user's own notes (e.g. an Obsidian vault: project list, tool watchlist, bookmarks) for prior art they already filed, and cite as `vault:` paths when useful.

## Inclusion rules

- **Useful context** — keep an item if it clarifies approach, architecture,
  UX pattern, stack choice, or a pitfall to avoid.
- **Free by default** — OSS, free tiers, public posts. Include a **paid**
  product only when the match is **very strong** (near-identical problem +
  clear best-in-class fit); mark it `paid` and say why it clears the bar.
- **Best-practice bias** — prefer maintained, documented, widely adopted or
  clearly opinionated-good references over abandoned toys.
- **No invention** — every item needs a real URL (or vault path). If a search
  fails or tools are unavailable, say so in Gaps; do not fabricate links.
- **Deduplicate** — merge the same solution seen via repo + X + HN into one
  entry; note alternate links under Sources.

## Output language

All narrative fields (summaries, why it helps, how it helps) in **English**.
Keep proper nouns and titles as published.

## Output template

```markdown
## Intent (restated)
- …

## Solutions

### 1. <Name>
- Type: repo | project | x-post | package | vault | other
- Cost: free | paid (justify)
- URL: …
- Why it helps: …
- How it helps: …
- Best-practice signal: …

### 2. <Name>
- …

## Gaps
- Searches that failed, thin coverage, or angles with no good prior art

## Sources consulted
- Tool / query → notable hits (or none)
```

If nothing useful is found, keep the template and put a single bullet under
Solutions: `- None found that met the usefulness bar`.

## Anti-patterns

- Do not return a naked link dump without Why / How.
- Do not pad with weakly related “also popular” repos.
- Do not start implementing, scaffolding, or writing a build plan.
- Do not prefer paid SaaS when a free/OSS reference covers the same job.
