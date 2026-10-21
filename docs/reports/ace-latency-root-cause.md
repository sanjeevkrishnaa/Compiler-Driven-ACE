# ACE compiler latency diagnosis — 2026-10-21

The corrected seed-0 random16 result is dominated by reservation rejection and
timeout waiting, not physical EPR generation. Instrumented runtime experiments
used the same 62 requests, seed 0, four memories, 5.3 ms preparation buffer,
50 ms request window and five-second simulation horizon. Production source was
not modified for these experiments.

## Measured decomposition

| Policy | Mean request latency ms | Retry waiting ms | Exposed setup/service ms | Retries | Makespan ms |
|---|---:|---:|---:|---:|---:|
| ODG | 13.7162 | 12.4871 | 1.2291 | 14 | 1207.0021 |
| Dynamic, cap 3, 1000 ms lease | 43.7839 | 42.8129 | 0.9710 | 48 | 3071.2016 |
| Dynamic, cap 2, 1000 ms lease | 26.0339 | 24.9742 | 1.0597 | 28 | 1970.9018 |
| Dynamic, cap 1, 1000 ms lease | 17.2307 | 16.0548 | 1.1758 | 18 | 1425.1020 |
| Dynamic, cap 3, 100 ms lease | 24.2145 | 23.1903 | 1.0242 | 26 | 1858.0017 |
| Dynamic, cap 3, 20 ms lease | 19.9065 | 18.7306 | 1.1758 | 21 | 1590.9020 |

All six experiments completed all 62 requests. Compiler service savings are
0.2581 ms/request with the default dynamic settings, but added waiting is
30.3258 ms/request. Every retry in the default ODG/dynamic runs follows an
application reservation admission failure; there were no multiple retries per
request in those two runs. These are single-seed diagnostic observations.

## Confirmed lifecycle and scheduling causes

1. **Application bookings survive completion.**
   `ResourceManagerAdaptive.expire_rules_by_reservation` expires rules without
   removing memory timecards. The timecards continue to block other reservations
   until their original 50 ms end time. At each of ODG's 14 rejected admissions,
   all four blocking cards belonged to already completed application requests.
   Every one of dynamic's 48 rejected admissions also had at least one card that
   would become free by removing only completed application bookings. This is
   an instantaneous admission snapshot, not a simulation of the resulting new
   trajectory or a guarantee of remote-endpoint admission.

2. **Consumed compiler reservations retain a one-second lease and quota.**
   `request_compiler_pair` reserves through `start + 1000 ms`. The one-shot rule
   prevents regeneration after consumption, but `remove_entanglement_pair` only
   removes the cached pair and metadata; it does not release the timecard or
   decrement `adaptive_memory_used`. The quota release remains scheduled for
   the lease end. In 45 of the 48 default-dynamic rejected application admissions,
   removing only already-consumed compiler bookings would free at least one
   local card. Blocker categories overlap and are not separate causal totals.

3. **A ready EPR still needs another application reservation.**
   Cache matching happens inside the application's generation protocol, after
   RSVP admission. A ready compiler pair therefore cannot bypass a full
   timecard bank. Request 2's pair existed at 1.7000 ms; application submission
   was at 14.1001 ms, but consumption occurred at 74.9001 ms after a timeout.
   Its rejected admission found the intended compiler pair, another compiler
   reservation, and two already-completed application bookings occupying all
   four cards on router_0_1.

4. **Immediate rejection becomes a full timeout.**
   The request app notifies the manager on approval and completion, not
   rejection. `_check_layer_timeout` waits through the 50 ms request window
   before queuing a retry; the next attempt also gets a 5.3 ms buffer. Each
   avoidable rejection therefore costs at least approximately 55.3 ms, versus
   physical service of about 1 ms. Layer barriers propagate the delay to later
   transfers and age stored EPRs.

5. **Offline capacity and physical leases do not describe the same lifetime.**
   `plan_preparations` reserves logical slots over `[generation_layer,
   target_layer)`. Runtime preparation starts at entry to the generation layer,
   before that layer's communications, and retains physical reservations after
   target consumption. The planner also treats same-layer consumption as freed
   before later preparation while runtime can retain it across sublayers.
   Dynamic scheduled 48 preparations but only 11 were accepted physically.
   Its 37 rejections comprise 17 local quota, 17 remote memory/timecard, and
   three local timecard rejections. Only ten requests consumed compiler pairs.

6. **Rejected preparations are not retried by the compiler controller.**
   `on_original_layer` triggers each planned layer once and ignores the launch
   return value. Rejections are recorded, but no future admission retry or
   replan is queued. The full trace is used to choose an initial launch layer;
   it is not yet a physical-resource-aware feedback scheduler.

## Interpretation and repair order

Full trace knowledge can hide generation time only if preparation does not
block the consumer or other demand. These results show a resource lifecycle
and admission problem in this implementation; they do not demonstrate an
inherent disadvantage of compiler information. A significant speedup remains
an empirical question after lifecycle correction and fair baseline reruns.

The immediate repair should release application and compiler ownership on
completion/adoption, including timecards, quota and associated future events.
Simply deleting cards is unsafe: the existing expiry events can later reset
memories that have been assigned to a new reservation. Release must be
idempotent and either cancel or ownership-guard those events. Apply the same
completion-release behavior to ODG for a fair comparison.

Next, make rejection visible to the request manager and retry on availability
or bounded backoff rather than waiting for a service timeout. Then add compiler
admission retries, account for both endpoints and adoption scratch memory, and
align planning with actual sublayer execution and physical memory lifetime.

Shortening leases alone is not a complete fix. The 20 ms experiment reduced
waiting but expired 29 of 31 compiler pairs (93.55%). Runtime lease tuning
trades blocking against expiration without correcting ownership.

Raw instrumentation is in `.tmp/ace_latency_diagnosis.json`; the diagnostic
driver is `.tmp/diagnose_ace.py` in the SeQUeNCe workspace. It monkeypatches
observers in process to collect admission snapshots and does not edit ACE.
