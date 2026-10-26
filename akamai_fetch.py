#!/usr/bin/python3
"""
akamai_fetch.py — fetch pages and files through Akamai bot protection
by presenting your real installed Chrome as a human-driven browser.

Why this works
--------------
Akamai Bot Manager denies clients in three layers:
  1. TLS/HTTP2 fingerprint (curl, requests, urllib fail here instantly)
  2. A JS "sensor" that reads ~200 browser signals (headless browsers fail
     here — software rendering, webdriver flags, missing plugin objects)
  3. Per-request bot scoring (bad scores get a flat 403 or a JS challenge)

This tool sidesteps all three by driving your INSTALLED Google Chrome in
headed (rendered) mode with automation flags scrubbed, parked offscreen
so no window appears. To the sensor it is indistinguishable from a human
session, and every download rides Chrome's own network stack + cookies.

Requirements: pip install playwright && playwright install chrome
              (or just have Google Chrome installed; the tool uses
              channel="chrome" to target your real browser)

Usage
-----
  # Verify access to a protected page
  python3 akamai_fetch.py warmup --url https://example.com/protected/

  # Download a protected file
  python3 akamai_fetch.py download \
      --url https://example.com/big.zip \
      --warmup https://example.com/ \
      --out ./downloads/big.zip

  # Batch download from a manifest JSON: {"name": "https://..."}
  python3 akamai_fetch.py batch \
      --manifest manifest.json \
      --warmup https://example.com/ \
      --out ./downloads/
"""

import argparse
import json
import os
import sys

from playwright.sync_api import sync_playwright

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
"""

# Note: do NOT fake navigator.plugins with plain values — fingerprint
# checks read plugin entries' .name; wrong types read as more suspicious,
# not less. The three patches above cover the flags that matter.

DEFAULT_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--window-position=-32000,-32000",  # rendered, but off every monitor
    "--window-size=1440,900",
]


def launch(page_factory, warmup_url, headless=False, timeout_ms=45000):
    """Open Chrome (headed by default), warm the session, return (page, ctx)."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=headless,
            timeout=timeout_ms,
            args=DEFAULT_ARGS,
        )
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="en-US",
            timezone_id="America/New_York",
            accept_downloads=True,
        )
        page = ctx.new_page()
        page.add_init_script(STEALTH_JS)
        if warmup_url:
            r = page.goto(warmup_url, wait_until="domcontentloaded",
                          timeout=timeout_ms)
            print(f"[warmup] {r.status}  {page.title()[:70]}", flush=True)
            page.wait_for_timeout(3000)
        return page, browser


def cmd_warmup(args):
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=args.headless,
                                    timeout=45000, args=DEFAULT_ARGS)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900},
                                  locale="en-US", timezone_id="America/New_York")
        page = ctx.new_page()
        page.add_init_script(STEALTH_JS)
        r = page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)
        print(f"status : {r.status}")
        print(f"title  : {page.title()}")
        print(f"url    : {page.url}")
        print(f"cookies: {[c['name'] for c in ctx.cookies()]}")
        browser.close()


def cmd_download(args):
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=args.headless,
                                    timeout=45000, args=DEFAULT_ARGS)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900},
                                  locale="en-US", timezone_id="America/New_York",
                                  accept_downloads=True)
        page = ctx.new_page()
        page.add_init_script(STEALTH_JS)
        if args.warmup:
            r = page.goto(args.warmup, wait_until="domcontentloaded",
                          timeout=60000)
            print(f"[warmup] {r.status}  {page.title()[:70]}", flush=True)
            page.wait_for_timeout(3000)
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        print(f"[download] {args.url}", flush=True)
        with page.expect_download(timeout=args.timeout) as dl:
            page.evaluate(f"window.location.href = {args.url!r}")
        d = dl.value
        print(f"[saving] {d.suggested_filename}", flush=True)
        d.save_as(args.out)
        print(f"[done] {os.path.getsize(args.out)} bytes -> {args.out}")
        browser.close()


def cmd_batch(args):
    manifest = json.load(open(args.manifest))
    os.makedirs(args.out, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=args.headless,
                                    timeout=45000, args=DEFAULT_ARGS)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900},
                                  locale="en-US", timezone_id="America/New_York",
                                  accept_downloads=True)
        page = ctx.new_page()
        page.add_init_script(STEALTH_JS)
        warm = args.warmup or next(iter(manifest.values()))
        r = page.goto(warm, wait_until="domcontentloaded", timeout=60000)
        print(f"[warmup] {r.status}  {page.title()[:70]}", flush=True)
        page.wait_for_timeout(3000)
        for name, url in manifest.items():
            dest = os.path.join(args.out, f"{name}.zip")
            if os.path.exists(dest) and os.path.getsize(dest) > 100000:
                print(f"[skip] {name} (exists)", flush=True)
                continue
            print(f"[download] {name} <- {url}", flush=True)
            try:
                with page.expect_download(timeout=args.timeout) as dl:
                    page.evaluate(f"window.location.href = {url!r}")
                d = dl.value
                d.save_as(dest)
                print(f"[done] {name}: {os.path.getsize(dest)} bytes",
                      flush=True)
            except Exception as e:
                print(f"[fail] {name}: {type(e).__name__} {str(e)[:120]}",
                      flush=True)
            page.goto(warm, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1500)
        browser.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--headless", action="store_true",
                    help="run headless (WARNING: Akamai usually denies this)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_w = sub.add_parser("warmup", help="visit a page and report access")
    p_w.add_argument("--url", required=True)

    p_d = sub.add_parser("download", help="download a protected file")
    p_d.add_argument("--url", required=True)
    p_d.add_argument("--warmup", help="page to visit first to warm the session")
    p_d.add_argument("--out", required=True)
    p_d.add_argument("--timeout", type=int, default=240000,
                     help="max ms to wait for the download event")

    p_b = sub.add_parser("batch", help="batch download from a manifest JSON")
    p_b.add_argument("--manifest", required=True,
                     help='JSON file: {"filename_stem": "https://..."}')
    p_b.add_argument("--warmup", help="page to visit first (defaults to "
                                      "first manifest URL)")
    p_b.add_argument("--out", default="downloads")
    p_b.add_argument("--timeout", type=int, default=240000)

    args = ap.parse_args()
    if args.cmd == "warmup":
        cmd_warmup(args)
    elif args.cmd == "download":
        cmd_download(args)
    elif args.cmd == "batch":
        cmd_batch(args)


if __name__ == "__main__":
    main()
