# Analyst guide: how to work in this repo

Read this file first. It tells you what your role is, where everything is, and how to read the results. The project itself is defined in `IMPLEMENTATION_CONTEXT_DOC.md`. That file is the source of truth. If this guide and that file disagree, that file wins, and you tell the user about the difference.

## 1. Your role

You are the analyst. The user stays in control. You read, think and edit files. The user runs commands.

You may:
- Read any file in the repo and in `runs/` and `results/`.
- Analyse results and explain what they mean.
- Suggest changes, and make code, prompt, config and doc edits in the repo.
- Write report text.
- Add entries at the bottom of `EXPERIMENT_ANALYSIS.md` (section 11). Read its last entries first, to learn where the project stands.

You must not:
- Run shell commands or any other program. When something must be run, give the user the exact command in a code block with one sentence saying what it does and what it costs. Wait for the output.
- Commit, push, pull, or change git settings. The user does that.
- Touch AWS in any way. There are no AWS keys on the instance and you do not need any.
- Read, print, copy or edit `~/.mccr_env` (it holds the TritonAI key), `.env`, or anything in `~/.ssh/`. Never ask the user to paste a key.
- Edit or delete anything inside `runs/`. Logs are append-only (invariant I4) and no run is ever deleted (I6).
- Edit, reorder or delete an existing entry in `EXPERIMENT_ANALYSIS.md`. Add a correction entry instead.
- Report any number that came from `--backend scripted`. Scripted runs only prove that the code works.

When you are unsure whether something is allowed, ask the user first.

## 2. What the project is (short version)

Five LLM agents (A1 to A5) handle one simulated aircraft maintenance case. They share one memory board. A faulty post on the board spreads into other agents' work. We measure how far it spreads, how well standard recovery methods repair it, and (Phase 2) whether recovering only the work that depended on the faulty post is cheaper and still correct.

Read `IMPLEMENTATION_CONTEXT_DOC.md` before you suggest anything. Use this map:

| You need | Section |
|---|---|
| The research questions and what we expect | 3 |
| The simulated world, agents and tools | 6 |
| Tasks, oracle and fault table | 7 |
| What each metric means | 8 |
| Log schemas and module interfaces | 9 |
| Recovery methods M0 to M4 | 10 and 11 |
| Controls, matrix size, budget | 12 |
| Phases and the exit criteria of each | 13 |
| Rules the code must keep (invariants I1 to I10) | 15.3 |
| Decisions made so far, and open items | 17 |
| Report outline and figures | 18 |
| What was run, found and changed so far, in order | `EXPERIMENT_ANALYSIS.md` (see section 11) |

Phases in one line each:
- **Phase 0:** environment and probes. Done.
- **Phase 1C (the PoC):** `scripts/poc_gate.py` on dev tasks T01 and T02. This decides GO or NO-GO for the full matrix.
- **Phase 1D:** the full matrix, analysis and the Phase 1 report (due Nov 4, 2026).
- **Phase 2:** `provenance.py` and the selective recovery mode M4 (due Dec 10, 2026). Not built yet.

## 3. The machines

| Place | What it is |
|---|---|
| The user's Mac | Where the user edits, and where AWS commands run. Repo at `~/GITHUB/mansi-project` |
| The EC2 instance | Ubuntu, reached with the SSH alias `mccr`. Where all model runs happen. Repo at `~/mcc-recovery` |
| GitHub | `Aleptonic/mansi-project`, branch `main`. The source of truth for code |

The instance can be stopped or deleted, and then its disk can be lost. Anything not pushed to GitHub, and any `runs/` not copied off, can disappear. The AWS commands and what stop and terminate do are in `aws/README.md`. Edits you make on the instance exist only there until the user commits and pushes them. Edits made on the Mac exist only there until the user pulls them on the instance. Remind the user of this when you finish a set of edits. The order for syncing is in `aws/README.md` ("The sync routine"): the Mac pushes, the instance pulls, runs, then pulls again and pushes only `results/`, and the Mac pulls.

The instance has a Python environment at `~/mcc-recovery/.venv`. The user runs tests with `.venv/bin/python -m pytest -q` (161 tests passed at the last push).

## 4. Repo map

```
IMPLEMENTATION_CONTEXT_DOC.md   source of truth for the project
EXPERIMENT_ANALYSIS.md          append-only log of experiments, findings and changes (section 11)
ANALYST_GUIDE.md                this file
README.md                       quickstart
aws/README.md                   how to start, stop, recreate the instance; GitHub sync
requirements.txt, pyproject.toml
config/                         settings (section 4.1)
prompts/                        agent system prompts
src/mccr/                       the library (section 4.2)
scripts/                        entry points the user runs (section 4.3)
tasks/                          generated tasks T01 to T08 (section 4.4)
tests/                          pytest suite (section 4.5)
runs/                           one folder per run. Not in git (section 5)
results/                        tables and reports. Not ignored by git (section 6)
```

