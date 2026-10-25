# Why does XY routing win? A test design written BEFORE the tests are run

Date 2026-10-25. Observation (done, 30 seeds): on QFT-96, XY routing cuts Dynamic latency 2.570 → 1.484 ms and ODG admission wait 0.200 → 0.018 ms
against the supplied routes, with identical hop counts (4,954) and identical placements.

## Hypothesis H (to be tested, not assumed)
Requests wait for a free communication memory. A core has 4. The supplied routes (shortest-hop search with a reliability tie-break) put many
migrations through the same relay cores in the same layer, so some cores' demand exceeds 4 and requests queue there. XY spreads the same
hops over more cores, so less demand exceeds 4 and less queueing happens. The benefit is therefore a property of how evenly the routes load
the cores, not of "XY" as such.

## Alternatives that would explain the same observation (each gets a test)
- A1 route length: ruled in/out by the hop histogram (identical for XY and the supplied routes: checked).
- A2 something specific to the XY geometry (e.g. XY happens to avoid one bad core) rather than spreading in general.
- A3 an artefact: runs not completing, an invariant violated, or a different request order. (completion rate, invariant checker, hop validity.)
- A4 the benefit is confined to QFT-96's trace and does not generalise. (ten benchmarks, memory budgets.)

## Tests
T1 Static load per arm (no simulation): per core endpoint and relay demand, per layer D = endpoint touch 1 + relay touch 2, excess = Σ max(0, D−C) for C in {2,3,4,6,8}.
T2 Dose–response by intervention on the supplied routes (placement fixed, hop counts fixed unless noted):
   mix-p (replace a random fraction p of migrations by their XY path), random-shortest (uniform among all shortest paths, 3 draws), O1TURN (random XY/YX, 3 draws),
   concentrate (among shortest paths pick the one through the currently busiest cores: pushes load the wrong way), avoid-hot-k (reroute only the migrations that
   pass through the k busiest relay cores of the supplied routes). Each run through ACE: ODG and Dynamic, 30 seeds, identical settings.
T3 Per-core evidence inside the simulator: admission wait per core and by role (endpoint of the migration vs relay) for supplied vs XY, ODG and Dynamic.
T4 Validity: completion rate 1.0 in every run, hop validity and partition replay for every trace, the ACE invariant checker on XY runs.
T5 Generalisation: ten benchmarks (48 qubits, mapper's own partitions) with supplied vs XY routes, and QFT-96 across memory budgets 2,3,4,6,8.

## Predictions (fixed now)
P1 T1: static excess at C=4 is highest for the supplied/reliability arms and lowest for XY/YX.
P2 Across all arms and interventions, ODG admission wait rises with static excess (Spearman ρ ≥ 0.8). Wrong if ρ < 0.5.
P3 Mix-p improves monotonically with p. random-shortest and O1TURN recover most (≥ 70%) of XY's ODG wait reduction, otherwise A2 (XY-specific) is supported.
   concentrate is worse than the supplied routes, otherwise the load story is wrong.
P4 T3: in the supplied routes the waiting concentrates on the cores with the highest relay demand; in XY it falls there.
P5 avoid-hot-1/2 recover a large share of the gain; if they recover almost none the cause is spread over many cores, not a few hot ones.
P6 T5: XY helps wherever memory is scarce (small budgets, the multi-hop-heavy workloads) and makes no difference where nothing is congested (GHZ, BV).

## How a conclusion is drawn
H is supported if P1–P5 hold; any prediction that fails is reported as a failure and H is narrowed or rejected accordingly. Correlation across five
arms alone is not accepted as causation: the interventions in T2 change only the routes of chosen migrations.
