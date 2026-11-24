# Methodology of the session analysis

This document describes how the data for RQ2 (what the author did) and
the token counts were collected, processed and coded. It is the base for
Section `sec:method` of the paper. Each step has a script in `analysis/`,
so that the author can run it again. `analysis/README.md` gives the order
of the scripts.

## 1. Data sources

The pltrs project ran from 2026-10-16 to 2026-11-23 on four machines. The
author worked only through T3 Code. T3 Code starts Claude Code through
the Claude Agent SDK. Each machine keeps two kinds of records:

| Source | Location | Contents |
| --- | --- | --- |
| Claude Code transcripts | `~/.claude/projects/<dir>/<session>.jsonl` and `<session>/subagents/agent-*.jsonl` | One record for each prompt, each model response (with the `usage` object of the API), each tool call and each tool result. |
| T3 Code database | `~/.t3/userdata/statev2.sqlite` | Threads, messages with the field `createdBy` (`user` or `agent`), runs, turns with token counts, and the Claude Code session id of each thread. |
| Codex session | `~/.codex/sessions/.../rollout-*.jsonl` | One session in the pltrs directory on MS-02. |

The collection kept the transcript directories whose name contains
`plt-rs`, and the directory `pltrs-icon-design` on the MacBook. It
excluded the directory of this paper (`pltrs-paper`) and the T3 title
generator directories (`t3code-claude-title-*`). From each T3 database,
`analysis/collect/t3_export.py` exported only the projects whose
workspace root contains `plt-rs`.

| Machine | Transcript files | T3 threads |
| --- | --- | --- |
| MS-02 | 376 (162 main, 214 subagent) | 378 |
| MacBook | 7 | 6 |
| Windows PC | 4 | 4 |
| Framework laptop | 4 | 29 |

The raw copies are in `data/raw/` (not in git). `analysis/collect/README.md`
gives the commands.

### Gap in the data

Claude Code deletes transcripts after `cleanupPeriodDays` days. The
default is 30. The Framework laptop and the Windows PC use the default.
The transcript of the first session (Framework, 2026-10-16 10:14 to 16:45
UTC) is deleted. T3 Code still has its messages and the token counts of
its main agent. The tokens of its subagents are lost. 24 commits of
`~/dev/plt-rs` are from this session. All other T3 threads with Claude
Code have a transcript (`results/usage/coverage.json`).

## 2. Token counts and cost

Script: `analysis/usage.py`. Results: `results/usage/`.

1. Each assistant record in a transcript has the `usage` object of the
   API response: `input_tokens`, `cache_creation` (split into 5-minute
   and 1-hour writes), `cache_read_input_tokens` and `output_tokens`.
2. Claude Code writes one record for each content block of a response.
   A resumed session also copies earlier records into a new file. The
   script keeps one row for each `message.id` over all files and
   machines (159,130 responses).
3. Records with the model `<synthetic>` are local error messages and have
   no API request. The script ignores them.
4. The cost is the token count multiplied by the list price of the
   Claude API (`analysis/pricing.json`, read on 2026-11-23). All
   responses have `speed` `standard`, `inference_geo` `global` and
   `service_tier` `standard`, so no multiplier applies.
5. Cross-check 1. Newer Claude Code versions write a `cost-state` record
   with the cost that Claude Code calculated. For the 177 sessions with
   such records, Claude Code gives $20,286 and the script gives $20,322
   (0.2 % difference).
6. Cross-check 2. T3 Code counts the tokens of the main agent of each
   turn. For the 173 threads with a transcript, T3 counts 38.6 billion
   input tokens and the transcripts 43.1 billion for the main agents.
   `analysis/t3_turn_check.py` finds the cause. For the 3,180 completed
   turns, the counts differ by less than 0.1 %. T3 stores no count for
   the 43 cancelled turns (2.5 billion input tokens in the transcripts),
   and only 0.7 of 2.7 billion for the 27 interrupted turns
   (`results/usage/t3_turn_check.json`).
7. Gap estimate (`analysis/coverage.py`). For the deleted first session,
   the script prices the T3 counts. T3 does not split the cache writes
   by duration, so the script gives a range: $52.32 (all 5-minute
   writes) to $55.29 (all 1-hour writes).
