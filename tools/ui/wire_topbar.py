#!/usr/bin/env python3
"""Add the top bar, app icons and avatar attribution to index.html.

Idempotent: run it again any time index.html gets rewritten from elsewhere
and every hook is put back without duplicating anything. That file is edited
by other work too, so this script -- not a hand edit -- is how it gets wired.

Usage:  python3 tools/ui/wire_topbar.py [--check]
"""
from __future__ import annotations

import argparse
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
INDEX = os.path.join(ROOT, "hivemind", "templates", "index.html")

# Anchors are patterns, not exact strings: index.html is edited by other work
# too, and a tag picking up an attribute should not break the wiring.
CSS_ANCHOR = re.compile(r'<link\b[^>]*href="/static/app\.css"[^>]*>')
CSS_ADD = '<link rel="stylesheet" href="/static/ui/topbar.css">'
BODY_ANCHOR = re.compile(r"<body\b[^>]*>")
BODY_ADD = '\n    {% include "_topbar.html" %}'
JS_ANCHOR = re.compile(r'<script\b[^>]*src="/static/app\.js"[^>]*>\s*</script>')
JS_ADD = '<script src="/static/ui/topbar.js" defer></script>'
# The jar in the top bar is the mark now, so the emoji duplicate goes.
EMOJI = '<div class="mark" aria-hidden="true">\U0001f9e0</div>'

# Icons, manifest and social preview. og:image must be absolute -- nearly
# every scraper refuses a relative one -- and there is exactly one host.
SITE_URL = "https://hivemind.ahcomputing.com"
HEAD_SENTINEL = "<!-- hm-head -->"
HEAD_ADD = HEAD_SENTINEL + "".join([
    '<link rel="icon" href="/static/ui/icons/favicon.svg" type="image/svg+xml">',
    '<link rel="icon" href="/static/ui/icons/favicon-32.png" sizes="32x32" type="image/png">',
    '<link rel="icon" href="/static/ui/icons/favicon.ico" sizes="48x48">',
    '<link rel="apple-touch-icon" href="/static/ui/icons/apple-touch-icon.png">',
    '<link rel="manifest" href="/static/ui/manifest.json">',
    '<meta name="theme-color" content="#1b0f30">',
    '<meta property="og:type" content="website">',
    '<meta property="og:title" content="HiveMind \u2014 conference updates">',
    '<meta property="og:description" content="What\u2019s happening right now, '
    'shared by people here.">',
    f'<meta property="og:image" content="{SITE_URL}/static/ui/icons/og-image.png">',
    f'<meta property="og:url" content="{SITE_URL}/">',
    '<meta name="twitter:card" content="summary_large_image">',
])

# CC-BY is a licence obligation, not a nicety: self-hosting the artwork means
# we carry the attribution ourselves.
CREDIT_SENTINEL = 'class="credit"'
FOOTER_ANCHOR = re.compile(r"<footer\b[^>]*>")
CREDIT_ADD = (
    '<p class="credit">Robot avatars by '
    '<a href="https://robohash.org">RoboHash</a> (MIT), self-hosted. '
    'Classic robot set by Zikri Kader, '
    '<a href="https://creativecommons.org/licenses/by/3.0/">CC BY 3.0</a>.</p>'
)

# Wording that self-hosting makes untrue. Replacing a sentence is not safely
# idempotent, so this is only ever warned about, never rewritten.
STALE_CLAIMS = ("Robot avatars load from RoboHash",)


def wire(text: str) -> tuple[str, list[str]]:
    done: list[str] = []

    def insert_after(pattern: re.Pattern[str], addition: str, what: str) -> None:
        nonlocal text
        m = pattern.search(text)
        if not m:
            raise SystemExit(
                f"could not find an anchor for the {what} "
                f"(pattern: {pattern.pattern}) in {INDEX}"
            )
        text = text[:m.end()] + addition + text[m.end():]
        done.append(what)

    if HEAD_SENTINEL not in text:
        insert_after(CSS_ANCHOR, HEAD_ADD, "icons and manifest")
    if "/static/ui/topbar.css" not in text:
        insert_after(CSS_ANCHOR, CSS_ADD, "stylesheet")
    if "_topbar.html" not in text:
        insert_after(BODY_ANCHOR, BODY_ADD, "include")
    if "/static/ui/topbar.js" not in text:
        match = JS_ANCHOR.search(text)
        if not match:
            raise SystemExit(
                f"could not find an anchor for the script (pattern: {JS_ANCHOR.pattern}) in {INDEX}"
            )
        app_script = match.group()
        if "defer" not in app_script:
            app_script = app_script.replace("<script", "<script defer", 1)
        # Deferred scripts run in document order, so the top bar is ready
        # before app.js emits report-feed activity.
        text = text[:match.start()] + JS_ADD + app_script + text[match.end():]
        done.append("script")
    if CREDIT_SENTINEL not in text:
        insert_after(FOOTER_ANCHOR, CREDIT_ADD, "avatar attribution")
    if EMOJI in text:
        text = text.replace(EMOJI, "", 1)
        done.append("removed duplicate emoji mark")

    return text, done


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="report whether the hooks are present; do not write")
    args = ap.parse_args()

    with open(INDEX) as fh:
        original = fh.read()
    updated, done = wire(original)

    stale = [c for c in STALE_CLAIMS if c in original]
    for claim in stale:
        print(f"index.html: WARNING stale claim is back and needs rewriting by hand: {claim!r}")

    if args.check:
        print("index.html: wired" if not done else "index.html: MISSING " + ", ".join(done))
        sys.exit(0 if not done and not stale else 1)

    if not done:
        print("index.html: already wired, nothing to do")
        return
    with open(INDEX, "w") as fh:
        fh.write(updated)
    print("index.html: added " + ", ".join(done))


if __name__ == "__main__":
    main()
