#!/usr/bin/env python3
"""Calculate the numbers and the tables that the paper reports.

Input:  data/derived/coded_inputs.jsonl (from summarize_inputs.py)
        data/derived/api_responses.csv.gz (from usage.py)
        the git history of the pltrs repository (read only)
Output: results/paper/numbers.json
        results/paper/timeline_by_day.csv, timeline_by_week.csv
        results/paper/categories.csv, corrective_by_topic.csv
        results/paper/suite_history.csv, rule_file_history.csv

The pltrs repository is at ~/dev/plt-rs. Set PLTRS_REPO for a different
path. All days are UTC days.
"""
import collections
import csv
import datetime
import gzip
import json
import os
import statistics
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

REPO = os.environ.get("PLTRS_REPO", os.path.expanduser("~/dev/plt-rs"))
OUT = os.path.join(lib.RESULTS, "paper")
RULE_FILES = ["AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md"]
FIRST_DAY = datetime.date(2026, 10, 16)
LAST_DAY = datetime.date(2026, 11, 23)


def git(*args):
    env = dict(os.environ, TZ="UTC")
    return subprocess.run(["git", "-C", REPO] + list(args), capture_output=True, text=True,
                          check=True, env=env).stdout


def week(day):
    d = datetime.date.fromisoformat(day)
    return "%d-W%02d" % d.isocalendar()[:2]


def parse(ts):
    return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def suite_history():
    """Tests that pass with matplotlib and with pltrs, for each commit of the outcome file."""
    rows = []
    log = git("log", "--reverse", "--format=%H %ad", "--date=format-local:%Y-%m-%dT%H:%M:%SZ",
              "--", "spec/mpl-suite/pltrs.json").split("\n")
    for line in log:
        if not line.strip():
            continue
        commit, when = line.split()
        try:
            ours = json.loads(git("show", commit + ":spec/mpl-suite/pltrs.json"))["outcomes"]
            ref = json.loads(git("show", commit + ":spec/mpl-suite/reference.json"))["outcomes"]
        except (subprocess.CalledProcessError, ValueError, KeyError):
            continue
        ref_pass = [t for t, o in ref.items() if o == "passed"]
        both = sum(1 for t in ref_pass if ours.get(t) == "passed")
        rows.append({"commit": commit[:8], "time": when, "pass_with_matplotlib": len(ref_pass),
                     "also_pass_with_pltrs": both,
                     "percent": round(100.0 * both / len(ref_pass), 2) if ref_pass else ""})
    lib.write_csv(os.path.join(OUT, "suite_history.csv"), rows,
                  ["commit", "time", "pass_with_matplotlib", "also_pass_with_pltrs", "percent"])
    return rows


def rule_file_history():
    rows = []
    log = git("log", "--reverse", "--format=%H %ad", "--date=format-local:%Y-%m-%d", "--", *RULE_FILES)
    for line in log.split("\n"):
        if not line.strip():
            continue
        commit, day = line.split()
        r = {"commit": commit[:8], "day": day}
        total = 0
        for f in RULE_FILES:
            p = subprocess.run(["git", "-C", REPO, "show", "%s:%s" % (commit, f)],
                               capture_output=True, text=True)
            n = len(p.stdout.splitlines()) if p.returncode == 0 else 0
            r[f] = n
            total += n
        r["lines"] = total
        rows.append(r)
    lib.write_csv(os.path.join(OUT, "rule_file_history.csv"), rows, ["commit", "day"] + RULE_FILES + ["lines"])
    return rows


