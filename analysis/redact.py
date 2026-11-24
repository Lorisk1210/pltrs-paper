#!/usr/bin/env python3
"""Make a redacted copy of data/raw in data/public, for publication.

Usage: redact.py [--check]

Input:  data/raw (all files), analysis/redact_rules.json,
        data/private/redact_literals.json (private), the known secret
        values from the local Claude Code settings
Output: data/public (same layout as data/raw; the rules also apply to file
        and directory names)
        results/privacy/redaction_report.json (replacements per rule)

With --check, the script runs analysis/privacy_scan.py patterns on
data/public and reports the hits that are left.

Method:
* Each line of each text file gets the literal rules, then the regex
  rules, in the order of the rules file.
* Known secret values become "[REDACTED-SECRET]".
* If "remove_images" is true, the base64 data of each image block becomes
  an empty string and the media type "image/removed".
* Binary files (for example PNG files in tool-result folders) are not
  copied. The report lists them.
"""
import collections
import gzip
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402
import privacy_scan  # noqa: E402

PUBLIC = os.path.join(lib.ROOT, "data", "public")
TEXT_EXT = (".jsonl", ".json", ".txt", ".md", ".output", ".log", ".gz")
IMG = re.compile(r'("type":\s*"base64",\s*"media_type":\s*")image/[a-z]+(",\s*"data":\s*")[A-Za-z0-9+/=]+(")')
IMG2 = re.compile(r'("data":\s*")[A-Za-z0-9+/=]{200,}(",\s*"media_type":\s*")image/[a-z]+(")')


def load_rules():
    r = json.load(open(os.path.join(lib.ROOT, "analysis", "redact_rules.json")))
    lit_file = os.path.join(lib.ROOT, r.get("literal_file", ""))
    lit = [(a, b) for a, b in json.load(open(lit_file))["literal"]] if r.get("literal_file") else []
    lit += [(a, b) for a, b in r.get("literal", [])]
    rx = [(re.compile(a), b) for a, b in r["regex"]]
    return lit, rx, r.get("remove_images", True)


def apply(s, lit, rx, secrets, remove_images, stats):
    for sv in secrets:
        if sv in s:
            stats["known_secret"] += s.count(sv)
            s = s.replace(sv, "[REDACTED-SECRET]")
    if remove_images:
        s, n = IMG.subn(r"\1image/removed\2\3", s)
        s, m = IMG2.subn(r"\1\2image/removed\3", s)
        stats["image"] += n + m
    for a, b in lit:
        if a in s:
            stats["literal -> " + b] += s.count(a)
            s = s.replace(a, b)
    for c, b in rx:
        s, n = c.subn(b, s)
        if n:
            stats["regex -> " + b] += n
    return s


def rename(rel, lit):
    for a, b in lit:
        rel = rel.replace(a, b)
    return rel


def redact_file(args):
    src, dst, lit, rx_src, secrets, remove_images = args
    rx = [(re.compile(a), b) for a, b in rx_src]
    stats = collections.Counter()
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if src.endswith(".gz"):
        fi = gzip.open(src, "rt", encoding="utf-8", errors="replace")
        fo = gzip.open(dst, "wt", encoding="utf-8")
    else:
        fi = open(src, encoding="utf-8", errors="replace")
        fo = open(dst, "w", encoding="utf-8")
    with fi, fo:
        for line in fi:
            fo.write(apply(line, lit, rx, secrets, remove_images, stats))
    return stats


def main():
    from multiprocessing import Pool
    lit, rx, remove_images = load_rules()
    rx_src = [(c.pattern, b) for c, b in rx]
    secrets = list(privacy_scan.known_secrets())
    if "--check" in sys.argv:
        check()
        return
    stats = collections.Counter()
    skipped = []
    jobs = []
    for root, _, names in os.walk(lib.RAW):
        for n in names:
            src = os.path.join(root, n)
            rel = os.path.relpath(src, lib.RAW)
            if not n.endswith(TEXT_EXT):
                skipped.append(rel)
                continue
            jobs.append((src, os.path.join(PUBLIC, rename(rel, lit)), lit, rx_src, secrets, remove_images))
    jobs.sort(key=lambda j: -os.path.getsize(j[0]))
    with Pool(os.cpu_count()) as pool:
        for st in pool.imap_unordered(redact_file, jobs):
            stats.update(st)
    rep = {"replacements": dict(stats.most_common()), "files_written": len(jobs),
           "binary_files_not_copied": len(skipped), "binary_files": skipped[:200]}
    os.makedirs(os.path.join(lib.RESULTS, "privacy"), exist_ok=True)
    with open(os.path.join(lib.RESULTS, "privacy", "redaction_report.json"), "w") as f:
        json.dump(rep, f, indent=2, ensure_ascii=False)
    print(json.dumps(rep["replacements"], indent=1))
    print("files written:", len(jobs), "binary files not copied:", len(skipped))


def check_file(path):
    secrets = privacy_scan.known_secrets()
    left = collections.Counter()
    examples = collections.defaultdict(set)
    for line in privacy_scan.lines_of(path):
        for sv in secrets:
            if sv in line:
                left["known_secret"] += 1
        for cat, c in privacy_scan.COMPILED.items():
            for m in c.finditer(line):
                v = m.group(0)
                if cat == "email" and privacy_scan.ALLOW_EMAIL.search(v):
                    continue
                left[cat] += 1
                if len(examples[cat]) < 10:
                    examples[cat].add(privacy_scan.mask(v))
    return left, examples


def check():
    """Scan data/public with the scan patterns and report what is left."""
    from multiprocessing import Pool
    paths = [os.path.join(r, n) for r, _, ns in os.walk(PUBLIC) for n in ns]
    paths.sort(key=lambda p: -os.path.getsize(p))
    left = collections.Counter()
    examples = collections.defaultdict(set)
    with Pool(os.cpu_count()) as pool:
        for l, e in pool.imap_unordered(check_file, paths):
            left.update(l)
            for k, v in e.items():
                if len(examples[k]) < 15:
                    examples[k] |= set(list(v)[:15 - len(examples[k])])
    out = {"note": "Hits of the scan patterns in data/public. Values are masked.",
           "left": dict(left.most_common()), "examples": {k: sorted(v) for k, v in examples.items()}}
    with open(os.path.join(lib.RESULTS, "privacy", "redaction_check.json"), "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