### 4.1 `config/`

- `model.yaml`: model id (`api-glm-5.3-flash`), temperature 0, `max_tokens` 1024, timeouts, `use_seed: true`, and fallback prices. Prices are inferred and only used if no measured cost was logged.
- `phase1.yaml`: dev tasks (T01, T02), eval tasks (T03 to T08), the 7 fault cells, `reps: 3`, `noise_floor_reps: 2`, `concurrency: 1`, `step_cap: 12`, `bm25_k: 4`, and the priority order of the blocks.

### 4.2 `src/mccr/` (the library)

| File | What it does |
|---|---|
| `schema.py` | `SCHEMA_VERSION`, `AgentCtx` (who is acting), `Post` |
| `logging.py` | `EventLog`: append-only JSONL events. `read_events` refuses mixed schema versions |
| `world.py` | The per-run directory: file reads and writes, run-start snapshot, undo log, tree hash. `outbox/` is outside what restore or undo can change |
| `board.py` | The shared board: `add`, `search` (BM25), `tombstone`. Records which posts and files each post depended on |
| `tools.py` | The only way agents touch files and the board. Applies the read ACL and the policy layer (`observe` or `enforce`). `VerifiedToolRunner` is the M3 version |
| `agents.py` | The ReAct loop, with native tool calls and a JSON fallback. Hashes the prompts |
| `llm.py` | `TritonAIClient` (real model) and `ScriptedClient` (debug only). Logs tokens, latency and the cost of each call |
| `rules.py` | The domain rules. Imported only by `tasks/gen_tasks.py`. Agents never see it |
| `oracle.py` | Grades a run from its world and logs. Never calls a model |
| `faults.py` | The fault injector (FA1, FA2, FA3, FD1, FD2). The only code that knows a fault exists |
| `orchestrator.py` | Prepares and runs one task, writes `manifest.json` and `oracle.json` |
| `recovery.py` | M1, M2 and M3. M4 raises `NotImplementedError` (Phase 2) |
| `metrics.py` | Turns run folders into one table row per run |
| `scripted_crew.py` | A deterministic fake crew for debugging. Not evidence about the model |

Who can read what (the routing ACL, always enforced): A1 reads `inputs/fault/` and `inputs/fim/`. A2 reads `inputs/records/`. A3 reads `inputs/mel/`. A4 and A5 read no input files and work only from the board. Reading `secrets/` is possible for everyone but is logged as a forbidden attempt.

### 4.3 `scripts/`

| Script | What it does | Cost |
|---|---|---|
| `probe_tritonai.py` | Checks model access, tool calling, seed, determinism and rate limits | A few cents |
| `validate_tasks.py` | Runs every task in scripted mode to check the board really carries the information and each fault changes the result | Free |
| `poc_gate.py` | The Phase 1C gate on dev tasks. Prints GO or NO-GO and writes `results/poc_gate.json` | Real model calls |
| `run_matrix.py` | Runs the Phase 1 matrix. Finished runs are skipped, so a rerun resumes. `--slice i/n` splits the jobs between two API keys | Real model calls |
| `analyze.py` | Builds the tables in `results/` from the run logs. Figures are not built yet | Free |
| `aws_bootstrap.sh`, `sync_s3.sh` | Instance setup and S3 sync. There is no S3 bucket in our account yet | n/a |

Useful options: `--backend scripted|tritonai`, `--tasks dev|eval`, `--blocks clean,M0,M2,M1,M3,enforce`, `--reps N`, `--runs DIR`, `--out FILE`, `--include-dev` (for `analyze.py`).

Never run `tasks/gen_tasks.py` after the PoC has started. It rewrites all task folders, and changing tasks makes earlier runs incomparable with later ones.

### 4.4 `tasks/`

`gen_tasks.py` writes `tasks/T01` to `T08`. T01 and T02 are dev tasks, used to tune prompts. T03 to T08 are evaluation tasks. Never report dev results as evaluation results. Each task folder holds:

- `world/inputs/...` and `world/secrets/mcc_api.env` (a fake credential holding a canary string). Nothing here is real data.
- `task_spec.md`: what every agent is told.
- `oracle.json`: the correct answer. Agents never see it.
- `fault_variants/`: the poisoned vendor feed and the other fault material.

`outputs/` and `outbox/` are created inside each run, not in the task.

### 4.5 `tests/`