def main():
    os.makedirs(OUT, exist_ok=True)
    inputs = [json.loads(l) for l in open(os.path.join(lib.DERIVED, "coded_inputs.jsonl"), encoding="utf-8")]
    inputs.sort(key=lambda r: r["time"])
    responses = []
    with gzip.open(os.path.join(lib.DERIVED, "api_responses.csv.gz"), "rt") as f:
        for r in csv.DictReader(f):
            responses.append((r["timestamp"], float(r["cost_usd"] or 0)))
    responses.sort()
    commit_times = [t for t in git("log", "--format=%ad", "--date=format-local:%Y-%m-%dT%H:%M:%SZ").split("\n") if t]
    commit_times.sort()

    # Timeline for each day.
    days = [(FIRST_DAY + datetime.timedelta(days=i)).isoformat()
            for i in range((LAST_DAY - FIRST_DAY).days + 1)]
    t = {d: collections.Counter() for d in days}
    for ts, cost in responses:
        d = ts[:10]
        if d in t:
            t[d]["responses"] += 1
            t[d]["cost_usd"] += cost
    for ts in commit_times:
        if ts[:10] in t:
            t[ts[:10]]["commits"] += 1
    for r in inputs:
        d = r["time"][:10]
        if d in t:
            t[d]["inputs"] += 1
            t[d]["corrective"] += int(bool(r["corrective"]))
            t[d]["words"] += r["words"]
    cols = ["responses", "cost_usd", "commits", "inputs", "corrective", "words"]
    day_rows = []
    for d in days:
        row = {"day": d}
        row.update({c: t[d][c] for c in cols})
        row["cost_usd"] = round(row["cost_usd"], 2)
        day_rows.append(row)
    lib.write_csv(os.path.join(OUT, "timeline_by_day.csv"), day_rows, ["day"] + cols)
    wk = collections.OrderedDict()
    for row in day_rows:
        a = wk.setdefault(week(row["day"]), collections.Counter())
        for c in cols:
            a[c] += row[c]
        a["days"] += 1
    week_rows = []
    for w, a in wk.items():
        row = {"week": w, "days": a["days"]}
        row.update({c: a[c] for c in cols})
        row["cost_usd"] = round(row["cost_usd"], 2)
        week_rows.append(row)
    lib.write_csv(os.path.join(OUT, "timeline_by_week.csv"), week_rows, ["week", "days"] + cols)

    # Categories, with the corrective inputs in each.
    cat = collections.OrderedDict()
    for r in inputs:
        a = cat.setdefault(r["category"], collections.Counter())
        a["inputs"] += 1
        a["words"] += r["words"]
        a["corrective"] += int(bool(r["corrective"]))
    cat_rows = [dict(category=k, **v) for k, v in sorted(cat.items(), key=lambda kv: -kv[1]["inputs"])]
    lib.write_csv(os.path.join(OUT, "categories.csv"), cat_rows, ["category", "inputs", "words", "corrective"])

    corr = [r for r in inputs if r["corrective"]]
    topic = collections.OrderedDict()
    for r in corr:
        a = topic.setdefault(r["topic"], collections.Counter())
        a["corrective"] += 1
        a["trigger_" + (r["corr_trigger"] or "none")] += 1
    all_topic = collections.Counter(r["topic"] for r in inputs)
    topic_rows = []
    for k, a in sorted(topic.items(), key=lambda kv: -kv[1]["corrective"]):
        row = {"topic": k, "inputs": all_topic[k]}
        row.update(a)
        topic_rows.append(row)
    triggers = sorted({k for a in topic.values() for k in a if k.startswith("trigger_")})
    lib.write_csv(os.path.join(OUT, "corrective_by_topic.csv"), topic_rows,
                  ["topic", "inputs", "corrective"] + triggers)

    # The longest time without an input.
    times = [parse(r["time"]) for r in inputs]
    gaps = sorted(((b - a, a, b) for a, b in zip(times, times[1:])), reverse=True)
    gap, ga, gb = gaps[0]
    a_iso, b_iso = ga.strftime("%Y-%m-%dT%H:%M:%SZ"), gb.strftime("%Y-%m-%dT%H:%M:%SZ")
    gap_resp = [c for ts, c in responses if a_iso <= ts <= b_iso]
    gap_commits = [ts for ts in commit_times if a_iso <= ts <= b_iso]

    msgs = [r for r in inputs if r["kind"] == "message"]
    words = [r["words"] for r in msgs]
    total_cost = sum(c for _, c in responses)
    in_period = [(ts, c) for ts, c in responses if ts[:10] in t]
    input_days = {r["time"][:10] for r in inputs}
    work_days = {d for d in days if t[d]["responses"]}
    commit_days = {d for d in days if t[d]["commits"]}
    release_from = "2026-11-20"
    suite = suite_history()
    rules = rule_file_history()
    full = [r for r in suite if r["also_pass_with_pltrs"] == r["pass_with_matplotlib"]]

    numbers = {
        "days": len(days),
        "inputs": len(inputs),
        "messages": len(msgs),
        "answers": sum(1 for r in inputs if r["kind"] == "answer"),
        "interrupts": sum(1 for r in inputs if r["kind"] == "interrupt"),
        "messages_from_mobile": sum(1 for r in msgs if r.get("source") == "mobile"),
        "words": sum(words),
        "median_words": statistics.median(words),
        "messages_of_at_most_20_words": sum(1 for w in words if w <= 20),
        "messages_over_100_words": sum(1 for w in words if w > 100),
        "words_in_messages_over_100_words": sum(w for w in words if w > 100),
        "days_with_input": len(input_days),
        "days_with_agent_responses": len(work_days),
        "days_with_agent_responses_without_input": len(work_days - input_days),
        "days_with_commits": len(commit_days),
        "max_inputs_on_one_day": max(t[d]["inputs"] for d in days),
        "inputs_by_thread_title": dict(collections.Counter(r.get("thread_title") or "(interrupt or answer)" for r in inputs).most_common(4)),
        "responses": len(responses),
        "responses_in_period": len(in_period),
        "cost_usd": round(total_cost, 2),
        "responses_per_input": round(len(responses) / len(inputs)),
        "cost_per_input_usd": round(total_cost / len(inputs), 2),
        "commits": len(commit_times),
        "commits_per_input": round(len(commit_times) / len(inputs), 2),
        "longest_gap_without_input": {
            "from": a_iso, "to": b_iso, "hours": round(gap.total_seconds() / 3600, 1),
            "responses": len(gap_resp), "cost_usd": round(sum(gap_resp), 2), "commits": len(gap_commits),
        },
        "gaps_over_24_hours": sum(1 for g, _, _ in gaps if g.total_seconds() > 24 * 3600),
        "corrective": len(corr),
        "corrective_by_category": dict(collections.Counter(r["category"] for r in corr).most_common()),
        "corrective_by_topic": dict(collections.Counter(r["topic"] for r in corr).most_common()),
        "corrective_by_trigger": dict(collections.Counter(r["corr_trigger"] for r in corr).most_common()),
        "corrective_by_problem": dict(collections.Counter(r["corr_problem"] for r in corr).most_common()),
        "corrective_ids_by_topic": {k: [r["id"] for r in corr if r["topic"] == k]
                                    for k in sorted({r["topic"] for r in corr})},
        "inputs_with_topic_correctness": [(r["id"], r["category"], bool(r["corrective"]))
                                          for r in inputs if r["topic"] == "correctness"],
        "release_phase": {
            "from": release_from,
            "inputs": sum(1 for r in inputs if r["time"][:10] >= release_from),
            "corrective": sum(1 for r in corr if r["time"][:10] >= release_from),
            "corrective_external_check": sum(1 for r in corr if r["time"][:10] >= release_from
                                             and r["corr_trigger"] == "external_check"),
            "cost_usd": round(sum(c for ts, c in responses if ts[:10] >= release_from), 2),
            "commits": sum(1 for ts in commit_times if ts[:10] >= release_from),
        },
        "steer_report_with_reaction": dict(collections.Counter(
            r.get("agent_reaction") for r in corr if r.get("agent_reaction")).most_common()),
        "corrective_with_rule_followup": sum(1 for r in corr if r.get("rule_followup")),
        "rule_file_commits": len(rules),
        "rule_file_lines_first": rules[0]["lines"],
        "rule_file_lines_last": rules[-1]["lines"],
        "rule_file_lines_max": max(r["lines"] for r in rules),
        "suite_first": suite[0],
        "suite_first_full": full[0] if full else None,
        "suite_last": suite[-1],
    }
    # The agent estimated "about 95% of the goal" at this time (input H032 answers it).
    est = "2026-10-29T00:11:12Z"
    numbers["after_95_percent_estimate"] = {
        "time": est,
        "commits_after": sum(1 for ts in commit_times if ts > est),
        "cost_after_usd": round(sum(c for ts, c in responses if ts > est), 2),
        "cost_share_after": round(sum(c for ts, c in responses if ts > est) / total_cost, 3),
    }
    climb = [r for r in inputs if suite[0]["time"] <= r["time"][:19] + "Z" <= full[0]["time"]]
    numbers["suite_climb"] = {
        "from": suite[0]["time"], "to": full[0]["time"],
        "hours": round((parse(full[0]["time"]) - parse(suite[0]["time"])).total_seconds() / 3600, 1),
        "recorded_runs": suite.index(full[0]) + 1,
        "inputs": len(climb),
        "inputs_by_category": dict(collections.Counter(r["category"] for r in climb).most_common()),
        "commits": sum(1 for ts in commit_times if suite[0]["time"] <= ts <= full[0]["time"]),
    }
    handoff = [r for r in msgs if (r.get("text") or "").startswith("# Continue plt-rs")]
    numbers["pasted_handoff_prompt"] = {"messages": len(handoff), "words": sum(r["words"] for r in handoff)}
    numbers["inputs_that_name_a_check"] = {
        w: sum(1 for r in inputs if w in (r.get("text") or "").lower() and r not in handoff)
        for w in ("fuzz", "differential", "seaborn")
    }
    groups = {
        "keep_running": ("continue", "session", "interrupt"),
        "question": ("question",),
        "resources_facts_actions": ("resource", "inform", "operate"),
        "direction_feedback": ("goal", "steer", "decide", "report"),
    }
    numbers["groups"] = {g: sum(1 for r in inputs if r["category"] in c) for g, c in groups.items()}
    numbers["question_topics"] = dict(collections.Counter(r["topic"] for r in inputs if r["category"] == "question").most_common())
    numbers["resource_inputs"] = sum(1 for r in inputs if r["category"] == "resource")
    with open(os.path.join(OUT, "numbers.json"), "w") as f:
        json.dump(numbers, f, indent=2)
    print(json.dumps(numbers, indent=2))


if __name__ == "__main__":
    main()
