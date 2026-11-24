#!/usr/bin/env python3
"""Merge the codes, measure the agreement of the two coders, and write the tables.

Input:  data/derived/human_inputs.jsonl
        results/coding/pass1_batch*.jsonl  (full codes, coder 1)
        results/coding/pass2_part*.jsonl   (category, topic, problem; coder 2, blind)
        results/coding/goal_recheck.jsonl  (for goal inputs: did the goal react to the agent?)
Output: data/derived/coded_inputs.jsonl (inputs with codes, private)
        results/inputs/*.csv, results/inputs/agreement.json,
        results/inputs/steering_cases.md

Interrupts get the category "interrupt" without a coder.
An input is "corrective" if it has the code steer or report, or if it is a
goal that reacts to agent behavior (goal_recheck). For corrective inputs,
"problem" and "trigger" come from pass 1 if pass 1 has them, else from the
goal recheck.
Cohen's kappa is calculated on the inputs that both coders coded.
"""
import collections
import glob
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

CATS = ["goal", "steer", "report", "question", "decide", "inform", "resource", "operate", "continue", "session", "interrupt"]


def kappa(pairs):
    n = len(pairs)
    if not n:
        return None
    agree = sum(1 for a, b in pairs if a == b) / n
    ca = collections.Counter(a for a, _ in pairs)
    cb = collections.Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return {"n": n, "percent_agreement": round(100 * agree, 1), "kappa": round((agree - pe) / (1 - pe), 3) if pe < 1 else None}


def load(pattern):
    out = {}
    for p in sorted(glob.glob(os.path.join(lib.RESULTS, "coding", pattern))):
        with open(p) as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    out[r["id"]] = r
    return out


def week(ts):
    d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return "%d-W%02d" % d.isocalendar()[:2]


