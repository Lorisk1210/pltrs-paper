#!/usr/bin/env python3
"""Find the T3 threads that have no Claude Code transcript, and estimate their tokens.

Claude Code deletes transcripts after "cleanupPeriodDays" (default 30).
The Framework laptop and the Windows PC use the default. T3 Code keeps a
token count for each turn of the main agent ("turnTokenUsage"). This
script uses these counts for the threads without a transcript.

Input:  data/raw/*/t3/t3_pltrs.jsonl.gz, data/raw/*/claude/**.jsonl,
        data/derived/api_responses.csv.gz (from usage.py)
Output: results/usage/t3_threads.csv, results/usage/coverage.json

Method:
* T3 stores the Claude Code session id of each thread in the provider
  thread ("nativeThreadRef"). A T3 thread has a transcript if a file with
  this session id exists in data/raw. T3 threads of the type "subagent"
  show the native subagents of Claude Code. They have no own session, and
  their tokens are in the subagents/ files of the parent session.
* For threads with a transcript, the script compares the T3 token count
  with the count of the main agent in the transcript (no subagents).
* For threads without a transcript, the script calculates the cost from
  the T3 counts. T3 does not split cache writes into 5-minute and 1-hour
  writes, so the script gives a low value (all 5-minute) and a high value
  (all 1-hour).
"""
import collections
import csv
import gzip
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402


def main():
    prices = json.load(open(os.path.join(lib.ROOT, "analysis", "pricing.json")))["models"]
    files = {}
    for f in lib.claude_files():
        if not f["is_subagent"]:
            files.setdefault(f["session"], set()).add((f["machine"], f["session"]))

    claude_main = collections.defaultdict(collections.Counter)
    with gzip.open(os.path.join(lib.DERIVED, "api_responses.csv.gz"), "rt") as fh:
        for r in csv.DictReader(fh):
            if r["is_subagent"] == "1":
                continue
            a = claude_main[(r["machine"], r["session"])]
            a["all_input"] += sum(int(r[k]) for k in ("input", "cache_write_5m", "cache_write_1h", "cache_read"))
            a["output"] += int(r["output"])
            a["cost_usd"] += float(r["cost_usd"] or 0)

    rows = []
    for machine, tb in lib.load_t3().items():
        native = collections.defaultdict(set)
        for pt in tb.get("provider_threads", []):
            ref = (pt["payload"].get("nativeThreadRef") or {}).get("nativeId")
            if ref:
                native[pt["thread_id"]].add(ref)
        turns = collections.defaultdict(collections.Counter)
        for t in tb.get("provider_turns", []):
            u = t["payload"].get("turnTokenUsage") or {}
            a = turns[t["thread_id"]]
            a["turns"] += 1
            for k in ("inputTokens", "cachedInputTokens", "cacheCreationTokens", "outputTokens"):
                a[k] += u.get(k) or 0
        for th in tb.get("threads", []):
            tid = th["thread_id"]
            sessions = set()
            for ref in native.get(tid, ()):
                sessions |= files.get(ref, set())
            a = turns.get(tid, collections.Counter())
            model = (th["payload"].get("modelSelection") or {}).get("model")
            cached = a["cachedInputTokens"]
            created = a["cacheCreationTokens"]
            uncached = max(a["inputTokens"] - cached - created, 0)
            row = {
                "machine": machine,
                "thread": tid,
                "title": th["title"],
                "created": th["created_at"],
                "provider": th["default_provider"],
                "model": model,
                "is_child": int(bool((th["payload"].get("lineage") or {}).get("parentThreadId"))),
                "turns": a["turns"],
                "t3_all_input": a["inputTokens"],
                "t3_cache_read": cached,
                "t3_cache_write": created,
                "t3_uncached_input": uncached,
                "t3_output": a["outputTokens"],
                "native_sessions": ";".join(sorted(native.get(tid, ()))),
                "transcript_sessions": ";".join(sorted("%s/%s" % s for s in sessions)),
            }
            if sessions:
                c = collections.Counter()
                for s in sessions:
                    c.update(claude_main.get(s, {}))
                row["claude_main_all_input"] = c["all_input"]
                row["claude_main_output"] = c["output"]
            p = prices.get(model)
            if p and not sessions:
                base = uncached * p["input"] + cached * p["cache_read"] + a["outputTokens"] * p["output"]
                row["est_cost_low_usd"] = round((base + created * p["cache_write_5m"]) / 1e6, 2)
                row["est_cost_high_usd"] = round((base + created * p["cache_write_1h"]) / 1e6, 2)
            rows.append(row)
    rows.sort(key=lambda r: r["created"])
    fields = ["machine", "thread", "title", "created", "provider", "model", "is_child", "turns",
              "t3_all_input", "t3_cache_read", "t3_cache_write", "t3_uncached_input", "t3_output",
              "native_sessions", "transcript_sessions", "claude_main_all_input", "claude_main_output",
              "est_cost_low_usd", "est_cost_high_usd"]
    lib.write_csv(os.path.join(lib.RESULTS, "usage", "t3_threads.csv"), rows, fields)

    missing = [r for r in rows if not r["transcript_sessions"]]
    claude_missing = [r for r in missing if r["provider"] == "claudeAgent" and r["turns"] and r["native_sessions"]]
    no_native = [r for r in missing if r["provider"] == "claudeAgent" and not r["native_sessions"]]
    matched = [r for r in rows if r["transcript_sessions"] and r["provider"] == "claudeAgent"]
    out = {
        "t3_threads": len(rows),
        "threads_with_transcript": len(rows) - len(missing),
        "threads_without_transcript": len(missing),
        "claude_threads_without_transcript_with_turns": [
            {k: r.get(k) for k in ("machine", "title", "created", "turns", "t3_all_input", "t3_output",
                                    "est_cost_low_usd", "est_cost_high_usd")} for r in claude_missing],
        "claude_threads_without_native_session": len(no_native),
        "claude_threads_without_native_session_with_turns": sum(1 for r in no_native if r["turns"]),
        "missing_tokens_all_input": sum(r["t3_all_input"] for r in claude_missing),
        "missing_tokens_output": sum(r["t3_output"] for r in claude_missing),
        "missing_cost_low_usd": round(sum(r.get("est_cost_low_usd") or 0 for r in claude_missing), 2),
        "missing_cost_high_usd": round(sum(r.get("est_cost_high_usd") or 0 for r in claude_missing), 2),
        "check_matched_threads": {
            "threads": len(matched),
            "t3_all_input": sum(r["t3_all_input"] for r in matched),
            "claude_main_all_input": sum(r.get("claude_main_all_input") or 0 for r in matched),
            "t3_output": sum(r["t3_output"] for r in matched),
            "claude_main_output": sum(r.get("claude_main_output") or 0 for r in matched),
            "note": "Several T3 threads can share one Claude session (for example after a handoff), so this is a coarse check.",
        },
        "other_providers": [
            {k: r.get(k) for k in ("machine", "title", "provider", "model", "turns", "t3_all_input", "t3_output")}
            for r in rows if r["provider"] != "claudeAgent"],
    }
    with open(os.path.join(lib.RESULTS, "usage", "coverage.json"), "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(json.dumps(out, indent=2, ensure_ascii=False)[:5000])


if __name__ == "__main__":
    main()
