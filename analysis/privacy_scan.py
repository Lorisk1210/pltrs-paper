#!/usr/bin/env python3
"""Scan the raw session data for private data before publication.

Input:  every file in data/raw (JSONL, gzip JSONL, JSON, text, Markdown)
        known secret values from the local Claude Code settings (read at
        run time, never written out)
Output: data/derived/privacy/findings.jsonl.gz (each hit with file, line and
        the masked value; private, do not publish)
        data/derived/privacy/scan_summary_unmasked.json (private)
        results/privacy/scan_summary.json (counts per category and per
        masked value)

The script does not change any file. analysis/redact.py makes the
redacted copy.

The categories are in PATTERNS. A value is masked as its first 4 and last
2 characters, so that the author can tell values apart without the
summary showing them.
"""
import collections
import gzip
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

PATTERNS = {
    "anthropic_key": r"sk-ant-[A-Za-z0-9_\-]{20,}",
    "openai_style_key": r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{24,}",
    "github_token": r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}",
    "pypi_token": r"pypi-[A-Za-z0-9_\-]{40,}",
    "crates_token": r"\bcio[A-Za-z0-9]{30,}",
    "aws_key": r"\bAKIA[0-9A-Z]{16}\b",
    "slack_token": r"xox[abprs]-[A-Za-z0-9\-]{10,}",
    "jwt": r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}",
    "private_key_block": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "secret_assignment": r"(?i)\b(?:api[_-]?key|auth[_-]?token|access[_-]?token|secret|password|passwd)\b[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9_\-\.\/+=]{12,}",
    "email": r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,6}\b(?![.(\w])",
    "env_secret": r"(?:TOKEN|_KEY|SECRET|PASSWORD)['\"]?\s*[:=]\s*['\"][^'\"\s]{12,}",
    "ipv4_tailscale": r"\b100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b",
    "ipv4_private": r"\b(?:192\.168|10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b",
    "hostname": r"(?i)\b[a-z0-9\-]+\.fritz\.box\b|ibssh_[a-z0-9]{10,}",
    "home_path_user": r"/Users/(?!author)[a-z][a-z0-9]+(?=/)|/home/(?!author)[a-z][a-z0-9]+(?=/)|C:\\\\?Users\\\\?(?!author)[a-z][a-z0-9]+",
    "ssh_command_user_host": r"\bssh\s+(?:-[A-Za-z]\s*\S+\s+)*[A-Za-z0-9_\-]+@[A-Za-z0-9.\-]+",
    "account_uuid": r"\"(?:creator_user_id|creator_account_id|accountUuid|organizationUuid|userID)\"\s*:\s*\"[^\"]+\"",
}
# The private terms (host names, user names, the name of the author) are in
# data/private/privacy_terms.json, which is not in git.
_TERMS = os.path.join(lib.ROOT, "data", "private", "privacy_terms.json")
if os.path.exists(_TERMS):
    _t = json.load(open(_TERMS))
    PATTERNS["hostname"] += "|" + "|".join(re.escape(h) for h in _t.get("hostnames", []))
    PATTERNS["home_path_user"] += "|" + "|".join(_t.get("home_paths", []))
    if _t.get("names"):
        PATTERNS["person_name"] = "(?i)" + "|".join(_t["names"])
    if _t.get("accounts"):
        PATTERNS["github_account"] = "|".join(re.escape(a) for a in _t["accounts"])
COMPILED = {k: re.compile(v) for k, v in PATTERNS.items()}
# Addresses that are documentation examples or harmless.
ALLOW_EMAIL = re.compile(r"(?i)noreply@anthropic\.com|@example\.(?:com|org)|git@github\.com|@users\.noreply\.github\.com")


def mask(v):
    v = str(v)
    return v if len(v) <= 8 else v[:4] + "..." + v[-2:] + " (len %d)" % len(v)


def known_secrets():
    """Read secret values from the local settings. Return {sha256: label}."""
    out = {}
    for path in [os.path.expanduser("~/.claude/settings.json")]:
        try:
            env = json.load(open(path)).get("env", {})
        except (OSError, ValueError):
            continue
        for k, v in env.items():
            if any(w in k.upper() for w in ("TOKEN", "KEY", "SECRET", "PASSWORD")) and isinstance(v, str) and len(v) >= 8:
                out[v] = "settings.env." + k
    return out


