# Responder booking cleanup after initiator completion

The three-seed final matrix stopped at Draper QFT Adder / XY / CD-unlimited /
seed 62. The old code completed all 6,510 transfers, but the audit found
`BOOKING_SURVIVES_COMPLETION`: request 6462 still held router_0_1 memory 1.

An exact replay reproduced the failure. Event tracing showed request 6462's
first compiler handoff rejected, followed by successful fallback generation.
The initiator credited the pair and released its reservation. The responder
never credited that attempt, leaving its application booking alive. This was
not a compiler quota leak, and it was not a shortage of the 256-slot bound.

The parallel application inherited a completion notifier which only contacted
intermediate routers. On a direct mesh edge it sent no notification at all,
assuming the responder would always release its lease independently. If that
callback is missed, its 50 ms timeout can outlive the workload's final 1 ms
drain and block subsequent requests in the meantime.

The parallel application's notifier now sends EXPIRE to every remote node on
the reservation path, including the responder. Messages use the existing real
classical channel. Local lease release remains idempotent; already completed
peers safely ignore duplicate release. No physical audit was relaxed, and no
peer memory is reset instantaneously by the initiator.

Validation:

- Exact failed workload/route/policy/seed rerun: 6,510/6,510 completed,
  106,150 observed events and zero audit violations; unlimited bound verified.
- A small physical regression deliberately omits responder credit. The previous
  notifier produces BOOKING_SURVIVES_COMPLETION; the fixed notifier passes the
  same audit, with responder release strictly after initiator completion and
  within the real classical-message delay.
- Two additional notification tests cover direct and multihop paths.
- All 187 compiler tests and four final-matrix tests pass (194 tests total).

## Existing final-matrix results

Do not edit specification.json or disable the source fingerprint check. The
additional completion messages can change event ordering, resource availability
and later metrics under every policy, so old and new implementation results
must not be silently combined into one final comparison. The exact replay
already follows a different successful handoff path after the fix.

Keep `output/final-results-224-3seed` as the archived pre-fix evidence. After
updating the code, run the coherent fixed matrix in a new directory:

```powershell
python -B tools/run_final_matrix.py --seeds 60,61,62 --jobs 2 --output output/final-results-224-3seed-peerfix
```

This starts a new matrix. It does not reuse the 323 old-code observations.
Future interruptions within this fixed matrix can resume with that same command.
