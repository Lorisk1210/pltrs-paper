# Collection of the raw data

These commands copied the session data into `data/raw/` on 2026-11-23.
`data/raw/` is not in git. It has private data.

## Claude Code transcripts

MacBook and Framework laptop (rsync):

```sh
rsync -a --include='*plt-rs*/***' --include='*pltrs-icon*/***' --exclude='*' \
  ~/.claude/projects/ data/raw/macbook/claude/
rsync -a --include='*plt-rs*/***' --exclude='*' \
  <framework>:.claude/projects/ data/raw/framework/claude/
```

MS-02 has no rsync. Use tar over ssh:

```sh
ssh <ms02> 'cd ~/.claude/projects && tar czf - ./*plt-rs*' \
  | tar xzf - -C data/raw/ms02/claude
```

Windows PC (the tar of Windows):

```sh
ssh <windows> 'cd /d %USERPROFILE%\.claude\projects && tar czf - C--Users-<user>--worktrees-plt-rs-winrel C--Users-<user>-dev-plt-rs D--dev-plt-rs' \
  | tar xzf - -C data/raw/windows/claude
```

## T3 Code databases

`t3_export.py` opens the database read-only and writes the pltrs rows.
Copy the script to each machine, run it, and copy the result back:

```sh
python3 analysis/collect/t3_export.py ~/.t3/userdata/statev2.sqlite data/raw/macbook/t3/t3_pltrs.jsonl.gz
scp analysis/collect/t3_export.py <host>:/tmp/
ssh <host> 'python3 /tmp/t3_export.py ~/.t3/userdata/statev2.sqlite /tmp/t3_pltrs.jsonl.gz'
scp <host>:/tmp/t3_pltrs.jsonl.gz data/raw/<machine>/t3/
```

On the Windows PC, use `py` instead of `python3` and the path
`C:\Users\<user>\.t3\userdata\statev2.sqlite`.

## Codex

One Codex session on MS-02 has the pltrs directory as its working
directory:

```sh
f=$(ssh <ms02> 'grep -l -m1 "plt-rs" -r ~/.codex/sessions --include=*.jsonl')
scp <ms02>:$f data/raw/ms02/codex/
```

No other machine has a Codex session in pltrs.

## Before a new collection

The Framework laptop and the Windows PC use the default
`cleanupPeriodDays` of 30. Claude Code on these machines deletes
transcripts after 30 days. Set a larger value in `~/.claude/settings.json`
on both machines to keep the remaining transcripts.