def files():
    for root, _, names in os.walk(lib.RAW):
        for n in names:
            yield os.path.join(root, n)


def lines_of(path):
    if path.endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
            yield from f
    elif path.endswith((".jsonl", ".json", ".txt", ".md", ".output", ".log")):
        with open(path, encoding="utf-8", errors="replace") as f:
            yield from f


# Categories with many harmless hits (paths, names). The script counts them
# but writes no single findings for them.
COUNT_ONLY = {"home_path_user", "person_name", "github_account", "hostname", "ipv4_tailscale", "ipv4_private"}


def scan_file(args):
    path, secrets = args
    rel = os.path.relpath(path, lib.RAW)
    counts = collections.Counter()
    values = collections.defaultdict(collections.Counter)
    findings = []
    images = 0
    got = False
    for no, line in enumerate(lines_of(path), 1):
        got = True
        if '"media_type"' in line and '"image"' in line:
            images += line.count('"media_type"')
        for sv, label in secrets.items():
            if sv in line:
                counts["known_secret"] += 1
                values["known_secret"][label] += 1
                findings.append({"file": rel, "line": no, "category": "known_secret", "value": label})
        for cat, rx in COMPILED.items():
            for m in rx.finditer(line):
                v = m.group(0)
                if cat == "email" and ALLOW_EMAIL.search(v):
                    continue
                counts[cat] += 1
                values[cat][v if cat in COUNT_ONLY else mask(v)] += 1
                if cat not in COUNT_ONLY:
                    findings.append({"file": rel, "line": no, "category": cat, "value": mask(v),
                                     "sha8": hashlib.sha256(v.encode()).hexdigest()[:8]})
    return rel, got, counts, values, findings, images


def main():
    from multiprocessing import Pool
    secrets = known_secrets()
    counts = collections.Counter()
    values = collections.defaultdict(collections.Counter)
    files_hit = collections.defaultdict(set)
    skipped = collections.Counter()
    images = 0
    out_dir = os.path.join(lib.DERIVED, "privacy")
    os.makedirs(out_dir, exist_ok=True)
    paths = sorted(files(), key=lambda p: -os.path.getsize(p))
    with gzip.open(os.path.join(out_dir, "findings.jsonl.gz"), "wt", encoding="utf-8") as out, Pool(os.cpu_count()) as pool:
        for rel, got, c, v, fnd, img in pool.imap_unordered(scan_file, [(p, secrets) for p in paths]):
            if not got:
                skipped[os.path.splitext(rel)[1] or "(none)"] += 1
            counts.update(c)
            images += img
            for cat, vv in v.items():
                values[cat].update(vv)
                files_hit[cat].add(rel)
            for x in fnd:
                out.write(json.dumps(x) + "\n")
    summary = {
        "note": "Counts are regex hits. Values are masked, except for host names, paths, names and IP addresses, which the author knows. Single hits are in data/derived/privacy/findings.jsonl.gz (private).",
        "categories": {
            cat: {"hits": counts[cat], "files": len(files_hit[cat]),
                  "top_values": values[cat].most_common(15)}
            for cat in sorted(counts, key=lambda c: -counts[c])
        },
        "image_blocks": images,
        "files_not_scanned_by_extension": dict(skipped),
    }
    # The full values stay private. The summary in results/ masks them.
    with open(os.path.join(out_dir, "scan_summary_unmasked.json"), "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    for cat in summary["categories"].values():
        cat["top_values"] = [[mask(v), n] for v, n in cat["top_values"]]
    summary["note"] = "Counts are regex hits. All values are masked. The unmasked values are in data/derived/privacy/ (private)."
    rd = os.path.join(lib.RESULTS, "privacy")
    os.makedirs(rd, exist_ok=True)
    with open(os.path.join(rd, "scan_summary.json"), "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(json.dumps({c: (v["hits"], v["files"]) for c, v in summary["categories"].items()}, indent=1))
    print("images", images, "not scanned", dict(skipped))


if __name__ == "__main__":
    main()
