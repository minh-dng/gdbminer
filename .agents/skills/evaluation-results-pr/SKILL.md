---
name: evaluation-results-pr
description: Checklist for `docs(evaluation)` pull requests that publish hardware evaluation results under `evaluation/`. Use when the user asks to upload, publish or document evaluation results, add trial folders, or open a docs(evaluation) PR.
---

# Evaluation results PR

Publishes finished trial folders from a run checkout. The PR is thesis documentation: every number
comes from the files, every omission is stated. Example: PR 81 (ESP32-C3 calc trial-1 to trial-4).
Work through the steps in order. A PR may state "no abnormalities" only after step 6.

## 1. Scope and sources

- [ ] Copy result folders unchanged from the run checkout. Treat that checkout as read-only: do not
      commit in it, modify it, or touch its `output/`, runners, boards or processes while it runs.
- [ ] Exclude source code changes, `example_programs/**`, other targets' folders and anything under
      `output/`.

## 2. Layout per trial folder

`evaluation/<platform>_applications/<platform>_<target>/trial-<n>-<setup>/` holds:

- `seed.N.in.trace` (one per seed; 20 for calc), `trace.json`, `trees.json`, `method_trees.json`,
  `loop_trees.json`, `mined_g.json`, `parsing_g.json`, `evaluation.json`, `out.log`
- `run/`: `configuration.toml`, `build.options.json`, `flash.log`, `trace.log`, `mine.log`,
  `eval.log`, `seeds.sha256`, `eval.sha256`, `state.txt`, `times.txt`, and `build.log` when it
  exists

- [ ] File count equals the source. Compare the file list with an existing folder of the same
      target.

## 3. Which logs and files to include

- [ ] `*.log` is in `.gitignore`: use `git add -f`, then check that the staged file count equals the
      file count on disk (PR 81: 39 per folder, 40 with `build.log`).
- [ ] Leave out `run/git-status.txt` (a local worktree listing). Keep the Git lines of
      `run/state.txt` unchanged; its `git status: N changed paths (see git-status.txt)` line then
      points to an unpublished file. Say so in the README and the PR, and keep the counts.
- [ ] Leave out resume material (`resume-*`, resumed logs, `runner.log`, resume scripts) and
      trace-only or never-mined attempts. Exception: the published run itself was a documented
      resume; then the PR explains it. Check:
      `find <folders> -iname '*resume*' -o -name runner.log`.
- [ ] `build.log`: include it only if the source folder has it. Never copy one from elsewhere
      (`output/<trial>/builds/`, a backup snapshot) into a folder whose run did not produce it. If
      it is missing, say so and point to the ELF sha256 in `state.txt` and to `build.options.json`.
      Compare a present `build.log` with the same setup's earlier one (`cmp`); state if identical.
- [ ] Keep absolute paths in run files, as in existing results, and say so in the PR.
- [ ] No secrets: grep for token, password and key patterns (ignore `token_generalizer` log lines).

## 4. Verify every number from the files

Not from the brief or from chat.

- [ ] `evaluation.json`: precision, recall, f1, `no_tested_inputs`, `tracing.duration` (with the
      seed count), `mining.duration`, `mining.requests` (methods, loops, tokens, total),
      throughput, evaluation duration.
- [ ] `run/times.txt`: all exit codes 0; row order shows reflashes and split runs.
- [ ] `run/state.txt`: date is the start of the run; git HEAD can differ between trials; ELF sha256
      per setup; board and port.
- [ ] Run dates from log timestamps. A run can be split (tracing days before mining).
- [ ] `Mining time` in `mine.log` matches `mining.duration`; the result line in `eval.log` matches
      `evaluation.json`.
- [ ] Do not generalise across trials. State what matched (for example only precision, recall and
      F1) and what did not (query counts, mining time, a manual resume).

## 5. Provenance gaps: state plainly when they apply

- [ ] The `openocd:` line of `state.txt` holds a Python traceback instead of the version. The
      version is in `eval.log`; reuse the wording of PR 80.
- [ ] The precision-query count is not recorded (`PRECISION_SET_SIZE`, default 1,000, absent from
      `evaluation.json`), so precision stays provisional unless a file shows the count.
- [ ] The recorded git HEAD may lack later tracer fixes. Check with
      `git merge-base --is-ancestor <fix> <HEAD>` and say the effect is not assessed.
- [ ] Mining time can vary a lot. Compare throughput (requests per second) before blaming query
      counts.

## 6. Anomaly scan

Per folder, before writing "no abnormalities":

- [ ] `grep -E 'ERROR|Traceback|Timeout|restart|abort|Stack canary|LIBUSB_ERROR|failed'` over
      `trace.log`, `mine.log`, `eval.log`, `flash.log`.
- [ ] Count `OpenOCD startup retry` per log. Report recoverable retries in the PR.
- [ ] `Start generating trace` count equals `Write trace of` count equals the seed count.
- [ ] No `Generated non accepting input` in `eval.log`.
- [ ] `No suitable loop` miner warnings compared with earlier trials.
- [ ] Compare grammars across trials by loading `parsing_g.json` and sorting the rule alternatives.
      Raw bytes differ because the miner is unseeded.

## 7. README

- [ ] `evaluation/<platform>_applications/README.md` keeps its existing paragraphs and gains a short
      paragraph and a table for the new trials: run dates (local time zone), inputs, tracing and
      mining hours, setups, ELF hashes, code revision, provenance gaps.
- [ ] Wrap at 100 characters, tables excepted:
      `awk 'length > 100 && !/^\|/ {print FILENAME": "FNR}' <README>`.

## 8. Git

- [ ] One commit per trial folder (or per setup pair), one for the README. Conventional messages:
      `docs(evaluation): add ESP32-C3 calc trial-2 for one cable`.
- [ ] PR title: `docs(evaluation): add ESP32-C3 calc trial-1 to trial-4 results`. Base `main`.
- [ ] No co-author line, no agent name in branch, commits or PR.
- [ ] If history needs rewriting before anyone reviewed it, amend and
      `git push --force-with-lease`; after `filter-branch`, delete `refs/original`.
- [ ] `git diff --stat origin/main` shows only `evaluation/<platform>_applications/` paths;
      `git status` is clean; no merge commits.
- [ ] Do not touch `docs/thesis` or other PRs. Do not merge.
