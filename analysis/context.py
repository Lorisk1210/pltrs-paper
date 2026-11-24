#!/usr/bin/env python3
"""Print one input of the author with its context, for the coding.

Usage: context.py H123 [--before 40] [--after 15] [--chars 600]

The output has two parts:
1. The record from data/derived/human_inputs.jsonl: the text, the thread
   and the T3 agent messages before and after the input.
2. If the input is linked to a Claude Code transcript, the records of the
   transcript before and after the input: agent text, tool calls with a
   short input, and tool results (shortened).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402


def short(s, n):
    s = (s or "").replace("\n", " ⏎ ")
    return s if len(s) <= n else s[:n] + " [...]"


def describe(d, n):
    t = d.get("type")
    ts = (d.get("timestamp") or "")[:19]
    out = []
    if t == "assistant":
        for b in d["message"].get("content") or []:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text" and b.get("text", "").strip():
                out.append("%s AGENT: %s" % (ts, short(b["text"], n * 2)))
            elif b.get("type") == "tool_use":
                out.append("%s TOOL %s: %s" % (ts, b.get("name"), short(json.dumps(b.get("input"), ensure_ascii=False), n)))
    elif t == "user":
        c = d["message"].get("content")
        if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
            for b in c:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    body = b.get("content")
                    if isinstance(body, list):
                        body = " ".join(x.get("text", "") for x in body if isinstance(x, dict))
                    out.append("%s RESULT: %s" % (ts, short(str(body), n)))
        else:
            out.append("%s PROMPT (%s): %s" % (ts, d.get("promptSource"), short(lib.text_of(c), n * 2)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("id")
    ap.add_argument("--before", type=int, default=40)
    ap.add_argument("--after", type=int, default=15)
    ap.add_argument("--chars", type=int, default=600)
    a = ap.parse_args()
    rec = None
    with open(os.path.join(lib.DERIVED, "human_inputs.jsonl"), encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["id"] == a.id:
                rec = r
                break
    if rec is None:
        sys.exit("unknown id " + a.id)
    print("=== INPUT", rec["id"], rec["kind"], rec["time"], rec["machine"])
    for k in ("thread_title", "thread_model", "thread_is_child", "is_first_in_thread"):
        if k in rec:
            print("%s: %s" % (k, rec[k]))
    print("\n--- TEXT\n" + (rec["text"] or ""))
    if rec.get("thread_first_message"):
        print("\n--- FIRST MESSAGE OF THREAD\n" + rec["thread_first_message"])
    for i, b in enumerate(rec.get("agent_before") or []):
        print("\n--- T3 AGENT MESSAGE BEFORE (%d of %d)\n%s" % (i + 1, len(rec["agent_before"]), b))
    if rec.get("agent_after"):
        print("\n--- T3 AGENT MESSAGE AFTER\n" + rec["agent_after"])
    links = rec.get("claude_links") or []
    if rec["kind"] in ("interrupt", "answer"):
        links = [{"file": rec["claude_file"], "uuid": rec["claude_uuid"]}]
    if not links:
        print("\n(no Claude Code transcript linked)")
        return
    link = links[0]
    path = os.path.join(lib.RAW, link["file"])
    lines = []
    hit = None
    for d in lib.records(path):
        if d.get("uuid") == link["uuid"]:
            hit = len(lines)
        lines.append(d)
        if hit is not None and len(lines) - hit > a.after * 3:
            break
    if hit is None:
        print("\n(uuid not found in transcript)")
        return
    print("\n=== TRANSCRIPT", link["file"])
    pre = []
    for d in lines[:hit]:
        pre.extend(describe(d, a.chars))
    for s in pre[-a.before:]:
        print(s)
    print(">>>>>> THE INPUT IS HERE")
    post = []
    for d in lines[hit + 1:]:
        post.extend(describe(d, a.chars))
    for s in post[:a.after]:
        print(s)


if __name__ == "__main__":
    main()
