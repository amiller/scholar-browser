#!/usr/bin/env python3
"""Steerable, multi-source research-paper dataset builder.

Reads steering inputs from topics.jsonl, harvests new papers per source, dedups against
manifest.jsonl, downloads PDFs politely. Designed to run on a schedule (e.g. every 6h).

  topics.jsonl   your steering log (append a line anytime) — what to gather
  manifest.jsonl provenance — every paper + which topic(s) pulled it + when
  dataset/papers/  the PDFs

Sources: eprint, arxiv, gscholar (Google Scholar), web. Browser-based sources use the
agent-browser bridge (+ xdotool Cloudflare solving); arxiv uses its plain HTTP API.
Env: DATASET_DIR, TOPICS_FILE, ENVOY_CONTAINER, DELAY.
"""
import os, re, json, time, base64, subprocess, random, urllib.request, urllib.parse
import eprint  # browser bridge: eprint.call(tool, *args) + eprint.search(q, n)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("DATASET_DIR", os.path.join(HERE, "dataset"))
PDFDIR = os.path.join(DATA, "papers")
MANIFEST = os.path.join(DATA, "manifest.jsonl")
TOPICS = os.environ.get("TOPICS_FILE", os.path.join(HERE, "topics.jsonl"))
C = os.environ.get("ENVOY_CONTAINER", "scholar-browser")
DELAY = float(os.environ.get("DELAY", "6"))
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

def today(): return time.strftime("%Y-%m-%d")
def load_jsonl(p):
    out = []
    if os.path.exists(p):
        for line in open(p):
            line = line.strip()
            if line:
                try: out.append(json.loads(line))
                except Exception: pass
    return out
def append_jsonl(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f: f.write(json.dumps(obj) + "\n")

# ---- browser helpers (eprint / gscholar / web) ----
def dex(*a): return subprocess.run(["docker","exec","-u","neko","-e","DISPLAY=:99.0",C,*a], capture_output=True, text=True)
def restart_brave(): subprocess.run(["docker","exec",C,"supervisorctl","restart","brave"], capture_output=True); time.sleep(15)
def b_nav(url): eprint.call("navigate", url, t=30)
def b_eval(js, t=30): return eprint.call("evaluate", js, t=t).get("result")
def b_xhr(url):
    js = ("(function(){try{var x=new XMLHttpRequest();x.open('GET','" + url + "',false);"
          "x.overrideMimeType('text/plain; charset=x-user-defined');x.send();"
          "if(x.status!==200)return 'ERR'+x.status;var s=x.responseText,b='';"
          "for(var i=0;i<s.length;i++)b+=String.fromCharCode(s.charCodeAt(i)&255);"
          "return btoa(b);}catch(e){return 'EXC'+e}})()")
    return b_eval(js, t=60)
def solve_cf(seed):
    b_nav(seed); time.sleep(6)
    js = ("(function(){var f=document.querySelector('iframe[src*=\"challenges.cloudflare.com\"]');"
          "var ch=window.outerHeight-window.innerHeight;"
          "if(!f)return JSON.stringify({found:false,ch:ch,W:window.innerWidth,H:window.innerHeight});"
          "var r=f.getBoundingClientRect();return JSON.stringify({found:true,x:r.x,y:r.y,w:r.width,h:r.height,ch:ch});})()")
    try: d = json.loads(b_eval(js, 20) or "{}")
    except Exception: d = {}
    ch = d.get("ch", 85)
    tx, ty = (int(d["x"]+28), int(d["y"]+d["h"]/2+ch)) if d.get("found") \
        else (int(d.get("W",1280)*0.30), int(d.get("H",900)*0.45+ch))
    sx, sy = random.randint(200,520), random.randint(140,320)
    for i in range(1, 25):
        t = i/24
        cx = int(sx+(tx-sx)*t+random.randint(-3,3)); cy = int(sy+(ty-sy)*t+int(28*(t*(1-t)))+random.randint(-3,3))
        dex("xdotool","mousemove",str(cx),str(cy)); time.sleep(0.012+random.random()*0.02)
    time.sleep(0.3); dex("xdotool","click","1"); time.sleep(7); restart_brave()
def browser_pdf(url, seed):
    for _ in range(3):
        b_nav(seed); time.sleep(1.2)
        r = b_xhr(url)
        if r and r.startswith("ERR429"): time.sleep(120); continue
        if r and r.startswith(("ERR403","ERR503")): solve_cf(seed); continue
        if not r or r.startswith(("ERR","EXC")): return None
        try: data = base64.b64decode(r)
        except Exception: return None
        return data if data[:4] == b"%PDF" else None
    return None

# ---- adapters: search(q, min_year) -> [paper]; download(paper) -> bytes|None ----
def eprint_search(q, min_year):
    out = []
    for p in eprint.search(q, 60):
        m = re.match(r"(\d{4})/", p["num"]); yr = int(m.group(1)) if m else 0
        if yr >= min_year:
            out.append({"id": p["num"], "source": "eprint", "title": p["title"], "authors": p["authors"],
                        "year": yr, "url": p["url"], "pdf_url": p["pdf"]})
    return out
def eprint_download(p): return browser_pdf(p["pdf_url"], p["url"])

def arxiv_search(q, min_year):
    url = ("http://export.arxiv.org/api/query?search_query=" + urllib.parse.quote("all:" + q) +
           "&start=0&max_results=40&sortBy=submittedDate&sortOrder=descending")
    try:
        xml = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30).read().decode()
    except Exception as e:
        print("[arxiv-err]", e); return []
    out = []
    for entry in re.findall(r"<entry>(.*?)</entry>", xml, re.S):
        def g(tag):
            m = re.search(r"<%s>(.*?)</%s>" % (tag, tag), entry, re.S)
            return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
        idu, title, pub = g("id"), g("title"), g("published")
        yr = int(pub[:4]) if pub[:4].isdigit() else 0
        aid = idu.rsplit("/abs/", 1)[-1]
        authors = ", ".join(re.findall(r"<name>(.*?)</name>", entry))
        if yr >= min_year:
            out.append({"id": aid, "source": "arxiv", "title": title, "authors": authors, "year": yr,
                        "url": idu, "pdf_url": "https://arxiv.org/pdf/" + aid})
    time.sleep(3)  # arxiv requests >=3s between API calls
    return out