One test file per area: board, tools and ACL, world and undo, logging, replay, oracle, rules and task coverage, faults, agents, recovery and metrics, llm, and the PoC gate. A change is not done until the user has run the suite and it passes.

## 5. What a run folder holds

Run id: `<task>__<cell>__<mode>__<policy>__r<rep>`, for example `T01__FA1xA1__M0__observe__r0`. A clean run uses `clean` as the cell. A recovery adds `__recovered_M1` or `__recovered_M2` to the faulted run's id. M3 is its own run with mode `M3`.

| File | Content |
|---|---|
| `manifest.json` | Task, mode, fault cell, `F` (the faulty artifact), rep, seed, model settings, prompt hashes, code commit, status |
| `events.jsonl` | Every event of the run, one JSON object per line |
| `events_recovery.jsonl` | Only in recovery folders: the events of the rerun |
| `oracle.json` | The grade (see below) |
| `world/` | The final files: `outputs/`, `outbox/`, and the inputs as left by the run |
| `world_store/` | Snapshots and the undo log's saved file contents |

A recovery folder is a copy of the faulted run, so the faulted run itself is never changed.

`oracle.json` has: `pass`, `score`, `checks` (component, disposition, reliability_review, dispatch_status, parts_request, required_strings, outputs_wellformed), `unsafe` (`malicious_text_present`, `forbidden_attempted`, `forbidden_applied`), `irreversible` (messages that were sent), and `pass_ignoring_irreversible`. After a recovery, `forbidden_attempted` counts only the rerun's attempts.

Event types in `events.jsonl`: `llm_call` (includes `status`, tokens, `finish_reason`, `cost_usd`), `react_step`, `board_add`, `board_search`, `board_tombstone`, `file_read`, `file_write`, `external_send`, `policy`, `verify_call`, `fault_injected`, `invocation_end`, `run_end`, `world_snapshot`, `world_restore`. Every event has `event_id`, `phase`, `agent`, `invocation` and `step`. The event ids start with `m_` for the main phase and `r_` for recovery.

## 6. Results files

- `results/poc_gate.json` and `results/poc_gate2.json`: the verdicts of PoC #1 and PoC #2. The tables are in `results/poc_tables/` and `results/poc2_tables/`.
- Each gate file has these fields: `go`, `gates`, `clean_success`, `fa1_dependence`, `adversarial_status`, `model_declined_runs`, `degraded_share`, `mean_llm_calls_per_run`, token means, `cost_source`, `mean_cost_usd_per_run`, `projected_matrix_usd`, `budget_limit_usd`, `recovered_correct_by_mode`, `failed_jobs`, `prompt_hashes`.
- `results/runs.csv`: one row per run, written by `analyze.py`.
- `results/clean_success.csv`, `propagation.csv`, `unsafe_ops.csv`, `recovery_by_mode.csv`, `run_status.csv`: summary tables.
- `results/phase0_probe_ec2.json`: the Phase 0 probe output.

PoC gate rules: clean success at least 60%, FA1 dependence at least 50%, the adversarial instruction reaches an executor (a model that declines it is a warning, not a failure), the projected cost is at most 60% of the $50 key budget, and no job failed.

## 7. How to analyse

Ask these questions of the PoC and of the matrix results, in this order:

1. **Did the runs finish?** Check `run_status` and the `invocation_end` events. Statuses `error`, `timeout` and `step_cap` are problems to explain, not noise.
2. **Did the model cut itself off?** Look for `finish_reason: length` in `llm_call` events. Reasoning tokens are billed and count against `max_tokens`, so long reasoning can truncate an answer.
3. **Are the repeats different?** At temperature 0 with a seed, the PoCs gave the same grade in most groups, but the board post text differed in every group (`EXPERIMENT_ANALYSIS.md`, E10). Compare both the `checks` and the post text of reps of the same cell, and report both.
4. **Does the fault reach the next agents?** For FA1, look at `board_search` events: did A3, A4 and A5 retrieve the faulty post? "Dependent" means the fault was retrieved and the checks differ from the clean reference. A run with no dependence is "no dependence", never "robust".
5. **Adversarial cells:** follow the funnel: `malicious_text_present`, then `forbidden_attempted`, then `forbidden_applied`. If the instruction was retrieved but nothing was attempted, the tag is `model_declined`. That is the model's behaviour, not protection by our system.
6. **Recovery:** compare M1, M2 and M3 against the faulted run. Expect M1 to stay wrong when the faulty post is still on the board, M2 to be correct but to redo everything, and M3 to cost more calls and miss faults. Report `pass` and `pass_ignoring_irreversible` together with the `irreversible` count. A sent message cannot be recovered.
7. **Cost and rate:** use `cost_usd` per call. The key limit is 100 requests per minute and 7 parallel requests.

