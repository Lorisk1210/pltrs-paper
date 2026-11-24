# Replication material for the pltrs paper

This repository has the scripts, the codebook and the codes for the paper
"What Human Input Do Coding Agents Need? A Case Study of an Agent-Built
Port of matplotlib". The paper analyzes the inputs that the author gave
to coding agents while they built [pltrs](https://github.com/Lorisk1210/plt-rs),
a port of matplotlib 3.11 to Rust.

## Contents

| Path | Contents |
| --- | --- |
| `analysis/*.py` | The scripts that count the tokens, find the inputs of the author, summarize the codes and draw the figures |
| `analysis/README.md` | The order in which to run the scripts |
| `analysis/METHODOLOGY.md` | The method in detail |
| `analysis/codebook.md` | The codebook for the classification of the inputs |
| `analysis/pricing.json` | The API prices that the cost calculation uses |
| `analysis/redact_rules.json` | The rules of the redaction script |
| `results/coding/*.jsonl` | The codes of each coding pass: coder 1 (`pass1_*`), coder 2 (`pass2_*`) and the recheck of the goals (`goal_recheck.jsonl`) |

Each code has the id of an input (`H001` to `H249`). Some ids are not
used, because the analysis excludes the threads of other providers and
the threads about the paper.

## What is not here

The session records are not in this repository. They contain private
data, and the scripts need them as input (`data/raw/`). Thus, you can
read the scripts and the codes here, but you cannot run the scripts
without session records of your own.

To run the analysis on a different project, copy its Claude Code
transcripts and its T3 Code export into `data/raw/` as
`analysis/collect/README.md` describes, and run the scripts in the order
of `analysis/README.md`.