def arxiv_download(p):
    try:
        data = urllib.request.urlopen(urllib.request.Request(p["pdf_url"], headers={"User-Agent": UA}), timeout=60).read()
        return data if data[:4] == b"%PDF" else None
    except Exception:
        return None

GS = (r'''(()=>{const cap=!!document.querySelector("#gs_captcha_ccl, form[action*=sorry], #recaptcha");'''
      r'''const rows=[...document.querySelectorAll(".gs_ri")].map(r=>({'''
      r'''title:((r.querySelector(".gs_rt")||{}).textContent||"").trim(),'''
      r'''info:((r.querySelector(".gs_a")||{}).textContent||"").trim(),'''
      r'''pdf:(r.closest(".gs_r")?.querySelector(".gs_or_ggsm a")||{}).href||""}));'''
      r'''return JSON.stringify({captcha:cap,rows});})()''')
def gscholar_search(q, min_year):
    b_nav("https://scholar.google.com/scholar?q=" + urllib.parse.quote(q) + "&as_ylo=" + str(min_year) + "&hl=en")
    time.sleep(4)
    try: d = json.loads(b_eval(GS, 30) or "{}")
    except Exception: d = {}
    if d.get("captcha"):
        print("[gscholar] blocked (captcha) — needs logged-in session + slow pacing; skipping"); return []
    out = []
    for r in d.get("rows", []):
        if not r.get("title"): continue
        out.append({"id": "gs:" + re.sub(r"\W+", "-", r["title"].lower())[:60], "source": "gscholar",
                    "title": r["title"], "authors": r.get("info", ""), "year": min_year,
                    "url": r.get("pdf", ""), "pdf_url": r.get("pdf", "")})
    return out
def gscholar_download(p):
    return browser_pdf(p["pdf_url"], p["pdf_url"]) if p.get("pdf_url") else None

def web_search(q, min_year):
    b_nav("https://duckduckgo.com/html/?q=" + urllib.parse.quote(q + " paper pdf")); time.sleep(3)
    js = r'''JSON.stringify([...document.querySelectorAll("a.result__a")].slice(0,15).map(a=>({title:a.textContent.trim(),url:a.href})))'''
    try: rows = json.loads(b_eval(js, 20) or "[]")
    except Exception: rows = []
    out = []
    for r in rows:
        u = r.get("url", "")
        out.append({"id": "web:" + re.sub(r"\W+", "-", (r.get("title", "") + u).lower())[:60], "source": "web",
                    "title": r.get("title", ""), "authors": "", "year": min_year,
                    "url": u, "pdf_url": u if u.lower().endswith(".pdf") else ""})
    return out
def web_download(p):
    return browser_pdf(p["pdf_url"], p["pdf_url"]) if p.get("pdf_url") else None

SOURCES = {"eprint": (eprint_search, eprint_download), "arxiv": (arxiv_search, arxiv_download),
           "gscholar": (gscholar_search, gscholar_download), "web": (web_search, web_download)}

def main():
    os.makedirs(PDFDIR, exist_ok=True)
    topics = load_jsonl(TOPICS)
    have = {(m["source"], m["id"]) for m in load_jsonl(MANIFEST)}
    print(f"[build] {len(topics)} topics, {len(have)} papers already in dataset", flush=True)
    added = 0
    for t in topics:
        src = t.get("source", "eprint"); q = t["q"]; min_year = int(t.get("min_year", 2020))
        if src not in SOURCES:
            print(f"[skip] unknown source: {src}", flush=True); continue
        search, download = SOURCES[src]
        print(f"[topic] [{src}] {q} (>= {min_year})", flush=True)
        try: results = search(q, min_year)
        except Exception as e:
            print(f"[search-err] {src} {q}: {e}", flush=True); continue
        for p in results:
            key = (p["source"], p["id"])
            if key in have: continue
            data = download(p)
            if not data:
                print(f"[miss] {src}:{p['id']} {p['title'][:50]}", flush=True); time.sleep(DELAY); continue
            fn = re.sub(r"[^\w.-]", "_", f"{p['source']}_{p['id']}") + ".pdf"
            open(os.path.join(PDFDIR, fn), "wb").write(data)
            append_jsonl(MANIFEST, {**p, "file": fn, "topics": [q], "added": today()})
            have.add(key); added += 1
            print(f"[+] {src}:{p['id']} {len(data)//1024}KB  {p['title'][:50]}", flush=True)
            time.sleep(DELAY + random.random() * 2)
    print(f"[done] added {added} new papers; dataset now {len(have)}", flush=True)

if __name__ == "__main__":
    main()
