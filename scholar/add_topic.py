#!/usr/bin/env python3
"""Append a steering input to topics.jsonl (your steering log).

  add_topic.py "oblivious data structures" --source eprint --min-year 2023 --note "..."
  add_topic.py "differential privacy" --source arxiv
"""
import os, json, time, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("query")
ap.add_argument("--source", default="eprint", choices=["eprint", "arxiv", "gscholar", "web"])
ap.add_argument("--min-year", type=int, default=2023)
ap.add_argument("--note", default="")
a = ap.parse_args()

rec = {"q": a.query, "source": a.source, "min_year": a.min_year, "note": a.note,
       "added": time.strftime("%Y-%m-%d")}
with open(os.path.join(HERE, "topics.jsonl"), "a") as f:
    f.write(json.dumps(rec) + "\n")
print("added steering:", rec)
