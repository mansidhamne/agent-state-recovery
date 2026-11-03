# Phase 1 report: sources to use

Every path is relative to the repo root. The report outline is in `IMPLEMENTATION_CONTEXT_DOC.md` §18.1. Every number in the report must come from a file below, and the report must name it (`ANALYST_GUIDE.md` §9).

## 1. Use these first

| Path | What it has | Use in the report |
|---|---|---|
| `results/phase1_tables/recovery_table.tex` (and `.md`) | Every metric per mode (M0 to M3) for the 7 matrix cells, in an accidental and an adversarial panel, with notes | The main results table (outline item 6) |
| `results/phase1_tables/stress_table.tex` (and `.md`) | The same metrics for the stress cells FA4, FA5 and FA6, one panel per cell | A second results table, reported apart from the matrix |
| `results/phase1_figures/F1_propagation.pdf` | Which agents read the faulty item or work built on it, per cell, under M0 | Propagation (RQ1, H1) |
| `results/phase1_figures/F2_adversarial_funnel.pdf` | Attack text present, retrieved, attempted, applied, for FD1 and FD2 | Unsafe actions, and "model declined" kept apart from protection |
| `results/phase1_figures/F3_correct_vs_cost.pdf` | Share correct against cost per mode: matrix accidental, matrix adversarial, stress | Recovery correctness and cost (RQ2, H2a to H2c) |
| `results/phase1_figures/F4_example_trace.pdf` | One task (T03, FA1, rep 0): the faulted run and its M1 rerun, action by action | The worked example of a fault spreading, and of M1 following the newer post |
| `results/phase1_figures/F7_hidden_effects.pdf` | Wrong orders, orders sent twice, tainted posts left live, calls redoing valid agents | What `pass` does not show (RQ5, H5), and the case for Phase 2 |
| `EXPERIMENT_ANALYSIS.md` | The append-only log, E00 to E30: what was run, expected, observed, and what it meant | The source of every finding and its reasoning. Cite entries by number (E24 matrix, E25 why M1 recovers, E26 and E27 new metrics, E28 and E29 stress block, E30 wasted work and figures) |
| `IMPLEMENTATION_CONTEXT_DOC.md` | The design: questions and hypotheses (§3), world and agents (§6), tasks, oracle and faults (§7), metrics (§8), recovery modes (§10), controls (§12), decision log (§17), report plan and threats to validity (§18) | Sections 1 to 5 of the report, the limitations, and the reasons for each design decision |

## 2. Tables and data behind the figures

All in `results/phase1_tables/`. Built from all 768 runs in `runs/main/` (E30).

| File | What it has | Use |
|---|---|---|
| `runs.csv` | One row per run with every metric (pass, checks, unsafe bits, wrong and duplicate orders, tainted posts, valid and wasted work, calls, tokens, cost, time, `fault_set`) | Any number not in the summary tables; min and max values |
| `clean_success.csv` | Pass rate per task on the 30 clean runs | Clean success and the T04 noise (outline item 6) |
| `clean_by_mode.csv` | Clean runs under M0 and M3: pass, calls, verifier calls, cost | M3's cost when nothing is wrong |
| `propagation.csv` | Dependence, affected stages and pass rate per cell under M0, split by `fault_set` | Propagation by cell |
| `unsafe_ops.csv` | Attack funnel per adversarial cell and mode | Unsafe actions |
| `recovery_by_mode.csv` | Recovery metrics per `fault_set`, fault class and mode | Recovery comparison, with exact means |
| `run_status.csv` | Runs per mode and status (`ok`, `degraded`) | Did the runs finish (FA3 timeouts explain the degraded runs) |
| `trace_checks.json` | Numbers read from the traces: who retrieved the faulty post, M1 rerun ranks and wording, M3 rejections with reasons, attack-marker posts with refusal words, calls cut off at the token limit | Quotes and counts for the M1, M3 and adversarial findings |

## 3. The system, for the method sections

