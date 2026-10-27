#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright>=1.49"]
# ///
"""Search X through a local Chrome signed in to X (Playwright). Free, no API key.

Reads the posts X's own search page loads (its SearchTimeline response), with the
page's post cards as a fallback. Read only: it scrolls, never clicks, likes or posts.

Prints JSON: {"query": ..., "source": "network"|"dom", "posts": [...]}.
Session: a browser profile at $INSPO_X_PROFILE (default ~/.inspo/x-profile).
Exit 2 = not signed in (run --login), exit 3 = blocked or page changed (the skill then falls back).

Usage:
    uv run x_browse.py --login
    uv run x_browse.py "<terms>" [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--handles a,b]
                       [--min-faves N] [--mode top|live] [--max 15] [--headed]

Uses the installed Google Chrome; `--channel chromium` uses Playwright's own build
(`uv run --with playwright playwright install chromium` once).
"""
import argparse
import html
import json
import os
import random
import shutil
import subprocess
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

PROFILE = Path(os.environ.get("INSPO_X_PROFILE", "~/.inspo/x-profile")).expanduser()
LOGIN_TIMEOUT_S = 600


def signed_in(context):
    return any(c["name"] == "auth_token" for c in context.cookies("https://x.com"))


def build_query(args):
    q = [args.query]
    if args.date_from:
        q.append(f"since:{args.date_from}")
    if args.date_to:
        q.append(f"until:{args.date_to}")
    if args.handles:
        handles = [f"from:{h.strip().lstrip('@')}" for h in args.handles.split(",") if h.strip()]
        q.append("(" + " OR ".join(handles) + ")" if len(handles) > 1 else handles[0])
    if args.min_faves:
        q.append(f"min_faves:{args.min_faves}")
    return " ".join(q)


def find_tweets(node, out):
    """Collect tweet objects from a SearchTimeline payload without relying on its exact layout."""
    if isinstance(node, dict):
        legacy = node.get("legacy")
        if node.get("rest_id") and isinstance(legacy, dict) and "full_text" in legacy:
            out.append(node)
            return
        for v in node.values():
            find_tweets(v, out)
    elif isinstance(node, list):
        for v in node:
            find_tweets(v, out)


def screen_name(tweet):
    user = tweet.get("core", {}).get("user_results", {}).get("result", {})
    return user.get("core", {}).get("screen_name") or user.get("legacy", {}).get("screen_name")


def unwrap(result):
    """Posts with visibility limits come wrapped as {"__typename": "TweetWithVisibilityResults", "tweet": {...}}."""
    return result.get("tweet", result) if result.get("__typename") == "TweetWithVisibilityResults" else result


def post_text(tweet):
    """Full text without the t.co links that only point to the quoted post or the post's own article."""
    legacy = tweet["legacy"]
    note = tweet.get("note_tweet", {}).get("note_tweet_results", {}).get("result", {})
    text = note.get("text") or legacy["full_text"]
    drop = {legacy.get("quoted_status_permalink", {}).get("url")}
    drop |= {u["url"] for u in legacy.get("entities", {}).get("urls", []) if "/i/article/" in u.get("expanded_url", "")}
    for url in drop - {None}:
        text = text.replace(url, "")
    return html.unescape(text).strip()


def article(tweet):
    a = tweet.get("article", {}).get("article_results", {}).get("result", {})
    if not a.get("title"):
        return None
    return {"url": f"https://x.com/i/article/{a.get('rest_id')}", "title": a["title"], "preview": a.get("preview_text")}


def quoted(tweet):
    q = unwrap(tweet.get("quoted_status_result", {}).get("result", {}))
    if "legacy" not in q:
        return None
    handle = screen_name(q) or "i"
    out = {"url": f"https://x.com/{handle}/status/{q['rest_id']}", "handle": handle, "text": post_text(q)}
    if art := article(q):
        out["article"] = art
    return out


def to_post(tweet):
    legacy = tweet["legacy"]
    handle = screen_name(tweet) or "i"
    try:
        date = datetime.strptime(legacy["created_at"], "%a %b %d %H:%M:%S %z %Y").date().isoformat()
    except (KeyError, ValueError):
        date = None
    post = {
        "url": f"https://x.com/{handle}/status/{tweet['rest_id']}",
        "handle": handle,
        "date": date,
        "text": post_text(tweet),
        "likes": legacy.get("favorite_count"),
        "reposts": legacy.get("retweet_count"),
        "links": [u["expanded_url"] for u in legacy.get("entities", {}).get("urls", []) if u.get("expanded_url")],
    }
    if art := article(tweet):
        post["article"] = art
    if q := quoted(tweet):
        post["quoted"] = q
    return post


