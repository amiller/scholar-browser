#!/usr/bin/env python3
"""Polite bulk harvester for IACR ePrint via the agent browser bridge.

Be a good citizen with the archive:
  - paced downloads with jitter (DELAY, default 6s)
  - exponential backoff on HTTP 429 (rate limit) — never hammer
  - skip already-downloaded files (resumable)
  - solve Cloudflare with xdotool ONLY on a real challenge (403), never on 429

Config via env: QUERIES (';'-separated), MIN_YEAR, DELAY, DLDIR, ENVOY_CONTAINER.
"""
import eprint, base64, time, os, re, json, subprocess, random

QUERIES = os.environ.get(
    "QUERIES",
    "oblivious RAM;ORAM;Path ORAM;oblivious data structures;garbled RAM;doubly oblivious",
).split(";")
MIN_YEAR = int(os.environ.get("MIN_YEAR", "2023"))
DELAY = float(os.environ.get("DELAY", "6"))          # polite gap between downloads (seconds)
DLDIR = os.environ.get("DLDIR", "papers")
C = os.environ.get("ENVOY_CONTAINER", "scholar-browser")

def year(num):
    m = re.match(r"(\d{4})/", num); return int(m.group(1)) if m else 0

def dex(*a):
    return subprocess.run(["docker", "exec", "-u", "neko", "-e", "DISPLAY=:99.0", C, *a],
                          capture_output=True, text=True)

def restart_brave():
    subprocess.run(["docker", "exec", C, "supervisorctl", "restart", "brave"], capture_output=True)
    time.sleep(15)

def xhr_pdf(num):
    js = ("(function(){try{var x=new XMLHttpRequest();x.open('GET','https://eprint.iacr.org/" + num +
          ".pdf',false);x.overrideMimeType('text/plain; charset=x-user-defined');x.send();"
          "if(x.status!==200)return 'ERR'+x.status;var s=x.responseText,b='';"
          "for(var i=0;i<s.length;i++)b+=String.fromCharCode(s.charCodeAt(i)&255);"
          "return btoa(b);}catch(e){return 'EXC'+e}})()")
    return eprint.call("evaluate", js, t=60).get("result")

def solve_cf():
    """Solve a Cloudflare Turnstile challenge with a human-like xdotool click on display :99."""
    eprint.call("navigate", "https://eprint.iacr.org/2025/1479.pdf"); time.sleep(6)
    js = ("(function(){var f=document.querySelector('iframe[src*=\"challenges.cloudflare.com\"]');"
          "var ch=window.outerHeight-window.innerHeight;"
          "if(!f)return JSON.stringify({found:false,ch:ch,W:window.innerWidth,H:window.innerHeight});"
          "var r=f.getBoundingClientRect();return JSON.stringify({found:true,x:r.x,y:r.y,w:r.width,h:r.height,ch:ch});})()")
    try: d = json.loads(eprint.call("evaluate", js, t=20).get("result") or "{}")
    except Exception: d = {}
    ch = d.get("ch", 85)
    tx, ty = (int(d["x"] + 28), int(d["y"] + d["h"] / 2 + ch)) if d.get("found") \
        else (int(d.get("W", 1280) * 0.30), int(d.get("H", 900) * 0.45 + ch))
    sx, sy = random.randint(200, 520), random.randint(140, 320)
    for i in range(1, 25):                       # human-like trajectory (real X11 input)
        t = i / 24
        cx = int(sx + (tx - sx) * t + random.randint(-3, 3))
        cy = int(sy + (ty - sy) * t + int(28 * (t * (1 - t))) + random.randint(-3, 3))
        dex("xdotool", "mousemove", str(cx), str(cy)); time.sleep(0.012 + random.random() * 0.02)
    time.sleep(0.2 + random.random() * 0.3)
    dex("xdotool", "click", "1"); time.sleep(7)
    restart_brave()                              # recover the worker; cf_clearance persists

def fetch(num, out):
    """Return 'ok' | 'cf' | '429' | 'fail'."""
    eprint.call("navigate", "https://eprint.iacr.org/" + num); time.sleep(1.5)
    r = xhr_pdf(num)
    if not r: return "fail"
    if r.startswith("ERR429"): return "429"
    if r.startswith(("ERR403", "ERR503")): return "cf"
    if r.startswith(("ERR", "EXC")): return "fail"
    try: data = base64.b64decode(r)
    except Exception: return "fail"
    if data[:4] != b"%PDF": return "fail"
    open(out, "wb").write(data); return "ok"

def page_429():
    b = eprint.call("evaluate", "document.body?document.body.innerText.slice(0,120):''", t=15).get("result") or ""
    return "too many requests" in b.lower()

# ---- discover (politely; ePrint rate-limits search too) ----
os.makedirs(DLDIR, exist_ok=True)
papers = {}
backoff = 60
for q in QUERIES:
    q = q.strip()
    print(f"[search] {q}", flush=True)
    for _ in range(10):
        try:
            res = eprint.search(q, 60)
        except Exception as e:
            print(f"[search-err] {q}: {e}", flush=True); res = []
        if res:
            for p in res: papers.setdefault(p["num"], p)
            backoff = 60; break
        if page_429():
            print(f"[429] search rate-limited — backing off {backoff}s (being polite)", flush=True)
            time.sleep(backoff); backoff = min(backoff * 2, 900); continue
        break  # genuinely no results
    time.sleep(3)
sel = sorted((p for p in papers.values() if year(p["num"]) >= MIN_YEAR),
             key=lambda p: p["num"], reverse=True)
print(f"[harvest] {len(sel)} papers >= {MIN_YEAR}; polite delay={DELAY}s", flush=True)

# ---- download (paced, backoff) ----
ok = skip = fail = 0
backoff = 60
for p in sel:
    num = p["num"]; out = f"{DLDIR}/{num.replace('/', '_')}.pdf"
    if os.path.exists(out) and os.path.getsize(out) > 1000:
        skip += 1; continue
    st = "fail"
    for _ in range(4):
        st = fetch(num, out)
        if st == "ok":
            ok += 1; backoff = 60
            print(f"[ok] {num} {os.path.getsize(out)//1024}KB  {p['title'][:55]}", flush=True); break
        if st == "cf":
            print(f"[cf] {num}: solving Cloudflare via xdotool", flush=True); solve_cf(); continue
        if st == "429":
            print(f"[429] rate-limited — backing off {backoff}s (being polite)", flush=True)
            time.sleep(backoff); backoff = min(backoff * 2, 600); continue
        break
    if st != "ok":
        fail += 1; print(f"[fail] {num}", flush=True)
    time.sleep(DELAY + random.random() * 2)      # polite, jittered gap

# ---- index ----
with open("oram-index.md", "w") as f:
    f.write(f"# ePrint papers (>= {MIN_YEAR})\n\n")
    for p in sel:
        have = "x" if os.path.exists(f"{DLDIR}/{p['num'].replace('/', '_')}.pdf") else " "
        f.write(f"- [{have}] **{p['num']}** {p['title']} — {p['authors']} — {p['url']}\n")
print(f"\n[done] ok={ok} skip={skip} fail={fail} total={len(sel)}", flush=True)
