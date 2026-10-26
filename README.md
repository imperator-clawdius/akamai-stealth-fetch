# akamai-stealth-fetch

Fetch pages and files through Akamai bot protection by presenting your
**real, installed Chrome** as a human-driven browser.

No proxies, no patched TLS libraries, no solved challenge cookies. Just your
own browser, rendered for real, with the automation flags scrubbed — parked
offscreen so nothing pops on your screen.

## Why bots get denied

Akamai (Bot Manager / Kona Site Defender) sits in front of a large slice of
the web — war.gov, many .gov/.mil hosts, and plenty of commercial properties.
It filters clients in three layers:

1. **TLS / HTTP2 fingerprint (JA3/JA4).** Every client advertises a specific
   set of cipher suites, extensions, and HTTP/2 settings during the handshake.
   `curl`, `requests`, and `urllib` carry a *non-browser* stack — an instant
   bot signal, and the request dies with a flat `403 Access Denied` before
   any page logic ever runs.
2. **The JS sensor.** Akamai injects a script that samples ~200 browser
   signals — WebGL renderer string, font set, screen metrics, plugin objects,
   mouse/keyboard entropy — to judge whether a human is driving. **Headless
   browsers fail here**: software-GL renderer, `navigator.webdriver=true`,
   missing `window.chrome`, no behavioral noise. Headless Chromium gets
   denied *even with a genuine Chrome TLS stack*.
3. **Scoring + challenges.** Every request is scored. Bad scores earn a flat
   deny; middling ones earn a JavaScript puzzle that mints a tracking cookie.

## What this tool does

It runs your installed Google Chrome via Playwright in **headed mode —
but positioned at `(-32000, -32000)`, off every monitor** — with
`AutomationControlled` disabled and the `webdriver` flag scrubbed. The
browser renders for real, so the sensor sees exactly what it sees when a
human browses. A warm-up visit establishes the session; downloads then ride
Chrome's own network stack and cookies.

## Install

```bash
pip install playwright
playwright install chrome   # or just have Google Chrome installed
```

## Usage

```bash
# 1. Verify access to a protected page
python3 akamai_fetch.py warmup --url https://www.war.gov/UFO/

# 2. Download a protected file through the warmed session
python3 akamai_fetch.py download \
    --url https://www.war.gov/medialink/ufo/release-07/documents_release_07_oct_23_2026.zip \
    --warmup https://www.war.gov/UFO/ \
    --out ./release_07.zip

# 3. Batch download from a manifest
cat > manifest.json <<'EOF'
{"release_01": "https://www.war.gov/medialink/ufo/bundle/Release_1.zip",
 "release_02": "https://www.war.gov/medialink/ufo/052226/release_02/release_02_document_bundle.zip"}
EOF
python3 akamai_fetch.py batch --manifest manifest.json --out ./archive/
```

## Case study: the PURSUE UAP archive

The Department of War publishes declassified UAP records at `war.gov/UFO` —
public documents, explicitly released "for private-sector analysis" — behind
an Akamai edge that flatly denies curl and headless browsers. This tool
pulled the complete archive: all 7 releases, 298 PDFs, 5.1 GB, every bundle
integrity-verified. (The site's video bundles, incidentally, sit on
CloudFront with no bot protection at all — `curl` got them directly.)

## Pitfalls learned

- **Headless loses.** With `--headless`, the same stealth patches still get
  403 — the sensor catches the rendered-vs-not difference. Keep it headed;
  the offscreen trick keeps your desktop clean.
- **Don't fake `navigator.plugins` with plain values.** Fingerprint checks
  read plugin entries' `.name`; wrong object types read as *more* suspicious,
  not less. Only the `webdriver` / `chrome` / `languages` patches matter.
- **Stay in the session.** Don't warm up in Chrome and then switch to curl —
  curl's TLS fingerprint fails layer 1 regardless of any cookies you copied.
- **Check the mirrors first.** Akamai-protected hosts often mirror big
  binaries on CDNs that aren't bot-gated (CloudFront, dam.*.gov, NARA's
  catalog API). A minute of probing can save the whole fight.

## Responsible use

Bot detection is not access control. This tool does not bypass logins,
paywalls, rate limits, or authorization — it only makes an automated client
*look like the browser it legitimately drives*. Use it for archiving public
records, research, testing your own sites, and accessibility tooling. Respect
a site's terms of service and the law; never use it to access anything you
aren't authorized to access. When a site offers an official API, use it.

## License

MIT — see [LICENSE](LICENSE).
