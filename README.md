# scholar-browser

A small, containerized **agent browser for harvesting scholarly papers** (IACR ePrint, and
extensible to arXiv / Google Scholar). It runs a real Brave in a Neko/X11 container, driven by
a control extension over an HTTP bridge, with a no-password noVNC viewer and **xdotool-based
Cloudflare solving**. The point: fetch paper PDFs that plain HTTP can't (Cloudflare challenges,
login walls) by using a *real* browser an agent can drive.

## Why
Sites like ePrint put PDFs behind Cloudflare; `curl`/`fetch`/`XHR` get a `403` challenge page.
A real browser solves the challenge once (earning a `cf_clearance` cookie), after which an
in-page XHR can pull the bytes. Synthetic clicks are detected, so the challenge is solved with
**xdotool** (real X11 input following a human-like trajectory). See [docs/INSIGHTS.md](docs/INSIGHTS.md).

## Layout
```
container/   Dockerfile + compose: Neko/Brave, control extension (force-installed),
             ws-bridge, noVNC (x11vnc + websockify), xdotool
scholar/     eprint.py (search), harvest.py (bulk download + auto-CF-solve)
docs/        the hard-won gotchas
```

## Quickstart
```bash
cd container
NEKO_PASSWORD=... docker compose up -d --build      # builds + force-installs the extension

# Watch the screen (no password): http://<host>:8091/vnc.html?autoconnect=true
# Drive it via the bridge:
curl -s localhost:3000/api/bridge -d '{"tool":"navigate","args":["https://eprint.iacr.org/2024/100"]}'
curl -s localhost:3000/api/bridge -d '{"tool":"evaluate","args":["document.title"]}'

# Bulk harvest (broad ORAM search by default; edit QUERIES in harvest.py):
cd ../scholar && python3 harvest.py        # downloads PDFs into ./papers, writes oram-index.md
```

The harvester solves Cloudflare automatically via xdotool when `cf_clearance` expires
(set `ENVOY_CONTAINER` if your container name differs).

## Steerable dataset builder
Instead of a hardcoded harvest, grow a research-paper dataset you steer over time.

```bash
cd scholar
python3 add_topic.py "oblivious RAM" --source eprint --min-year 2023
python3 add_topic.py "private information retrieval" --source arxiv
python3 build_dataset.py            # harvest new papers for all topics, politely
```
- **`topics.jsonl`** — your steering log; each line `{q, source, min_year, note, added}`.
  Append anytime (via `add_topic.py` or by hand). Timestamps = a record of what you asked for, when.
- **`dataset/manifest.jsonl`** — provenance; each paper records the topic(s) that pulled it + date.
- **`dataset/papers/`** — the PDFs. Re-runs skip what's already there (resumable).
- **Sources:** `eprint` (Cloudflare-handled), `arxiv` (plain API), `gscholar` (best-effort; needs a
  logged-in session + slow pacing), `web` (DuckDuckGo, best-effort).

Run it on a schedule (e.g. every 6h via cron) and it quietly extends the dataset as you add topics.

## Notes
- The control extension under `container/extension/` is **minimal and purpose-built**: just
  `navigate` / `evaluate` / `screenshot`, polling the bridge. No CDP, no automation flags,
  no input synthesis (Cloudflare clicks are done with xdotool, not the extension).
- For remote access, tunnel the ports over SSH (`-L 8091:localhost:8091 -L 3000:localhost:3000`)
  — no need to expose them publicly.