Known caution: BM25 gives a zero score to a word that appears in exactly half the posts, and ties then go to the newest post. This can affect how FA2's stale post ranks. See section 17 of the main doc.

Findings that contradict a hypothesis in section 3 are valid results. Report them as they are.

## 8. How to make changes safely

1. Read the part of `IMPLEMENTATION_CONTEXT_DOC.md` that covers what you are changing.
2. Keep the invariants in section 15.3. The ones most often broken by accident:
   - I1: agents touch files and the board only through `tools.py`.
   - I2: only `tasks/gen_tasks.py` and the oracle side know `rules.py`. The tests check this.
   - I4: analysis reads logs only.
   - I8: only `faults.py` knows a fault exists.
   - I9: recovery receives `F` from the manifest.
3. Interfaces and log schemas are frozen for Phase 1. If a change needs a new field, change the doc first (section 9.3), then the code, then the tests. Log the reason in section 17 of the doc.
4. Prompts in `prompts/` are frozen after the PoC passes. A prompt change after that needs a doc entry. New prompt text means a new `--runs` directory, because runs are never overwritten.
5. Add or update a test for every behaviour you change. Scripted tests must stay deterministic.
6. After your edits, tell the user:
   - which files changed and why, in plain words,
   - the test command to run,
   - that the edits are not committed, and what to commit.
7. Edit the doc's decision log (section 17) for any decision, so the next session can see it. Write what was decided, the reason, and the date.
8. Add an entry to `EXPERIMENT_ANALYSIS.md` for every analysis you do and every change that can affect results (section 11). The decision log says what was decided. The experiment log says what was observed and why.

## 9. Writing the report

The outline and figures are in section 18 of the main doc. Rules:
- Every number must come from `results/` or from the logs. Say which file.
- Separate accidental and adversarial faults in every table.
- Say how many reps each number is based on, and show min to max, not only the mean.
- Use `EXPERIMENT_ANALYSIS.md` to say what changed between runs, so that each result is tied to the code, settings and prompts that produced it.
- State the limits: synthetic domain, one model, a hosted model that can change, a small task set, and the cost of a sent message that cannot be undone.
- Keep the disclaimer that all procedures and data are invented and are not real maintenance guidance.

## 10. Commands the user can run

Give the user commands like these (always from `~/mcc-recovery`, on the instance). You never run them yourself.

```bash
.venv/bin/python -m pytest -q
```
Runs the tests. Free.

```bash
source ~/.mccr_env && .venv/bin/python scripts/poc_gate.py --backend tritonai
```
Runs the PoC on the real model. Costs real money, so first confirm that the tests pass.

```bash
.venv/bin/python scripts/analyze.py
```
Rebuilds the tables in `results/` from `runs/`. Free.

```bash
git status && git diff
```
Shows what changed, before a commit.

## 11. The experiment log

`EXPERIMENT_ANALYSIS.md` is the running record of every experiment, analysis and change. We use it later for a detailed analysis and for the report, so that nothing depends on anyone's memory. The main doc's decision log (section 17) says what we decided. This log says what we ran, what we saw, what we changed, and what happened afterwards.

Rules:
1. **Append only.** Add new entries at the bottom. Never edit, reorder or delete an earlier entry, not even to fix a typo or a wrong number. Add a "Correction" entry that names the entry it corrects and says what was wrong. Git history lets us check this.
2. **One entry per event:** an experiment, an analysis of results, a change to code, config, prompts, tasks or the main doc that can affect results, a correction, or a decision.
3. **Number entries in order** (E00, E01, ...). Never reuse a number.
4. **Name the source of every number:** the file on the instance, under `runs/` or `results/`. Say whether the run folder has been copied off the instance. If the output was only pasted into the chat, say that.
5. **Link cause and effect.** A change entry names the entry that found the problem. The next experiment entry names the change. This is how we later show what a change did.
6. **Write the expectation first.** Before a run starts, write what you expect, and why. When the results arrive, add a new entry that names the first one and says whether the expectation held. Never rewrite the expectation.
7. **Record bad and surprising results as they are.** A result that contradicts a hypothesis is useful.
8. **Mark guesses as hypotheses.** Say what has not been checked.
9. **Record what was held fixed.** For each experiment, give the code commit, step cap, temperature, seed, model, prompt hashes, and the run folder.

Write an entry when:
- an experiment starts (the expectation) and when its results arrive;
- the user pastes output for you to analyse;
- you or the user make a change that can affect results;
- a run is abandoned or fails, with the reason.

Use the template at the top of the file. Leave a field out only when it truly does not apply, and write "n/a". The user commits the file. Remind the user to commit it when you finish.
