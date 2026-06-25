#!/usr/bin/env python3
"""eprint.py - search IACR ePrint through the Envoy/neko Brave bridge (no CDP).
Usage: eprint.py "query" [--limit N]
"""
import json, urllib.request, urllib.parse, sys, time, re, os

BRIDGE = os.environ.get("ENVOY_BRIDGE", "http://localhost:3000") + "/api/bridge"

def call(tool, *args, t=40):
    req = urllib.request.Request(BRIDGE, data=json.dumps({"tool": tool, "args": list(args)}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=t).read())

CATS = {"Applications","Cryptographic protocols","Foundations","Implementation",
        "Secret-key cryptography","Public-key cryptography","Attacks and cryptanalysis"}
NUMRE = re.compile(r"^(19|20)\d\d/\d+$")

def search(query, limit=25):
    call("navigate", "https://eprint.iacr.org/search?q=" + urllib.parse.quote(query))
    time.sleep(4)
    text = call("evaluate", "document.body.innerText").get("result") or ""
    i = text.find("results sorted")
    body = text[i:] if i >= 0 else text
    lines = [l.strip() for l in body.split("\n")]
    papers, cur = [], None
    for l in lines:
        if NUMRE.match(l):
            if cur: papers.append(cur)
            cur = {"num": l, "lines": []}
        elif cur is not None and l:
            cur["lines"].append(l)
    if cur: papers.append(cur)
    out = []
    for p in papers[:limit]:
        ls = [x for x in p["lines"] if x != "(PDF)" and not x.startswith("Last updated")
              and not x.startswith("Withdrawn") and not x.startswith("Revised")]
        title = ls[0] if ls else ""
        authors = ls[1] if len(ls) > 1 else ""
        cat = next((x for x in ls if x in CATS), "")
        out.append({"num": p["num"], "title": title, "authors": authors, "cat": cat,
                    "url": "https://eprint.iacr.org/" + p["num"],
                    "pdf": "https://eprint.iacr.org/" + p["num"] + ".pdf"})
    return out

if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "oblivious RAM"
    lim = int(sys.argv[sys.argv.index("--limit")+1]) if "--limit" in sys.argv else 25
    res = search(q, lim)
    for r in res:
        print(f"\n{r['num']}  [{r['cat']}]\n  {r['title']}\n  {r['authors']}\n  {r['url']}")
    print(f"\n{len(res)} results for: {q}")
