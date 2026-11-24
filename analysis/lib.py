"""Shared loaders for the session data in data/raw.

The layout of data/raw is:

    data/raw/<machine>/claude/<project dir>/<session id>.jsonl
    data/raw/<machine>/claude/<project dir>/<session id>/subagents/agent-<id>.jsonl
    data/raw/<machine>/t3/t3_pltrs.jsonl.gz
    data/raw/<machine>/codex/rollout-*.jsonl

analysis/collect/README.md tells how the files were copied.
"""
import glob
import gzip
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
DERIVED = os.path.join(ROOT, "data", "derived")
RESULTS = os.path.join(ROOT, "results")
MACHINES = ["macbook", "ms02", "windows", "framework"]


def claude_files():
    """Yield one dict for each Claude Code transcript file."""
    for machine in MACHINES:
        base = os.path.join(RAW, machine, "claude")
        for path in sorted(glob.glob(os.path.join(base, "**", "*.jsonl"), recursive=True)):
            rel = os.path.relpath(path, base)
            parts = rel.split(os.sep)
            project = parts[0]
            sub = "subagents" in parts
            if sub:
                session = parts[1]
                agent = os.path.splitext(parts[-1])[0]
            else:
                session = os.path.splitext(parts[1])[0]
                agent = None
            yield {
                "machine": machine,
                "project": project,
                "path": path,
                "rel": os.path.join(machine, "claude", rel),
                "session": session,
                "is_subagent": sub,
                "agent": agent,
            }


def project_label(name):
    """Return a project directory name without the user part of the path."""
    return re.sub(r"^(?:-Users-[a-z0-9]+-|-home-[a-z0-9]+-|[A-Z]--Users-[a-z0-9]+-|[A-Z]--)-?", "", name)


def records(path):
    """Yield the JSON records of a JSONL file. Skip lines that do not parse."""
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def text_of(content):
    """Return the text blocks of a message content as one string."""
    if isinstance(content, str):
        return content
    out = []
    for b in content or []:
        if isinstance(b, dict) and b.get("type") == "text":
            out.append(b.get("text", ""))
    return "\n".join(out)


def load_t3():
    """Return {machine: {table: [rows]}} with the JSON payloads parsed."""
    out = {}
    for machine in MACHINES:
        path = os.path.join(RAW, machine, "t3", "t3_pltrs.jsonl.gz")
        if not os.path.exists(path):
            continue
        tables = {}
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                if "payload_json" in row:
                    row["payload"] = json.loads(row.pop("payload_json"))
                tables.setdefault(row["table"], []).append(row)
        out[machine] = tables
    return out


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def write_csv(path, rows, fields):
    import csv
    os.makedirs(os.path.dirname(path), exist_ok=True)
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "wt", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