| Path | What it has | Use |
|---|---|---|
| `prompts/A1_fault_analyst.md` to `prompts/A5_dispatch_parts.md` | The five agents' system prompts (frozen at the end of Phase 1C) | Describe each agent's role. Hashes are in E23 |
| `prompts/verifier.md` | The M3 verifier prompt | Describe M3 and its limit (E20) |
| `config/model.yaml` | Model id, temperature 0, `max_tokens` 1024, seed | Setup and controls |
| `config/phase1.yaml` | Eval and dev tasks, the 7 cells, the stress cells, 3 reps, step cap 12, `bm25_k` 4 | Setup and controls |
| `tasks/T03/` (any of `T03` to `T08`) | `task_spec.md` (what agents are told), `oracle.json` (the truth), `world/inputs/` (the invented manuals and records), `fault_variants/` | A worked example of the workload, and the oracle |
| `src/mccr/faults.py` | How each fault is injected | Fault injection section |
| `src/mccr/recovery.py` | What M1, M2 and M3 do | Baselines section |
| `src/mccr/oracle.py` | The checks and the unsafe bits | Oracle section |
| `src/mccr/metrics.py` | How each metric is computed from the logs | Metric definitions, including the any-read lineage rule |

## 4. Supporting material

| Path | What it has | Use |
|---|---|---|
| `docs/M4_VALUE.md` | Where M4 must beat M1, M2 and M3, apart from cost, with Phase 1 numbers | The Phase 2 direction (outline item 7) |
| `docs/PROJECT_GUIDE.html` | A plain-language guide to the whole project, with a timeline of every log entry | Background reading. Not a source of numbers |
| `docs/replay/replay.html` | The animated board replay of selected runs | Presentation and demo, and a check of the F4 story |
| `ANALYST_GUIDE.md` | How to read run folders and results, and the report rules (§9) | Rules for numbers, reps and limitations |
| `aws/README.md` | How the runs were made: instances, setup, sync | The reproducibility appendix |
| `README.md` | Quickstart | The reproducibility appendix |
| `scripts/run_matrix.py`, `scripts/analyze.py`, `scripts/report_tables.py`, `scripts/figures.py`, `scripts/trace_checks.py` | The commands that produced every run, table and figure | The reproducibility appendix. Commands are in E24, E29 and E30 |
| `results/phase0_probe_ec2.json`, `results/poc_gate.json`, `results/poc_gate2.json` | The model probe and the two go/no-go gates on the dev tasks | Method history only (E01, E03, E08). Dev-task numbers are never reported as results |

## 5. Do not use for report numbers

| Path | Why |
|---|---|
| `results/matrix_tables/`, `results/matrix_tables2/`, `results/stress_tables/`, `results/shakeout_tables/` | Earlier builds. Their values match `results/phase1_tables/`, but they lack later columns. Use `phase1_tables` |
| `results/poc_tables/`, `results/poc2_tables/`, `results/m3smoke_tables/`, `results/m3fix_tables/` | Dev tasks T01 and T02 only. Method history, not evaluation results |
| Any output of `--backend scripted` | The scripted crew is for debugging only (D11). It says nothing about the model |
| `runs/` | Raw logs, not in git, about 768 folders on `mccr-2` and the Mac. The source of the tables, not something to cite directly. Cite the table or the log entry instead |

## 6. Points the report must state (from the sources)

- Accidental and adversarial faults are always shown apart. The stress cells are shown apart from the matrix (E28).
- Every number gives its run count, and min to max where it is a mean (`ANALYST_GUIDE.md` §9).
- "Model declined" is the model's behaviour, not a protection (doc §7.2).
- The new metrics were added after the matrix results (E26). `pass` stays the main measure.
- The stress cells were designed after the matrix, to test E25's explanation, with expectations written first (E28).
- FA5's "consistent" claim kept the component's plain-word description, which is how M3 caught some runs (E29).
- Limits: synthetic domain, one hosted model, 6 tasks, 3 reps, a small board where each search returns about 80% of it, and a 5-agent chain (E25, E30, doc §18.4).
- The incident used as motivation is marked [VERIFY] in the doc. Check its sources before citing it.
- All procedures and data are invented and are not real maintenance guidance.
