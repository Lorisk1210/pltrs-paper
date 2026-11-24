#!/usr/bin/env python3
"""Compare the T3 token counts with the transcripts for each turn status.

Input:  data/raw/*/t3/t3_pltrs.jsonl.gz, data/derived/api_responses.csv.gz
        (run analysis/usage.py first)
Output: results/usage/t3_turn_check.json

Method:
* T3 Code stores the token count of the main agent for each turn
  ("turnTokenUsage") and the status of the turn (completed, failed,
  cancelled, interrupted).
* For each turn, the script adds the input tokens of the main-session
  responses in the transcript whose time is between the start and the end
  of the turn. The script finds the transcript through the Claude Code
  session id of the T3 thread.
* The script compares the two sums for each turn status.
"""
import collections
import csv
import gzip
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

INPUT = ("input", "cache_write_5m", "cache_write_1h", "cache_read")


def main():
    resp = collections.defaultdict(list)
    with gzip.open(os.path.join(lib.DERIVED, "api_responses.csv.gz"), "rt") as f:
        for r in csv.DictReader(f):
            if r["is_subagent"] == "0":
                resp[(r["machine"], r["session"])].append(
                    (r["timestamp"], sum(int(r[k]) for k in INPUT)))
    turns = collections.Counter()
    no_usage = collections.Counter()
    t3 = collections.Counter()
    transcript = collections.Counter()
    for machine, tables in lib.load_t3().items():
        sessions = {}
        for pt in tables.get("provider_threads", []):
            native = (pt["payload"].get("nativeThreadRef") or {}).get("nativeId")
            if native:
                sessions.setdefault(pt["thread_id"], set()).add(native)
        for t in tables.get("provider_turns", []):
            start, end = t["started_at"], t["completed_at"] or "9999"
            s = 0
            for native in sessions.get(t["thread_id"], ()):
                s += sum(x for ts, x in resp.get((machine, native), []) if start <= ts <= end)
            if not s:
                continue  # no transcript for this turn
            status = t["status"]
            usage = t["payload"].get("turnTokenUsage") or {}
            turns[status] += 1
            if not usage:
                no_usage[status] += 1
            t3[status] += usage.get("inputTokens") or 0
            transcript[status] += s
    out = {
        "note": "Input tokens (uncached input, cache writes and cache reads) of the main agent, "
                "for the turns that have responses in a transcript.",
        "by_status": {
            k: {"turns": turns[k], "turns_without_t3_usage": no_usage[k],
                "t3_input_tokens": t3[k], "transcript_input_tokens": transcript[k]}
            for k in sorted(turns)
        },
        "total": {"t3_input_tokens": sum(t3.values()),
                  "transcript_input_tokens": sum(transcript.values())},
    }
    path = os.path.join(lib.RESULTS, "usage", "t3_turn_check.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
