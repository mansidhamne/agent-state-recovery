# What selective recovery (M4) must do better, apart from cost

This note says where M4 must beat M1, M2 and M3 in Phase 2, and which Phase 1 numbers show the gap. M4 is not built yet. Every number below comes from the Phase 1 matrix or the stress block (`EXPERIMENT_ANALYSIS.md` E24 to E29).

## The four methods in one line each

| Method | What it does |
|---|---|
| M1 restart, keep board | Reruns every agent. Keeps the board and the files as they are |
| M2 restart, wipe all | Reruns every agent. Wipes the board and restores the input files |
| M3 always-verify | Asks the model to check every write before it happens |
| M4 selective recovery | Uses the record of who read what. Removes only the bad items and what was built on them, restores bad files, and reruns only the affected agents |

## Where M4 must win

| What to measure | M1 | M2 | M3 | What M4 must show |
|---|---|---|---|---|
| **Correct after a fault that stays in the world** (FA4, corrupted file) | 0 of 18 | 18 of 18 | 0 of 18 | Correct, like M2. M4 restores the bad file |
| **Correct after a stale post that claims authority** (FA6, "revised diagnosis") | 13 of 18 | 18 of 18 | 5 of 18 | Correct, like M2. M4 removes the stale post |
| **Bad posts left on the board** (tainted posts left live, per run) | 2 to 5 | 0 | 2 to 5 | 0, like M2. Later work cannot read them |
| **Orders sent twice** (duplicate orders) | 18 in the matrix, 6 more in FA4 | 19 in the matrix | none | Fewer than M1 and M2. M4 does not rerun an agent whose order was valid |
| **The same wrong order sent again** | yes: FA4 went from 6 to 12 wrong orders | no | no | No |
| **Valid work kept** (retained valid work) | none: all 5 agents rerun | none: all 5 agents rerun | n/a | More than 0. Untouched agents keep their work |
| **Calls spent redoing valid agents** (wasted work, per run) | about 3 to 6 | about 3 to 6 | n/a | Close to 0 |
| **Work redone** (recomputed stages) | 5 of 5 agents | 5 of 5 agents | n/a | Only the affected agents |
| **Extra cost on runs with no fault** | none | none | about +44% calls on every run | None. Keeping the record costs logging only, no model calls |

## What M4 cannot do

- **It cannot undo a sent message.** 7 wrong orders in the matrix stay after every method. M4 must list them as irreversible, like the others.
- **It needs to be told which item is bad.** M4 starts from the faulty item `F` (invariant I9). M3 tries to find bad items itself. The two do different jobs.
- **It saves little on a small, linear crew.** With 5 agents in a chain, a fault at A1 reaches 4 of 5 agents. The saving grows when the work is wider, for example several aircraft on one board (planned for Phase 2).

## In one sentence

M4 must be as correct as wipe-all (M2), leave as clean a board as M2, send fewer duplicate orders than M1 or M2, keep the valid work that M1 and M2 throw away, and cost nothing extra on runs with no fault, unlike M3.
