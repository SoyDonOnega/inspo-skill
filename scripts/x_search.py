#!/usr/bin/env python3
"""Search X through the xAI API's x_search tool (Responses API). Standard library only.

Prints JSON: {"answer": ..., "citations": [...], "usage": {...}}.
API key: $XAI_API_KEY, or the macOS Keychain item "xai-api-key".
Exit 2 = no key, exit 3 = API error (the skill then falls back).

Usage:
    python3 x_search.py "<what to look for>" [--from YYYY-MM-DD] [--to YYYY-MM-DD]
                        [--handles a,b] [--max 15]

Cost (xAI, 2026): $5 per 1,000 posts fetched + model tokens, billed by xAI.
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

ENDPOINT = "https://api.x.ai/v1/responses"
MODEL = os.environ.get("XAI_MODEL", "grok-4.7")

PROMPT = """Find X posts that are useful prior art or context for: {query}

Return up to {max} posts, best first. For each: author handle, date, one-line summary,
why it is useful, and the post URL (https://x.com/<handle>/status/<id>).
Prefer posts with demos, linked repos or docs, and credible practitioners.
Skip engagement bait, giveaways and reposts without substance.
Only list posts you actually retrieved; if none qualify, say so."""


def api_key():
    key = os.environ.get("XAI_API_KEY")
    if key:
        return key
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", "xai-api-key", "-w"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def build_request(args):
    tool = {"type": "x_search"}
    if args.date_from:
        tool["from_date"] = args.date_from
    if args.date_to:
        tool["to_date"] = args.date_to
    if args.handles:
        tool["allowed_x_handles"] = [h.strip().lstrip("@") for h in args.handles.split(",")][:20]
    return {
        "model": MODEL,
        "input": [{"role": "user", "content": PROMPT.format(query=args.query, max=args.max)}],
        "tools": [tool],
    }


def parse_response(data):
    """Collect answer text and every URL the response cites."""
    texts, citations = [], []
    for item in data.get("output", []):
        for part in item.get("content", []) or []:
            if part.get("type") == "output_text":
                texts.append(part.get("text", ""))
                for ann in part.get("annotations", []) or []:
                    url = ann.get("url")
                    if url and url not in citations:
                        citations.append(url)
    for url in data.get("citations", []) or []:
        url = url.get("url") if isinstance(url, dict) else url
        if url and url not in citations:
            citations.append(url)
    usage = data.get("usage", {})
    return {
        "answer": "\n".join(texts).strip(),
        "citations": citations,
        "usage": usage.get("server_side_tool_usage_details", usage),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("query")
    p.add_argument("--from", dest="date_from")
    p.add_argument("--to", dest="date_to")
    p.add_argument("--handles")
    p.add_argument("--max", type=int, default=15)
    args = p.parse_args()

    key = api_key()
    if not key:
        print(json.dumps({"error": "no xAI API key (set XAI_API_KEY or Keychain item 'xai-api-key')"}))
        return 2
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(build_request(args)).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        print(json.dumps({"error": f"HTTP {e.code}", "detail": e.read().decode(errors="replace")[:500]}))
        return 3
    except (urllib.error.URLError, TimeoutError) as e:
        print(json.dumps({"error": str(e)}))
        return 3
    print(json.dumps(parse_response(data), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
