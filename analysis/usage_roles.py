#!/usr/bin/env python3
"""Split the tokens and the cost by the role of each session.

Input:  data/derived/api_responses.csv.gz (from usage.py),
        data/raw/*/t3/t3_pltrs.jsonl.gz
Output: results/usage/by_role.csv, results/usage/sessions.csv

Roles:
* human_thread: a T3 thread whose first message the author typed.
* delegated_thread: a T3 thread that an agent started (createdBy "agent"),
  for example with the T3 tool delegate_task or t3_thread_launch.
* native_subagent: a subagent of Claude Code (file under subagents/).
* no_t3_thread: a session that has no T3 thread (for example a headless
  "claude -p" run).
The column "purpose" is "paper" for threads about the paper (title has
"paper" or "scientific"), "estimate" for threads that only estimate cost or
progress, else "project".
"""
import collections
import csv
import gzip
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

FIELDS = ["input", "cache_write_5m", "cache_write_1h", "cache_read", "output"]


def purpose(title):
    t = (title or "").lower()
    if "paper" in t or "scientific" in t:
        return "paper"
    if any(w in t for w in ("cost", "token", "estimate", "progress", "completion est")):
        return "estimate"
    return "project"


def main():
    sess = {}
    for machine, tb in lib.load_t3().items():
        threads = {t["thread_id"]: t for t in tb.get("threads", [])}
        first = {}
        for m in sorted(tb.get("messages", []), key=lambda m: m["created_at"]):
            if m["role"] == "user" and m["thread_id"] not in first:
                first[m["thread_id"]] = m["payload"].get("createdBy")
        for pt in tb.get("provider_threads", []):
            ref = (pt["payload"].get("nativeThreadRef") or {}).get("nativeId")
            th = threads.get(pt["thread_id"])
            if ref and th:
                sess[ref] = {
                    "role": "human_thread" if first.get(th["thread_id"]) == "user" else "delegated_thread",
                    "title": th["title"],
                    "purpose": purpose(th["title"]),
                    "t3_machine": machine,
                }
    agg = collections.OrderedDict()
    with gzip.open(os.path.join(lib.DERIVED, "api_responses.csv.gz"), "rt") as f:
        for r in csv.DictReader(f):
            info = sess.get(r["session"], {"role": "no_t3_thread", "title": "", "purpose": "project"})
            role = "native_subagent" if r["is_subagent"] == "1" else info["role"]
            key = (r["machine"], r["session"], r["agent"] if r["is_subagent"] == "1" else "")
            a = agg.setdefault(key, {"machine": r["machine"], "session": r["session"], "agent": key[2],
                                     "role": role, "parent_role": info["role"], "purpose": info["purpose"],
                                     "title": info["title"], "first": r["timestamp"], "responses": 0,
                                     "cost_usd": 0.0, **{k: 0 for k in FIELDS}})
            a["responses"] += 1
            a["last"] = r["timestamp"]
            a["cost_usd"] += float(r["cost_usd"] or 0)
            for k in FIELDS:
                a[k] += int(r[k])
    rows = list(agg.values())
    for a in rows:
        a["cost_usd"] = round(a["cost_usd"], 2)
    cols = ["machine", "session", "agent", "role", "parent_role", "purpose", "title", "first", "last",
            "responses"] + FIELDS + ["cost_usd"]
    lib.write_csv(os.path.join(lib.RESULTS, "usage", "sessions.csv"), rows, cols)
    g = collections.OrderedDict()
    for a in rows:
        k = (a["role"], a["purpose"])
        x = g.setdefault(k, collections.Counter())
        x["sessions"] += 1
        x["responses"] += a["responses"]
        x["cost_usd"] += a["cost_usd"]
        for f in FIELDS:
            x[f] += a[f]
    out = [dict(role=k[0], purpose=k[1], **{kk: (round(v, 2) if kk == "cost_usd" else v) for kk, v in x.items()})
           for k, x in sorted(g.items(), key=lambda kv: -kv[1]["cost_usd"])]
    lib.write_csv(os.path.join(lib.RESULTS, "usage", "by_role.csv"), out,
                  ["role", "purpose", "sessions", "responses"] + FIELDS + ["cost_usd"])
    for r in out:
        print(r)


if __name__ == "__main__":
    main()
