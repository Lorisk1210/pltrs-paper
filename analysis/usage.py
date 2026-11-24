#!/usr/bin/env python3
"""Count the tokens of all model requests and calculate the API cost.

Input:  data/raw/*/claude/**.jsonl, data/raw/*/t3/t3_pltrs.jsonl.gz,
        analysis/pricing.json
Output: data/derived/api_responses.csv.gz (one row per model response)
        results/usage/*.csv and results/usage/summary.json

Method:
* Each assistant record in a Claude Code transcript has the "usage" object
  of the API response. Claude Code writes one record for each content
  block, so one response can have several records with the same
  message.id. A resumed or forked session also copies earlier records
  into a new file. The script keeps one row for each message.id over all
  files and machines.
* Records with the model "<synthetic>" are local error messages of Claude
  Code. They have no API request, and the script ignores them.
* The cost of a response is the sum of the token counts multiplied by the
  prices in analysis/pricing.json.
* As a cross-check, the script reads the "cost-state" records that newer
  Claude Code versions write. Each has the cost that Claude Code
  calculated for one process.
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

FIELDS = ["input", "cache_write_5m", "cache_write_1h", "cache_read", "output"]


def price_of(row, prices):
    model = row["model"]
    if model == "claude-haiku-5-5":
        prompt = row["input"] + row["cache_write_5m"] + row["cache_write_1h"] + row["cache_read"]
        if prompt > 100_000:
            model = "claude-haiku-5-5>100k"
    p = prices["models"].get(model)
    if p is None:
        return None
    mult = 2.0 if row.get("speed") == "fast" else 1.0
    if row.get("inference_geo") == "us":
        mult *= 1.1
    return mult * sum(row[k] * p[k] for k in FIELDS) / 1e6


def main():
    prices = json.load(open(os.path.join(lib.ROOT, "analysis", "pricing.json")))
    rows = {}
    copies = collections.Counter()
    cost_state = {}
    files = 0
    for f in lib.claude_files():
        files += 1
        for d in lib.records(f["path"]):
            t = d.get("type")
            if t == "cost-state":
                key = (f["machine"], d.get("sessionId"), d.get("startTime"))
                cost_state[key] = d
                continue
            if t != "assistant":
                continue
            msg = d.get("message") or {}
            model = msg.get("model")
            u = msg.get("usage")
            if not u or model == "<synthetic>":
                continue
            mid = msg.get("id") or d.get("requestId") or d.get("uuid")
            cc = u.get("cache_creation") or {}
            w1h = cc.get("ephemeral_1h_input_tokens")
            w5m = cc.get("ephemeral_5m_input_tokens")
            total_w = u.get("cache_creation_input_tokens") or 0
            if w1h is None and w5m is None:
                w5m, w1h = total_w, 0
            row = {
                "message_id": mid,
                "machine": f["machine"],
                "project": lib.project_label(f["project"]),
                "session": f["session"],
                "agent": f["agent"] or "",
                "is_subagent": int(f["is_subagent"] or bool(d.get("isSidechain"))),
                "file": f["rel"],  # private: data/derived only
                "timestamp": d.get("timestamp", ""),
                "model": model,
                "entrypoint": d.get("entrypoint", ""),
                "speed": u.get("speed") or "",
                "service_tier": u.get("service_tier") or "",
                "inference_geo": u.get("inference_geo") or "",
                "input": u.get("input_tokens") or 0,
                "cache_write_5m": w5m or 0,
                "cache_write_1h": w1h or 0,
                "cache_read": u.get("cache_read_input_tokens") or 0,
                "output": u.get("output_tokens") or 0,
                "thinking": (u.get("output_tokens_details") or {}).get("thinking_tokens") or 0,
                "web_search": (u.get("server_tool_use") or {}).get("web_search_requests") or 0,
            }
            old = rows.get(mid)
            if old is None:
                rows[mid] = row
            else:
                if old["file"] != row["file"]:
                    copies[mid] += 1
                # Later records of the same response can have a higher output count.
                for k in FIELDS + ["thinking"]:
                    old[k] = max(old[k], row[k])
    out = list(rows.values())
    for r in out:
        r["day"] = r["timestamp"][:10]
        r["cost_usd"] = price_of(r, prices)
    out.sort(key=lambda r: r["timestamp"])
    fields = ["message_id", "machine", "project", "session", "agent", "is_subagent", "file",
              "timestamp", "day", "model", "entrypoint", "speed", "service_tier", "inference_geo"] \
        + FIELDS + ["thinking", "web_search", "cost_usd"]
    lib.write_csv(os.path.join(lib.DERIVED, "api_responses.csv.gz"), out, fields)

    def group(keyf):
        g = collections.OrderedDict()
        for r in out:
            k = keyf(r)
            a = g.setdefault(k, collections.Counter())
            a["responses"] += 1
            for x in FIELDS + ["thinking", "web_search"]:
                a[x] += r[x]
            a["cost_usd"] += r["cost_usd"] or 0
        res = []
        for k, a in g.items():
            row = dict(zip(keyf.names, k)) if isinstance(k, tuple) else {keyf.names[0]: k}
            row.update(a)
            row["all_input"] = a["input"] + a["cache_write_5m"] + a["cache_write_1h"] + a["cache_read"]
            row["cost_usd"] = round(a["cost_usd"], 2)
            res.append(row)
        return res

    def key(*names):
        def f(r):
            return tuple(r[n] for n in names)
        f.names = names
        return f

    cols = ["responses"] + FIELDS + ["all_input", "thinking", "web_search", "cost_usd"]
    rd = os.path.join(lib.RESULTS, "usage")
    tables = {
        "by_machine": ("machine",),
        "by_model": ("model",),
        "by_machine_model": ("machine", "model"),
        "by_day": ("day",),
        "by_day_model": ("day", "model"),
        "main_vs_subagent": ("is_subagent",),
        "by_session": ("machine", "project", "session"),
    }
    for name, names in tables.items():
        res = group(key(*names))
        if name == "by_session":
            res.sort(key=lambda r: -r["cost_usd"])
        lib.write_csv(os.path.join(rd, name + ".csv"), res, list(names) + cols)
    total = group(key("all"))[0] if False else None
    tot = collections.Counter()
    for r in out:
        for x in FIELDS + ["thinking", "web_search"]:
            tot[x] += r[x]
        tot["cost_usd"] += r["cost_usd"] or 0
    tot["responses"] = len(out)

    # Cross-check with the cost-state records of Claude Code.
    cs = collections.Counter()
    cs_models = collections.defaultdict(collections.Counter)
    for d in cost_state.values():
        cs["processes"] += 1
        cs["cost_usd"] += d.get("totalCostUSD") or 0
        for m, mu in (d.get("modelUsage") or {}).items():
            for k, v in mu.items():
                if isinstance(v, (int, float)):
                    cs_models[m][k] += v
    sessions_with_cs = {(m, s) for (m, s, _) in cost_state}
    bottom_up_same = sum(r["cost_usd"] or 0 for r in out if (r["machine"], r["session"]) in sessions_with_cs)

    summary = {
        "transcript_files": files,
        "unique_responses": len(out),
        "responses_copied_into_other_files": len(copies),
        "first_response": out[0]["timestamp"] if out else None,
        "last_response": out[-1]["timestamp"] if out else None,
        "totals": dict(tot),
        "speed_values": dict(collections.Counter(r["speed"] for r in out)),
        "inference_geo_values": dict(collections.Counter(r["inference_geo"] for r in out)),
        "service_tier_values": dict(collections.Counter(r["service_tier"] for r in out)),
        "cross_check_cost_state": {
            "note": "cost-state records exist only in newer Claude Code versions. Compare with the bottom-up cost of the same sessions.",
            "processes": cs["processes"],
            "sessions": len(sessions_with_cs),
            "claude_code_cost_usd": round(cs["cost_usd"], 2),
            "bottom_up_cost_same_sessions_usd": round(bottom_up_same, 2),
            "model_usage": {m: dict(v) for m, v in cs_models.items()},
        },
    }
    os.makedirs(rd, exist_ok=True)
    with open(os.path.join(rd, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