def main():
    inputs = [json.loads(l) for l in open(os.path.join(lib.DERIVED, "human_inputs.jsonl"), encoding="utf-8")]
    p1 = load("pass1_batch*.jsonl")
    p2 = load("pass2_part*.jsonl")
    gr = load("goal_recheck.jsonl")
    # Keep only the codes of the inputs that inputs.py still lists.
    ids = {r["id"] for r in inputs}
    p1, p2, gr = ({k: v for k, v in d.items() if k in ids} for d in (p1, p2, gr))
    rd = os.path.join(lib.RESULTS, "inputs")
    os.makedirs(rd, exist_ok=True)

    coded = []
    missing = []
    for r in inputs:
        c = dict(r)
        if r["kind"] == "interrupt":
            c.update(category="interrupt", also=[], topic="none", confidence="high", quotable=True)
        elif r["id"] in p1:
            c.update({k: v for k, v in p1[r["id"]].items() if k != "id"})
        else:
            missing.append(r["id"])
        title = (r.get("thread_title") or "").lower()
        c["about_paper"] = "paper" in title or "scientific" in title
        c["words"] = len((r.get("text") or "").split()) if r["kind"] == "message" else 0
        c["steer_any"] = c.get("category") == "steer" or "steer" in (c.get("also") or [])
        g = gr.get(r["id"])
        c["goal_reacts_to_agent"] = g["reacts_to_agent"] if g else None
        if g:
            c["goal_trigger"], c["goal_problem"], c["goal_evidence"] = g["trigger"], g["problem"], g["evidence"]
        cats = [c.get("category")] + list(c.get("also") or [])
        c["corrective"] = bool(c["steer_any"] or "report" in cats or (g and g["reacts_to_agent"]))
        c["corr_trigger"] = c.get("trigger") or (g and g["trigger"]) or None
        c["corr_problem"] = c.get("problem") or (g and g["problem"]) or None
        c["corr_evidence"] = c.get("evidence") or (g and g["evidence"]) or None
        coded.append(c)
    with open(os.path.join(lib.DERIVED, "coded_inputs.jsonl"), "w", encoding="utf-8") as f:
        for c in coded:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    # Agreement.
    both = [i for i in p1 if i in p2]
    agree = {
        "coder1": "pass1 (full codebook, transcript context)",
        "coder2": "pass2 (category, topic, problem; blind to coder 1)",
        "category": kappa([(p1[i]["category"], p2[i]["category"]) for i in both]),
        "topic": kappa([(p1[i]["topic"], p2[i]["topic"]) for i in both]),
        "steer_vs_not": kappa([(p1[i]["category"] == "steer", p2[i]["category"] == "steer") for i in both]),
        "problem_when_both_steer_or_report": kappa([
            (p1[i]["problem"], p2[i]["problem"]) for i in both
            if p1[i]["category"] in ("steer", "report") and p2[i]["category"] in ("steer", "report")]),
        "confusion_category": {},
    }
    conf = collections.Counter((p1[i]["category"], p2[i]["category"]) for i in both if p1[i]["category"] != p2[i]["category"])
    agree["confusion_category"] = {"%s -> %s" % k: v for k, v in conf.most_common()}
    with open(os.path.join(rd, "agreement.json"), "w") as f:
        json.dump(agree, f, indent=2)
    dis = []
    for i in both:
        a, b = p1[i], p2[i]
        if a["category"] != b["category"] or a["topic"] != b["topic"]:
            dis.append({"id": i, "coder1_category": a["category"], "coder2_category": b["category"],
                        "coder1_topic": a["topic"], "coder2_topic": b["topic"],
                        "coder1_confidence": a.get("confidence"), "coder1_note": a.get("note") or ""})
    lib.write_csv(os.path.join(rd, "disagreements.csv"), dis, list(dis[0].keys()) if dis else ["id"])

    # Counts.
    def count(keyf, name, fields):
        cnt = collections.Counter()
        words = collections.Counter()
        for c in coded:
            for k in keyf(c):
                cnt[k] += 1
                words[k] += c["words"]
        rows = [dict(zip(fields, k if isinstance(k, tuple) else (k,)), inputs=v, words=words[k]) for k, v in sorted(cnt.items(), key=lambda kv: (-kv[1], str(kv[0])))]
        lib.write_csv(os.path.join(rd, name), rows, list(fields) + ["inputs", "words"])
        return rows

    count(lambda c: [c.get("category")], "by_category.csv", ["category"])
    count(lambda c: [c.get("category")] + list(c.get("also") or []), "by_category_including_also.csv", ["category"])
    count(lambda c: [c.get("topic")], "by_topic.csv", ["topic"])
    count(lambda c: [c.get("category")] if not c["about_paper"] else [], "by_category_without_paper_threads.csv", ["category"])
    count(lambda c: [(c.get("category"), c.get("topic"))], "by_category_topic.csv", ["category", "topic"])
    count(lambda c: [(week(c["time"]), c.get("category"))], "by_week_category.csv", ["week", "category"])
    count(lambda c: [c["time"][:10]], "by_day.csv", ["day"])
    count(lambda c: [c.get("machine")], "by_machine.csv", ["machine"])
    st = [c for c in coded if c.get("trigger") or c.get("problem")]
    st_ids = {c["id"] for c in st}
    count(lambda c: [c.get("problem")] if c in st else [], "steer_report_by_problem.csv", ["problem"])
    count(lambda c: [c.get("trigger")] if c in st else [], "steer_report_by_trigger.csv", ["trigger"])
    count(lambda c: [(c.get("category"), c.get("problem"))] if c in st else [], "steer_report_by_category_problem.csv", ["category", "problem"])
    count(lambda c: [c.get("agent_reaction")] if c in st else [], "steer_report_by_reaction.csv", ["agent_reaction"])
    corr = [c for c in coded if c["corrective"]]
    count(lambda c: [c["corr_problem"]] if c["corrective"] else [], "corrective_by_problem.csv", ["problem"])
    count(lambda c: [c["corr_trigger"]] if c["corrective"] else [], "corrective_by_trigger.csv", ["trigger"])
    count(lambda c: [(c["category"], c["corr_problem"])] if c["corrective"] else [], "corrective_by_category_problem.csv", ["category", "problem"])
    count(lambda c: [(week(c["time"]), c["corr_problem"])] if c["corrective"] else [], "corrective_by_week_problem.csv", ["week", "problem"])

    # The list of all coded inputs. Text only if the coder marked it quotable.
    rows = []
    for c in coded:
        rows.append({
            "id": c["id"], "time": c["time"], "machine": c["machine"], "kind": c["kind"],
            "thread_title": c.get("thread_title") or "", "words": c["words"],
            "category": c.get("category"), "also": ";".join(c.get("also") or []), "topic": c.get("topic"),
            "trigger": c.get("trigger") or "", "problem": c.get("problem") or "",
            "agent_reaction": c.get("agent_reaction") or "", "rule_followup": c.get("rule_followup") or "",
            "corrective": c["corrective"], "corr_trigger": c["corr_trigger"] or "", "corr_problem": c["corr_problem"] or "",
            "confidence": c.get("confidence"), "quotable": c.get("quotable"),
            "text": lib.norm(c.get("text")) if c.get("quotable") else "[not quotable: private data]",
        })
    lib.write_csv(os.path.join(rd, "coded_inputs.csv"), rows, list(rows[0].keys()))

    # Steering and report cases, for reading.
    with open(os.path.join(rd, "steering_cases.md"), "w", encoding="utf-8") as f:
        f.write("# Steering and report cases\n\n")
        f.write("Each corrective input: the code `steer` or `report` in `category` or `also`, "
                "or a `goal` that reacts to agent behavior (from the goal recheck). "
                "Generated by `analysis/summarize_inputs.py`. Do not edit by hand.\n\n")
        for c in [c for c in coded if c["corrective"] and c["id"] not in st_ids]:
            st.append(c)
            c["trigger"], c["problem"], c["evidence"] = c["corr_trigger"], c["corr_problem"], c["corr_evidence"]
        st.sort(key=lambda c: c["id"])
        for c in st:
            f.write("## %s (%s, %s)\n\n" % (c["id"], c["time"][:16].replace("T", " "), c.get("thread_title") or c["kind"]))
            f.write("* Category: `%s`%s. Topic: `%s`.\n" % (c["category"], (" (also " + ", ".join(c.get("also") or []) + ")") if c.get("also") else "", c.get("topic")))
            f.write("* Trigger: `%s`. Problem: `%s`. Agent reaction: `%s`.\n" % (c.get("trigger"), c.get("problem"), c.get("agent_reaction")))
            if c.get("rule_followup"):
                f.write("* Rule follow-up: %s\n" % c["rule_followup"])
            if c.get("quotable"):
                f.write("\n> " + lib.norm(c.get("text"))[:1500] + "\n")
            else:
                f.write("\n> [not quotable: private data]\n")
            f.write("\n%s\n\n" % (c.get("evidence") or ""))
            if c.get("note"):
                f.write("Note: %s\n\n" % c["note"])

    total_words = sum(c["words"] for c in coded)
    summary = {
        "inputs": len(coded),
        "messages": sum(1 for c in coded if c["kind"] == "message"),
        "answers": sum(1 for c in coded if c["kind"] == "answer"),
        "interrupts": sum(1 for c in coded if c["kind"] == "interrupt"),
        "words_typed": total_words,
        "inputs_in_paper_threads": sum(1 for c in coded if c["about_paper"]),
        "median_words_per_message": sorted(c["words"] for c in coded if c["kind"] == "message")[sum(1 for c in coded if c["kind"] == "message") // 2],
        "steer_any": sum(1 for c in coded if c["steer_any"]),
        "steer_or_report_any": len(st_ids),
        "goals_reacting_to_agent": sum(1 for c in coded if c["goal_reacts_to_agent"]),
        "goals_rechecked": sum(1 for c in coded if c["goal_reacts_to_agent"] is not None),
        "corrective": sum(1 for c in coded if c["corrective"]),
        "not_coded": missing,
        "agreement": {k: agree[k] for k in ("category", "topic", "steer_vs_not", "problem_when_both_steer_or_report")},
    }
    with open(os.path.join(rd, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))
    print(json.dumps(agree["confusion_category"], indent=1))


if __name__ == "__main__":
    main()
