# Default compiler preparation policy

The default compiler policy is quota-six with demand guarding: eight physical
communication memories per core, at most six compiler reservations, generation
budget eight, offline active-layer lookback 2--8, 10 ns empty-layer gaps,
execution-first/ready-first per-qubit admission, all-chain preparation, in-place
pair handoff and a 50 ms compiler reservation lifetime. The planning coherence
window is ten active layers.

History routing is not selected by this runner. The input trace is already
routed, so callers must supply the History-routed trace when that routing policy
is required.

- `--compiler-memories 6 --total-memories 8` caps compiler reservations at six
  while retaining eight physical communication memories. Both the planner and
  physical endpoint protocols enforce compiler capacity. Application reservations
  may use all eight slots. This is a fixed cap, not an adaptive borrowing policy.
- Demand guarding is enabled by default. `--demand-first` checks both endpoints before every preparation attempt. It
  defers speculation sharing an endpoint with waiting eligible demand and checks
  free timecards after accounting for application promises in flight. Use
  `--no-demand-first` only for an explicit control experiment.
- `--refill-on-release` is enabled by default and accelerates rejected preparation retries when a booking
  is released. Release bursts coalesce into one wake two picoseconds afterward,
  after the application's one-picosecond admission grace. Handshakes already in
  flight are not duplicated. This operates inside an active layer and never
  waits for the layer barrier. The existing one-millisecond retry is retained as
  a fallback. Use `--no-refill-on-release` for the former retry-only behavior.
- `--preparation-priority chain-length` is the default. A routed end-to-end
  communication is the hop chain for one qubit in one circuit layer. Longer
  chains launch first, with earlier hops breaking ties. Execution retains
  ready-first admission; within both the ready and ODG classes, longer eligible
  chains are serviced first. Per-qubit predecessor ordering is never bypassed.
- `--preparation-priority dependency` instead orders candidate launches and accelerated
  retries by target layer, then the number of predecessor hops that have not
  started, then trace order. This is a dependency proxy for eligibility, not a
  physical-time prediction. All hop positions remain candidates. `trace` is the
  default ordering.
- `--planning-mode runtime` supplies preparation candidates without offline
  storage reservations. Physical timecards and compiler quota admit them as
  capacity becomes available. The runtime also enforces `--generation-capacity`
  launches per core per active layer. A launch that books locally but is rejected
  remotely still consumes launch budget; a locally rejected attempt does not.
  Empty layers do not reset this budget. Deferred requests are reconsidered at
  later active-layer transitions or retry events and stop when their execution
  request starts.

The default planner remains `offline`. Runtime planning, dependency-priority
ordering and pair borrowing remain opt-in controls. Physical
coherence, reservation lifetime, ready-pair handoff and the application ordering
rules are independent of these controls.

The QAOA comparison and exact commands are under
`docs/research/compiler-pregeneration/preparation-policy-2026-11-03/` after the
dated study completes. Use hop readiness together with admission wait, latency
and makespan; increasing readiness can increase congestion and execution time.