8. Roles (`analysis/usage_roles.py`). Each session gets one role:
   a thread that the author started, a thread that an agent started
   (T3 `delegate_task` or `t3_thread_launch`), a native Claude Code
   subagent, or no T3 thread.

The cost is what the project would cost at API prices. The author paid
for subscriptions.

Five threads used other providers (Grok 4.7 through Cursor, GPT-6 through
Codex, Gemini 3.8 Flash through Antigravity). All five only answered
questions about cost or progress. T3 has token counts only for the Codex
thread (2.2 million input, 13,159 output). They are not in the cost.
`analysis/inputs.py` also removes the 8 inputs in these threads, after it
numbers the inputs. Thus, the ids of the other inputs stay the same, and
the ids H034 to H037, H040, H047, H048 and H059 are not used.

Two threads on the MacBook are about the paper and not about pltrs
("Scientific Value of a Project Paper" and "Scientific Paper Angles for
Project"). `analysis/inputs.py` removes their 20 inputs in the same way.
Their 49 responses ($3.27) stay in the cost, because the cost covers all
sessions of the pltrs repository.

The case ends when release 0.1.1 is complete. The last release step is
the upload to crates.io on 23 November 2026 (input H225 at 08:29 UTC).
`analysis/inputs.py` removes the 5 later inputs (H226 to H230), which
are about a writing tool of the author.

## 3. Identification of the author's inputs

Script: `analysis/inputs.py`. Results: `data/derived/human_inputs.jsonl`
(private), `results/inputs/source_audit.json`.

An input is text that the author typed, or an action of the author in a
session. The script uses three rules:

1. **T3 messages.** A T3 message with `createdBy` `user` and the creation
   source `web` or `mobile` is an input (199 messages, 21 of them from
   the phone, without the threads of other providers, the threads about
   the paper and the inputs after the end of the case). Messages with `createdBy` `agent` (3,667) are tasks and
   reports between agents. Two messages with `createdBy` `user` and the
   source `server` are an automatic "Continue where you left off." and a
   relayed agent text. The script does not count them.
2. **Answers.** An answer to an `AskUserQuestion` tool call is an input
   (2, both on the Windows PC).
3. **Interrupts.** A `[Request interrupted by user]` record in a main
   session is an input (15). The 5 interrupts in subagents come from the
   parent agent and are not counted.

Validation. Each prompt in a transcript that came through the SDK must
have a T3 message with the same text. Of 1,818 such prompts, 201 match an
author message, 1,599 match an agent message, and 18 have no match. Of
the 18, 14 are agent tasks with a T3 prefix ("the agent in T3 thread ...
sent this message"), 3 are branch name prompts of T3 and 1 is the brief
of a headless `claude -p` run for the icon design. So T3 has every
prompt that the author typed in the sessions with a transcript.

For each input the script keeps the context: the thread title, the first
message of the thread, the last two agent messages before the input and
the first agent message after it. It links the input to the transcript
prompt with the same text within 10 minutes.

## 4. Coding

Codebook: `analysis/codebook.md`. Results: `results/inputs/`.

The coding is a directed content analysis. The categories come from the
research questions and from a first reading of all messages. They
were fixed before the coding started. Each input gets:

* `category`: the main function (goal, steer, report, question, decide,
  inform, resource, operate, continue, session, interrupt), and `also`
  for further functions.
* `topic`: what the input is about (11 values).
* For `steer` and `report`: the `trigger` (what made the author write
  the input), the `problem` (what the agent did wrong), the `evidence`
  from the transcript, the `agent_reaction` and the `rule_followup` (the
  commit that turned the correction into a rule, from `git log` of the
  rule files).

Procedure:

1. Coder 1 coded all 234 inputs with text (201 after the removal of
   the threads of other providers, the threads about the paper and the
   inputs after the end of the case) (5 batches of 47 in time
   order) with the full codebook. For each `steer` and `report` input,
   coder 1 read the transcript before the input
   (`analysis/context.py <id>`) to find what the agent did.
2. Coder 2 coded `category`, `topic` and `problem` of the same 234
   inputs, without access to the codes of coder 1.
3. A recheck coded each `goal` input (31) for whether it reacted to agent
   behavior. The first pass treated a goal as new when it did not name a
   mistake. Some goals were answers to an agent claim (for example "95 %
   done"). The recheck found 16 such goals.
4. `analysis/summarize_inputs.py` merges the codes. An input is
   "corrective" if it has `steer` or `report`, or if it is a goal that
   reacts to the agent (43 inputs).

Coders 1 and 2 and the recheck were Claude Opus 5.5 agents. Agreement
between coder 1 and coder 2 (`results/inputs/agreement.json`):

| Field | Inputs | Agreement | Cohen's kappa |
| --- | --- | --- | --- |
| category | 201 | 96.5 % | 0.959 |
| topic | 201 | 97.5 % | 0.970 |
| steer or not steer | 201 | 97.5 % | 0.851 |
| problem (both coded steer or report) | 27 | 88.9 % | 0.867 |

Both coders are the same model with the same codebook, so this agreement
measures how stable the codes are, not how two independent people would
code. The author reviewed the codes after the coding and agreed with
them. This review was not blind, because the author saw the codes of
the model. `results/inputs/disagreements.csv` lists the 11 inputs where
the two coders differ in the category or the topic. For these, the
tables use the codes of coder 1.

## 5. Privacy

Scripts: `analysis/privacy_scan.py`, `analysis/redact.py`. Results:
`results/privacy/`.

1. The scan looks for keys and tokens, e-mail addresses, IP addresses,
   host names, home paths, the name of the author, account ids and
   `ssh` commands in each file of `data/raw`. It also checks for the
   exact values of the secrets in the local settings.
2. `analysis/redact.py` writes a copy of `data/raw` to `data/public`
   with the rules of `analysis/redact_rules.json`. It replaces the
   values, removes screenshots and does not copy binary files.
3. `analysis/redact.py --check` scans `data/public` again and lists
   what is left.

Results of the scan of `data/raw` (`results/privacy/scan_summary.json`):

* An access key is in 7 lines of 3 transcripts, because an agent printed
  the environment of Claude Code.
* The IP addresses of the five machines are in 10,830 places, mostly from
  the global rule file that Claude Code puts into each request.
* The e-mail addresses of the two Claude accounts, the user and host of
  the Instabox, the host names of the machines and 217 account ids are in
  the data.
* 3,753 screenshots are in the transcripts.
* No GitHub, PyPI, crates.io or AWS token matched.

After the redaction, the check finds no key, IP address, e-mail address
or host name in `data/public` (`results/privacy/redaction_check.json`).
The hits that are left are the GitHub account name (2,859, in repository
URLs), 1,744 forms of the first name of the author, 404 paths of other
users (for example `/home/runner` of GitHub CI), 217 and 7 lines that
are already redacted, and 23 false hits in base64 data.

The literal rules (host names and user names) are in
`data/private/redact_literals.json`, and the scan terms are in
`data/private/privacy_terms.json`. Both are not in git, because they
contain the private values.

The rules cannot find private text that has no pattern, for example a
personal remark in a prompt. A search of `data/public` found such text:
20 files name other projects of the author, in directory listings and
in lists of T3 threads. Thus, the session records are not published.
The public repository has only the scripts, the codebook and the codes
of each coding pass (`results/coding/*.jsonl`).

Before a later publication of the records, the author must read all
messages and remove this text. This includes the messages in the threads
of other providers and in the threads about the paper, which are in
`data/public` too.

## 6. Limits

* One gap: the first session on the Framework laptop (Section 1).
* The coders are agents. Their codes are a proposal for the author.
* An input can have more than one function. The analysis counts the main
  function. `also` keeps the others.
* The "problem" of a steer is what the context shows. The author may
  have seen more (a window, a figure) than the transcript records.
* The data shows only the inputs in sessions. Work of the author outside
  the sessions (for example a manual change of a GitHub setting, H202)
  is visible only when the author mentions it.

## Candidate sources for the method section

Check each one at the publisher before you cite it.

* Runeson and Höst (2009), guidelines for case studies in software
  engineering, Empirical Software Engineering.
* Hsieh and Shannon (2005), three approaches to qualitative content
  analysis (directed content analysis), Qualitative Health Research.
* Cohen (1960), the kappa coefficient, Educational and Psychological
  Measurement.
* Landis and Koch (1977), the interpretation of kappa values, Biometrics.
