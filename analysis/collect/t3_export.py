#!/usr/bin/env python3
"""Export the pltrs threads from a T3 Code database.

Usage: t3_export.py <statev2.sqlite> <out.jsonl.gz>

The script opens the database read-only. It writes one JSON object per
line. Each object has a "table" key and the columns of one row. It keeps
only the rows of projects whose workspace root contains "plt-rs" or
"pltrs-icon", and their threads, messages, runs, provider turns and
subagents, and the provider threads (they hold the Claude Code session
id of each thread).
"""
import gzip
import json
import sqlite3
import sys

PATTERNS = ("plt-rs", "pltrs-icon")


def rows(con, sql, args=()):
    cur = con.execute(sql, args)
    names = [d[0] for d in cur.description]
    for r in cur:
        yield dict(zip(names, r))


def main(db, out):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    projects = [
        p for p in rows(con, "select * from projection_projects")
        if any(s in (p["workspace_root"] or "") for s in PATTERNS)
    ]
    pids = [p["project_id"] for p in projects]
    n = {}
    with gzip.open(out, "wt", encoding="utf-8") as f:
        def emit(table, row):
            row = dict(row, table=table)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n[table] = n.get(table, 0) + 1

        for p in projects:
            emit("projects", p)
        q = ",".join("?" * len(pids)) or "''"
        threads = list(rows(con, f"select * from orchestration_v2_projection_threads where project_id in ({q})", pids))
        for t in threads:
            emit("threads", t)
        tids = [t["thread_id"] for t in threads]
        for i in range(0, len(tids), 500):
            chunk = tids[i:i + 500]
            qq = ",".join("?" * len(chunk))
            for table, src in [
                ("messages", "orchestration_v2_projection_messages"),
                ("runs", "orchestration_v2_projection_runs"),
                ("provider_turns", "orchestration_v2_projection_provider_turns"),
                ("subagents", "orchestration_v2_projection_subagents"),
                ("provider_threads", "orchestration_v2_projection_provider_threads"),
            ]:
                for r in rows(con, f"select * from {src} where thread_id in ({qq})", chunk):
                    emit(table, r)
    print(json.dumps(n))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
