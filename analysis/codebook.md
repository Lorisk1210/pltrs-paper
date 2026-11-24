# Codebook for the inputs of the author

This codebook defines the codes for each input of the author. An input is
one message that the author typed in T3 Code, one answer to an
`AskUserQuestion` tool call, or one interrupt. `analysis/inputs.py` collects
the inputs into `data/derived/human_inputs.jsonl`. Each input has an id
`H001` to `H249`.

Give each input one value for each field below. Code what the input does,
not what the agent did after it. If an input does two things, give the
main function in `category` and the other functions in `also`.

## Field `category`

The main function of the input. Exactly one value.

| Code | Definition | Examples | Not this code |
| --- | --- | --- | --- |
| `goal` | Sets a new goal, a new target or a new requirement for the project or for one work stream, or makes the goal larger. | "Build matplotlib completely in Rust ..."; "Continue until it is 100 %, but it should also pass the full test suite of matplotlib"; "pltrs must be faster than matplotlib across the board". | A message that only says that the agent is wrong about the goal is `steer`. |
| `steer` | Corrects or redirects the current work, because the agent did something that the author did not want, or did not do something that the author expected. The input refers to something that the agent did, said or planned. | "The figures still look the same as matplotlib"; "Progress has slowed down, the changes take hours but are small"; "You are the agent making decisions, decide this yourself". | A new requirement without a reference to agent behavior is `goal`. A failure that the author saw in the software or in CI, with no claim about the agent, is `report`. |
| `report` | Reports a defect, a failed check or a wrong result that the author observed: in a manual test, in GitHub CI, on PyPI or on a machine. | "The subplot configuration tool does not work"; "macos universal2 failed"; a pasted error log. | A report of a resource problem that the agent caused (OOM, full disk) is `steer` with `problem` `resource_misuse`. |
| `question` | Asks for information: status, progress, an estimate, an explanation or a cost. The input does not tell the agent to change its work. | "How much % is done?"; "Do the tests fail because the implementation is wrong?"; "explain this". | A question that is a disguised correction ("U mean it's done completely? The goal is reached?") is `steer`. |
| `decide` | Chooses between options that the agent gave, or answers a question of the agent. | "Go with Icon E"; "go with your recommendation for the license"; "1. yes 2. I am at the Mac". | |
| `inform` | Gives a fact that the agent cannot get itself and that is not a defect: access, the state of a machine, a file location, the result of a manual step. | "ssh ... you should be able to do this now"; "its now there"; "done". | Machine availability is `resource`. |
| `resource` | Gives, limits or takes back compute: machines on or off, the number of subagents, the model or effort, usage limits, "stop for today". | "You can run up to 5 subagents"; "Windows PC is on as well now"; "stop all work"; "now you are Fable 5.2". | If the limit reacts to a mistake of the agent (OOM, full disk, wrong machine), use `steer`. |
| `operate` | Tells the agent to do one operational action: commit, push, publish, run a command, set up a tool, make a release step. | "push to github"; "Commit and push"; "you run it"; "publish them". | |
| `continue` | Tells the agent to go on, with no new content. | "continue"; "Continue"; "continue!". | "Continue, but ..." with new content gets the code of the new content. |
| `session` | Controls the agent session itself: a slash command. | `/compact`; `/usage`. | |
| `interrupt` | The author stopped the running turn. Only for inputs of kind `interrupt`. | | |

## Field `also`

A list of other `category` codes that the input also has. Empty list if
none.

## Field `topic`

What the input is about. Exactly one value.

