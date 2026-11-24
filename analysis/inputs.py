#!/usr/bin/env python3
"""Collect every input of the author, with the context around it.

Input:  data/raw/*/t3/t3_pltrs.jsonl.gz, data/raw/*/claude/**.jsonl
Output: data/derived/human_inputs.jsonl (one object per input, with context)
        data/derived/inputs_index.csv (one row per input, short text; private)
        data/derived/source_audit_full.json (private)
        results/inputs/source_audit.json (counts that show which messages
        the script kept and which it rejected)

Method:
* T3 Code stores each message with the field "createdBy". The value "user"
  marks text that a person typed in the T3 Code web or mobile client. The
  value "agent" marks text that an agent sent, for example a task for a
  child thread. The script keeps the "user" messages with the creation
  source "web" or "mobile". Messages with "createdBy" "user" and the
  creation source "server" are written by T3 Code itself (an automatic
  "Continue" or a relayed agent text). The script lists them in the audit
  and does not count them.
* The script checks that each prompt in the Claude Code transcripts that
  came from the SDK has a T3 message with the same text. Prompts without a
  match are listed in the audit.
* Two more kinds of input exist only in the Claude Code transcripts: the
  answers to an AskUserQuestion tool call, and "[Request interrupted by
  user]" records. The script adds them.
* For each message, the context is: the thread title, the first message of
  the thread, the last two agent messages before the input and the first
  agent message after it.
"""
import collections
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

BEFORE_CHARS = 3000
AFTER_CHARS = 2000
FIRST_CHARS = 1500


def _secs(ts):
    from datetime import datetime
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def tail(s, n):
    s = s or ""
    return s if len(s) <= n else "[...] " + s[-n:]


def head(s, n):
    s = s or ""
    return s if len(s) <= n else s[:n] + " [...]"


CASE_END = "2026-11-23T10:00:00Z"


def is_paper_thread(title):
    t = (title or "").lower()
    return "paper" in t or "scientific" in t


