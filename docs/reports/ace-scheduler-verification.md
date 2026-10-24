# Verification of the per-qubit scheduler with event-driven admission (Gate 4)

Code at the commit that adds this file. ACE-internal numbers only; none are comparable with the native
SeQUeNCe backend. Data: `results/ace_scheduler_verification_2026-10-24/matrix_event_admission.csv`.

| Check | Result |
|---|---|
| Full matrix: 10 MQT workloads x on-demand/fixed/dynamic x 2 and 4 memories per core x physics seeds 0, 1 (120 cells), invariant monitor attached | 120 of 120 complete every request, 0 invariant violations |
| Rejections | on-demand: 0 in all 40 cells. With pre-generation (fixed, dynamic): 330 over 80 cells, at most 7 for any one request |
| Longest wait for admission | 14 ms (on-demand, 4 memories) to 78 ms (fixed, 2 memories) |
| GHZ against the legacy manager | event logs identical (on-demand, dynamic); fixed identical apart from reservation labels |
| Random small traces, 1/2/4 memories | all complete, no violation, never more bookings than memories; 16 memories: no contention |
| Python hash seeds 1 and 2, QFT dynamic, 2 memories | identical makespan (7134.42 ms), events and retries |
| Legacy baseline | 164 of 164 rows reproduced with the new code |
| Starvation guard, QFT on-demand, 2 memories | guard on 5571.8 ms, off 5416.6 ms: the guard costs 2.9% makespan here, in exchange for no starvation |

Reading the rejections: with pre-generation a pair can take a memory between the scheduler's check and the
reservation message arriving; the request rejoins the line. Whether every one of them is that case was not
traced individually, except that all 848 rejections of the earlier polling run on QFT (4 memories) coincided
with a core whose memories were all held by other requests.

Not covered: CGP and ACGP through the per-qubit scheduler (they need the request plan plumbed through the
runner), several mapping seeds, and expiry of unused pre-generated pairs under load.