def dom_posts(page):
    posts = []
    for card in page.locator('article[data-testid="tweet"]').all():
        link = card.locator('a[href*="/status/"]:has(time)').first
        if not link.count():
            continue
        path = link.get_attribute("href").split("?")[0]
        text = card.locator('[data-testid="tweetText"]').first
        posts.append({
            "url": "https://x.com" + path,
            "handle": path.strip("/").split("/")[0],
            "date": (link.locator("time").get_attribute("datetime") or "")[:10] or None,
            "text": text.inner_text() if text.count() else "",
        })
    return posts


def launch(p, args, headless):
    PROFILE.mkdir(parents=True, exist_ok=True)
    kwargs = {"headless": headless, "viewport": {"width": 1280, "height": 900}}
    if args.channel != "chromium":
        kwargs["channel"] = args.channel
    return p.chromium.launch_persistent_context(str(PROFILE), **kwargs)


def browser_binary(p, args):
    if args.channel == "chromium":
        return p.chromium.executable_path
    mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    return mac if Path(mac).exists() else shutil.which("google-chrome")


def login(p, args):
    """Open a plain (not automated) browser on the profile: X refuses sign-in in an automated one."""
    PROFILE.mkdir(parents=True, exist_ok=True)
    binary = browser_binary(p, args)
    if not binary:
        print(json.dumps({"error": "Google Chrome not found; use --channel chromium"}))
        return 3
    # --use-mock-keychain matches what Playwright passes, so the saved cookies stay readable.
    cmd = [binary, f"--user-data-dir={PROFILE}", "--use-mock-keychain", "--no-first-run",
           "--no-default-browser-check", "https://x.com/login"]
    print("Sign in to X in the window that opened, then quit that browser (Cmd+Q).", file=sys.stderr)
    try:
        subprocess.run(cmd, timeout=LOGIN_TIMEOUT_S, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        pass
    context = launch(p, args, headless=True)
    ok = signed_in(context)
    context.close()
    if ok:
        print(json.dumps({"signed_in": True, "profile": str(PROFILE)}))
        return 0
    print(json.dumps({"error": "not signed in to X after the login window closed"}))
    return 2


def search(p, args):
    if not PROFILE.exists():
        print(json.dumps({"error": f"no X session at {PROFILE}; run x_browse.py --login"}))
        return 2
    context = launch(p, args, headless=not args.headed)
    page = context.pages[0] if context.pages else context.new_page()
    if not signed_in(context):
        context.close()
        print(json.dumps({"error": "not signed in to X; run x_browse.py --login"}))
        return 2

    tweets, responses = {}, []

    def on_response(resp):
        if "SearchTimeline" not in resp.url:
            return
        responses.append(resp.status)
        try:
            found = []
            find_tweets(resp.json(), found)
            for t in found:
                tweets.setdefault(t["rest_id"], t)
        except (PlaywrightError, ValueError):
            pass

    page.on("response", on_response)
    query = build_query(args)
    url = "https://x.com/search?" + urllib.parse.urlencode({"q": query, "src": "typed_query", "f": args.mode})
    try:
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        stale = 0
        while len(tweets) < args.max and stale < 3:
            before = len(tweets)
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(random.randint(1500, 2500))
            stale = stale + 1 if len(tweets) == before else 0
        source, posts = "network", [to_post(t) for t in tweets.values()]
        if not posts and not responses:
            source, posts = "dom", dom_posts(page)
    except PlaywrightError as e:
        context.close()
        print(json.dumps({"error": str(e).splitlines()[0]}))
        return 3
    context.close()

    if not posts and (not responses or any(s >= 400 for s in responses)):
        print(json.dumps({"error": "X returned no search results page (blocked, rate-limited or layout changed)",
                          "statuses": responses}))
        return 3
    print(json.dumps({"query": query, "source": source, "posts": posts[: args.max]}, ensure_ascii=False, indent=2))
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("query", nargs="?")
    p.add_argument("--login", action="store_true")
    p.add_argument("--from", dest="date_from")
    p.add_argument("--to", dest="date_to")
    p.add_argument("--handles")
    p.add_argument("--min-faves", type=int)
    p.add_argument("--mode", choices=["top", "live"], default="top")
    p.add_argument("--max", type=int, default=15)
    p.add_argument("--headed", action="store_true")
    p.add_argument("--channel", default="chrome")
    args = p.parse_args()
    if not args.login and not args.query:
        p.error("a query is required unless --login")

    with sync_playwright() as pw:
        return login(pw, args) if args.login else search(pw, args)


if __name__ == "__main__":
    sys.exit(main())
