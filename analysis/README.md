# Analysis scripts

The scripts read the session data in `data/raw/` and write tables to
`results/`. They need only Python 3 (no packages). `METHODOLOGY.md`
explains the method. `codebook.md` defines the codes.

## Order

Run the scripts from the repository root, in this order:

```sh
python3 analysis/usage.py            # tokens and cost per API response
python3 analysis/coverage.py         # T3 threads without a transcript
python3 analysis/usage_roles.py      # tokens and cost per session role
python3 analysis/t3_turn_check.py    # T3 token counts against the transcripts, per turn status
python3 analysis/inputs.py           # the inputs of the author, with context
# coding: agents write results/coding/*.jsonl (see METHODOLOGY.md)
python3 analysis/summarize_inputs.py # merge codes, agreement, tables
python3 analysis/paper_numbers.py    # numbers and tables of the paper
python3 analysis/code_size.py        # lines of code of pltrs and matplotlib
python3 analysis/figures.py          # figures/*.pdf (draws with pltrs: pip install pltrs)
python3 analysis/privacy_scan.py     # private data in data/raw
python3 analysis/redact.py           # redacted copy in data/public
python3 analysis/redact.py --check   # private data left in data/public
```

`python3 analysis/context.py H023` prints one input with the agent
messages and the transcript around it.

## Files

| File | Purpose |
| --- | --- |
| `collect/t3_export.py`, `collect/README.md` | Copy the raw data from the machines |
| `lib.py` | Shared loaders |
| `pricing.json` | API prices per million tokens |
| `usage.py`, `coverage.py`, `usage_roles.py`, `t3_turn_check.py` | Tokens and cost |
| `inputs.py`, `context.py` | The inputs of the author |
| `codebook.md` | The codes |
| `summarize_inputs.py` | Merge codes, agreement, tables |
| `paper_numbers.py`, `code_size.py`, `figures.py` | Numbers, tables and figures of the paper |
| `privacy_scan.py`, `redact.py`, `redact_rules.json` | Private data |

## Data folders

| Folder | Contents | In git |
| --- | --- | --- |
| `data/raw/` | Copies of the transcripts and T3 exports | No (private) |
| `data/derived/` | Per-response token rows, inputs with context, codes, privacy findings | No (private) |
| `data/public/` | Redacted copy of `data/raw` | No. The redaction does not remove all private data. |
| `data/private/` | Private redaction rules and scan terms (host names, user names) | No (private) |
| `results/` | Tables and summaries | No |
| `results/coding/*.jsonl` | The codes of the agent coders (pass 1, pass 2, goal recheck) | Yes |
