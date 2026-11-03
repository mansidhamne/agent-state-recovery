# agent-state-recovery

**When Restart Is Not Recovery: Provenance, Persistent Faults, and Shared-State Agents**

This repository studies how faults spread through a small team of tool-using agents that share a retrieval-backed board, and what recovery must restore to make that team safe again. Currently, the domain is a fully synthetic aircraft-maintenance-control workflow.

The central result is that a simple restart can restore a correct final answer while retaining contaminated shared state, repeating an irreversible mistake, or failing again when the corrupt input persists. A wipe-and-restore baseline (M2) cleared the board and recovered all stress cases; a restart that keeps state (M1) did not.

## What is in this repository

- A five-agent ReAct-style crew with a shared BM25 board, file tools, simulated external messages, provenance logs, and a programmatic oracle.
- Eight generated synthetic tasks: T01--T02 for development and T03--T08 for evaluation.
- Accidental, adversarial, timeout, persistent-reference, and stale-revision fault injections.
- Recovery baselines: M0 (no recovery), M1 (restart and keep board), M2 (restart and wipe/restore), and M3 (always verify writes).
- Phase 1 result tables, report figures, a trace replay, unit tests, and an append-only experiment log.

Nothing in this repository contacts an aircraft, vendor, or production system. “Secrets” are invented strings like `CANARY-T03-...`, stored only inside a synthetic task folder. They are not real passwords, API keys, or private data. Even the external sends are local files in an `outbox/` directory.

## Demo

Open the interactive agent-board replay (replay/replay.html) to watch how information, faults, and recovery actions move through the team.

## Key findings

The primary matrix uses six evaluation tasks, three repetitions per fault cell, and `api-glm-5.3-flash` at temperature 0.

- A single plausible but wrong diagnosis (FA1) propagated in 18/18 runs and caused six unsafe releases in the two synthetic HOLD tasks.
- In the base matrix, M1 restored final oracle correctness in 126/126 recoveries, but left tainted posts live in 72 of those successful recoveries and could not retract seven wrong orders already sent.
- The pre-registered stress block identifies the limit of that apparent M1 success: M1 recovered 0/18 persistent corrupted-reference cases (FA4), and duplicated six wrong orders. M2 recovered all 54 stress cases and removed tainted board state.
- An always-verify baseline (M3) cost more and missed the initiating FA1 errors. It caught some stress cases only where the fault left a visible textual inconsistency; it did not catch the internally consistent persistent-input case.
- The adversarial prompts were retrieved by downstream agents but declined by this particular model. This is a finding about model behavior, not evidence of a general defense.



## System at a glance

```text
Synthetic task files ──> A1 diagnosis ──> A2 records ──> A3 plan ──> A4 work order ──> A5 dispatch
                              │                │              │               │               │
                              └──────────────── shared BM25 board + provenance ────────────────┘

Fault injection ──> M0: leave faulted state
                   M1: rerun all agents, keep board/world
                   M2: restore clean world, wipe board, rerun all agents
                   M3: verify every proposed write before it is stored
```



## Setup

Requirements: Python 3.12 and [uv](https://docs.astral.sh/uv/). The pinned Python dependencies are in `requirements.txt`.

```bash
git clone https://github.com/mansidhamne/agent-state-recovery.git
cd agent-state-recovery

uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m pytest
```

The full test suite should pass without an API key. The generated task fixtures are committed, so setup does not need network access after dependencies are installed.

## Run against TritonAI

```bash
export TRITONAI_API_KEY='...'

# Confirm route access, tool calling, seed support, and rate-limit headers.
.venv/bin/python scripts/probe_tritonai.py --model api-glm-5.3-flash

# Start with a small development run in a new directory.
.venv/bin/python scripts/run_matrix.py \
  --backend tritonai --tasks dev --blocks clean,M0,M2,M1,M3 --reps 1 \
  --runs runs/dev-demo
```

For the full evaluation design, inspect `config/phase1.yaml` before running.

## Repository map


| Path                     | Purpose                                                                                                        |
| ------------------------ | -------------------------------------------------------------------------------------------------------------- |
| `src/mccr/`              | Core implementation: agents, board, tools/policy, faults, recovery, oracle, metrics, world state, and logging. |
| `prompts/`               | Role prompts for A1--A5 and the M3 verifier prompt.                                                            |
| `tasks/`                 | Synthetic task generator plus T01--T08 task fixtures, ground-truth oracles, and fault variants.                |
| `config/`                | Pinned model parameters and the Phase 1 task/cell/mode configuration.                                          |
| `scripts/run_matrix.py`  | Runs M0/M1/M2/M3 experiment blocks and writes a folder per run.                                                |
| `scripts/analyze.py`     | Converts finished run logs into CSV summary tables.                                                            |
| `tests/`                 | Unit and integration tests for the harness and recovery mechanisms.                                            |
| `results/`               | Committed summaries, tables, and figures from completed runs.                                                  |
| `docs/replay/`           | Self-contained browser replay of representative traces.                                                        |
| `EXPERIMENT_ANALYSIS.md` | Append-only experiment log: settings, expectations, results, interpretations, and caveats.                     |




## Modes and fault sets


| Item     | Meaning                                                                                                                      |
| -------- | ---------------------------------------------------------------------------------------------------------------------------- |
| M0       | Faulted run without recovery.                                                                                                |
| M1       | Rerun all five agents while keeping the board and world state.                                                               |
| M2       | Restore the run-start world snapshot, wipe the board, replace the faulty input with its clean version, and rerun all agents. |
| M3       | Fresh faulted run with a verifier invoked before every proposed board/file write.                                            |
| FA1--FA3 | Base accidental faults: wrong claim, stale post, and missing invocation.                                                     |
| FD1--FD2 | Base adversarial injections through a vendor feed or a spoofed board post.                                                   |
| FA4--FA6 | Separately reported stress faults: persistent corrupted reference, transient consistent claim, and late wrong revision.      |