def main():
    t3 = lib.load_t3()
    audit = collections.Counter()
    rejected = []

    # Index of the Claude Code prompts, to link each input to its transcript.
    prompt_index = {}
    claude_prompts = []
    extra = []
    for f in lib.claude_files():
        for d in lib.records(f["path"]):
            if d.get("type") != "user":
                continue
            tur = d.get("toolUseResult")
            if isinstance(tur, dict) and "answers" in tur:
                extra.append({
                    "kind": "answer",
                    "machine": f["machine"],
                    "time": d.get("timestamp"),
                    "text": json.dumps(tur.get("answers"), ensure_ascii=False),
                    "questions": tur.get("questions"),
                    "claude_file": f["rel"],
                    "claude_uuid": d.get("uuid"),
                    "session": f["session"],
                })
                continue
            if tur is not None:
                continue
            text = lib.text_of(d["message"].get("content"))
            if text.strip() == "[Request interrupted by user]":
                extra.append({
                    "kind": "interrupt",
                    "machine": f["machine"],
                    "time": d.get("timestamp"),
                    "text": text,
                    "claude_file": f["rel"],
                    "claude_uuid": d.get("uuid"),
                    "session": f["session"],
                    "is_subagent": f["is_subagent"],
                })
                continue
            if d.get("promptSource") == "sdk" and not f["is_subagent"]:
                key = lib.norm(text)[:400]
                prompt_index.setdefault(key, []).append((f["rel"], d.get("uuid"), d.get("timestamp")))
                claude_prompts.append((key, f, d.get("timestamp"), text))

    # T3 messages of all machines.
    t3_keys = {}
    inputs = []
    seen = set()
    for machine, tb in t3.items():
        threads = {t["thread_id"]: t for t in tb.get("threads", [])}
        by_thread = collections.defaultdict(list)
        for m in tb.get("messages", []):
            by_thread[m["thread_id"]].append(m)
        for msgs in by_thread.values():
            msgs.sort(key=lambda m: (m["created_at"], m["message_id"]))
        for tid, msgs in by_thread.items():
            th = threads.get(tid)
            tp = th["payload"] if th else {}
            first = next((m for m in msgs if m["role"] == "user"), None)
            for i, m in enumerate(msgs):
                p = m["payload"]
                if m["role"] != "user":
                    continue
                text = p.get("text") or ""
                key = lib.norm(text)[:400]
                t3_keys.setdefault(key, set()).add(p.get("createdBy"))
                if p.get("createdBy") != "user":
                    audit["t3_user_role_by_agent"] += 1
                    continue
                if p.get("creationSource") not in ("web", "mobile"):
                    audit["t3_by_user_but_source_" + str(p.get("creationSource"))] += 1
                    rejected.append({"machine": machine, "thread": tid, "time": m["created_at"],
                                     "source": p.get("creationSource"), "text": head(text, 300)})
                    continue
                if m["message_id"] in seen:
                    audit["duplicate_message_id"] += 1
                    continue
                seen.add(m["message_id"])
                before = [x for x in msgs[:i] if x["role"] == "assistant" and (x["payload"].get("text") or "").strip()]
                after = next((x for x in msgs[i + 1:] if x["role"] == "assistant" and (x["payload"].get("text") or "").strip()), None)
                # Short texts such as "continue" occur in many sessions. Keep
                # the transcript prompts within 10 minutes of the T3 message,
                # nearest first.
                links = sorted(
                    (l for l in prompt_index.get(key, []) if l[2] and abs(_secs(l[2]) - _secs(m["created_at"])) < 600),
                    key=lambda l: abs(_secs(l[2]) - _secs(m["created_at"])))
                inputs.append({
                    "kind": "message",
                    "machine": machine,
                    "source": p.get("creationSource"),
                    "thread": tid,
                    "thread_title": th["title"] if th else None,
                    "thread_provider": th["default_provider"] if th else None,
                    "thread_model": (tp.get("modelSelection") or {}).get("model"),
                    "thread_is_child": bool((tp.get("lineage") or {}).get("parentThreadId")),
                    "thread_created": th["created_at"] if th else None,
                    "message_id": m["message_id"],
                    "time": m["created_at"],
                    "text": text,
                    "attachments": len(p.get("attachments") or []),
                    "is_first_in_thread": first is m,
                    "thread_first_message": None if first is m else head(first["payload"].get("text") if first else "", FIRST_CHARS),
                    "agent_before": [tail(x["payload"].get("text"), BEFORE_CHARS) for x in before[-2:]],
                    "agent_before_time": before[-1]["created_at"] if before else None,
                    "agent_after": head(after["payload"].get("text"), AFTER_CHARS) if after else None,
                    "claude_links": [{"file": a, "uuid": b, "time": c} for a, b, c in links],
                })

    # Check: every SDK prompt in the transcripts must have a T3 message.
    unmatched = []
    for key, f, ts, text in claude_prompts:
        hit = t3_keys.get(key)
        if hit is None:
            hit = next((v for k, v in t3_keys.items() if k and (key.startswith(k[:200]) or k.startswith(key[:200]))), None)
        if hit is None:
            unmatched.append({"file": f["rel"], "time": ts, "text": head(text, 300)})
            audit["claude_prompt_without_t3_message"] += 1
        elif "user" in hit:
            audit["claude_prompt_matches_user_message"] += 1
        else:
            audit["claude_prompt_matches_agent_message"] += 1

    # Interrupts that a sub-agent receives are relayed by its parent, not typed.
    # A resumed session copies earlier records, so the same uuid can be in two files.
    seen_uuid = set()
    for e in extra:
        if e["kind"] == "interrupt" and e.get("is_subagent"):
            audit["interrupt_in_subagent_skipped"] += 1
            continue
        if e["claude_uuid"] in seen_uuid:
            audit[e["kind"] + "_copy_skipped"] += 1
            continue
        seen_uuid.add(e["claude_uuid"])
        inputs.append(e)

    inputs.sort(key=lambda r: r["time"] or "")
    for n, r in enumerate(inputs, 1):
        r["id"] = "H%03d" % n
    # Threads of other providers (Cursor, Codex, Antigravity) only answered
    # questions about cost or progress. Their inputs are not part of the
    # analysis. The script removes them after the numbering, so that the
    # ids of the coded inputs stay the same.
    other = [r for r in inputs if r.get("thread_provider") not in (None, "claudeAgent")]
    audit["other_provider_excluded"] = len(other)
    inputs = [r for r in inputs if r not in other]
    # Two threads are about the paper on pltrs, not about pltrs. Their
    # inputs are not input to the project.
    paper = [r for r in inputs if is_paper_thread(r.get("thread_title"))]
    audit["paper_thread_excluded"] = len(paper)
    inputs = [r for r in inputs if r not in paper]
    # The case ends when release 0.1.1 is complete. The last release step is
    # the upload to crates.io on 23 November 2026 (input at 08:29 UTC). The
    # later inputs in the project threads are about a writing tool of the
    # author, not about pltrs.
    late = [r for r in inputs if (r["time"] or "") > CASE_END]
    audit["after_case_end_excluded"] = len(late)
    inputs = [r for r in inputs if r not in late]
    os.makedirs(lib.DERIVED, exist_ok=True)
    with open(os.path.join(lib.DERIVED, "human_inputs.jsonl"), "w", encoding="utf-8") as f:
        for r in inputs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    rd = os.path.join(lib.RESULTS, "inputs")
    os.makedirs(rd, exist_ok=True)
    # The index and the full audit have message texts and paths, so they stay private.
    with open(os.path.join(lib.DERIVED, "inputs_index.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "kind", "time", "machine", "source", "thread_title", "words", "text_start"])
        for r in inputs:
            w.writerow([r["id"], r["kind"], r["time"], r["machine"], r.get("source", ""), r.get("thread_title") or "",
                        len((r["text"] or "").split()), lib.norm(r["text"])[:160]])
    counts = collections.Counter((r["kind"], r["machine"]) for r in inputs)
    out = {
        "inputs": len(inputs),
        "by_kind_machine": {"%s/%s" % k: v for k, v in sorted(counts.items())},
        "audit": dict(audit),
        "rejected_t3_messages": rejected,
        "claude_prompts_without_t3_message": unmatched,
    }
    with open(os.path.join(lib.DERIVED, "source_audit_full.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    public = {k: out[k] for k in ("inputs", "by_kind_machine", "audit")}
    public["note"] = "Counts only. The texts of the rejected and unmatched messages are in data/derived/source_audit_full.json (private)."
    with open(os.path.join(rd, "source_audit.json"), "w", encoding="utf-8") as f:
        json.dump(public, f, indent=2, ensure_ascii=False)
    print(json.dumps({k: out[k] for k in ("inputs", "by_kind_machine", "audit")}, indent=2))


if __name__ == "__main__":
    main()
