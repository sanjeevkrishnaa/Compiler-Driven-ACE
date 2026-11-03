# Compiler preparation admission controls

The per-qubit scheduler admits current execution before future preparation at
layer opening. These optional controls govern what happens to queued preparation
after that point; they do not replace execution-first or ready-first admission.

- `--compiler-memories 6 --total-memories 8` caps compiler reservations at six
  while retaining eight physical communication memories. Both the planner and
  physical endpoint protocols enforce compiler capacity. Application reservations
  may use all eight slots. This is a fixed cap, not an adaptive borrowing policy.
- `--demand-first` checks both endpoints before every preparation attempt. It
  defers speculation sharing an endpoint with waiting eligible demand and checks
  free timecards after accounting for application promises in flight.
- `--refill-on-release` accelerates rejected preparation retries when a booking
  is released. Release bursts coalesce into one wake two picoseconds afterward,
  after the application's one-picosecond admission grace. Handshakes already in
  flight are not duplicated. The existing one-millisecond retry is retained as
  a fallback. Active-layer transitions also wake pending retries.
- `--preparation-priority dependency` orders candidate launches and accelerated
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

The default planner remains `offline`, with demand guard and accelerated refill
disabled. Physical coherence, reservation lifetime, ready-pair handoff and the
application ordering rules are independent of these controls.

The QAOA comparison and exact commands are under
`docs/research/compiler-pregeneration/preparation-policy-2026-11-03/` after the
dated study completes. Use hop readiness together with admission wait, latency
and makespan; increasing readiness can increase congestion and execution time.