| Code | Definition |
| --- | --- |
| `scope` | Which matplotlib features pltrs must have, completeness, parity, drop-in use. |
| `correctness` | Tests, conformance with matplotlib, bugs, failing checks. |
| `performance` | Speed and memory of pltrs, benchmarks. |
| `look` | The visual design: the modern look, the matplotlib look, icons. |
| `code_quality` | Code style, structure, naming, dependencies. |
| `docs` | Documentation, README, writing style, rule files. |
| `release` | Packaging, CI, GitHub, PyPI, crates.io, license, versions. |
| `infrastructure` | Machines, disk, memory, parallel agents, models, usage limits. |
| `process` | How the agent organizes its work: subagents, decisions, reports, git workflow, when to ask. |
| `meta` | Not the work on pltrs: cost and progress estimates for the author, the paper, tools of the author. |
| `none` | No topic (`continue`, `session`, `interrupt`). |

## Fields for `steer` and `report`

Fill these fields if `category` or `also` has `steer` or `report`. Else
set them to `null`.

### `trigger`

What made the author write the input. One value.

| Code | Definition |
| --- | --- |
| `agent_message` | A message or a claim of the agent, for example "done" or a status table. |
| `own_use` | The author used or looked at pltrs: a figure, a window, a script. |
| `external_check` | GitHub CI, PyPI, crates.io or another tool outside the session. |
| `resource_event` | Out of memory, full disk, usage limit, a machine that hangs. |
| `progress` | The author saw slow progress or too little output. |
| `preference` | The author changed their mind. No problem of the agent. |

### `problem`

What the agent did wrong. One value. Read the context (the agent
messages before the input, and the transcript) to decide.

| Code | Definition |
| --- | --- |
| `premature_completion` | The agent said that the work or the goal is done, or stopped, while the goal was not reached. |
| `scope_narrowing` | The agent made the goal smaller: it skipped hard parts, deferred them, called them out of scope or read the goal narrowly. |
| `misread_intent` | The agent understood a request differently from what the author meant. |
| `wrong_priority` | The agent worked on things of low value, or its progress was too slow for the effort. |
| `quality` | The output has low quality: unclear text, bad names, code smells. |
| `defect` | pltrs has a bug, a crash or a visible difference. |
| `resource_misuse` | The agent used machines badly: out of memory, full disk, the wrong machine or drive, too many or too few parallel agents. |
| `rule_violation` | The agent did not follow a rule that the author gave before. |
| `asked_unnecessarily` | The agent asked the author for a decision or an action that it could do itself. |
| `tooling_failure` | The agent or its tools failed (a crash, an API error, a lost subagent), with no wrong decision of the agent. |
| `none` | No problem of the agent (`trigger` is `preference`). |

### `evidence`

Two to four sentences: what the agent did or said before the input, with
the time and the place in the transcript. Write only what the context
shows. If the context does not show it, write "not in the data".

### `agent_reaction`

One value: `accepted` (the agent agreed and changed its work), `argued`
(the agent disagreed or explained why it was right), `partial` (the agent
agreed in part), `no_reply` (no agent message follows), `unclear`.

### `rule_followup`

If the correction became a rule in `AGENTS.md`, `CLAUDE.md` or
`CONTRIBUTING.md` of `~/dev/plt-rs`, give the commit hash and the rule in
a few words. Search with `git -C ~/dev/plt-rs log -p --since <date> --
AGENTS.md CLAUDE.md CONTRIBUTING.md`. Else `null`.

## Other fields

* `confidence`: `high`, `medium` or `low`. How sure you are of `category`.
* `quotable`: `true` if the text is about the project and has no private
  data (no key, password, IP address, host name, e-mail address, account
  name or personal matter). Else `false`.
* `note`: one sentence, only if a decision was hard. Else `null`.

## Decision rules

1. Read the input, the agent messages before it and the agent message after it.
2. If the input only says to go on, code `continue`, even if it has a
   small addition such as "!" or "(now you are Fable 5.2)". If the
   addition sets a model or a machine, code `resource`.
3. If the input refers to something that the agent did and wants it
   different, code `steer`, even if it is a question in form.
4. If the input sets something new that the agent could not know, and it
   does not refer to agent behavior, code `goal`.
5. If two codes fit equally, take the one that is higher in the table of
   `category`, and put the other in `also`.
