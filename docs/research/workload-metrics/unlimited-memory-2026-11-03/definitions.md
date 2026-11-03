# Unlimited-memory comparison

Compiler-driven only, on both XY and History routes, for the same QFT, exact QPE,
QAOA, Draper QFT adder and Quantum Volume workloads as the preceding C=8 study.
The 208-qubit circuits, T-HQA/OEE seed-42 mapping, 14 data slots per core, initial
headroom, 4x4 mesh and routed request files are unchanged. Physics seed is 60.
History is not rerouted with a different cost threshold: each route is held fixed
to isolate the memory-capacity comparison.

Both physical communication-memory capacity and compiler storage quota are made
nonbinding. Generation capacity stays at eight preparation launches per core per
logical layer; physical device/channel parameters are unchanged. Original logical
lookback 2-8, 5 ms empty gaps, 50 ms compiler reservation lifetime, physical memory
coherence and execution-first admission are retained. The additional demand guard
is disabled. Unlimited capacity does NOT mean infinite pair lifetime.

## Representation and checks

SeQUeNCe materializes memory objects, so it cannot instantiate a literal infinite
array. The experiment starts with 256 physical communication memories and compiler
quota 256 per core, increasing the pool and rerunning if verification fails.
The accepted runs must satisfy all of these checks:

1. Their offline plans exactly match plans with more compiler storage than the
   entire workload could require, while retaining launch capacity eight.
2. Peak live compiler bookings stay below the quota, and no preparation is
   rejected for local quota, local timecard capacity or remote memory capacity.
3. A conservative runtime bound, distinct booked slots plus all outstanding
   submitted application requests incident on the core, stays below physical
   capacity. Booked applications can be counted twice, making the bound
   conservative. Rejected/requeued requests remain counted until completion.
4. Every request completes and the usual ownership/order audit passes.

Capacity verification is workload/seed-specific, not a guarantee for arbitrary
circuits. The CSV and capacity_verification.json record actual pools, per-core
peaks, conservative bounds, compiler rejection reasons and node seed manifests.

## Random streams and baseline

Adding memory objects changes indices in SeQUeNCe's entity list. An optional
reference-eight-memory seeding mode preserves the original eight-slot indices
for common entities and assigns extra memory entities afterward. Building actual
8- and 256-slot topologies verifies the common indices and all 40 physical node
seeds match. The unlimited runs must match that reference seed manifest.
Their initial component RNG streams therefore align with the existing eight-slot
baseline. Different event sequences can still consume random draws differently.
This is a single-seed controlled comparison, not statistical replication.

## Metrics

Latency is eligibility-to-EPR-delivery per hop; the CSV also retains whole-chain
latency. Fidelity is delivered EPR fidelity, not circuit output fidelity.
Coverage is sampled at layer opening before admission or new preparation: full
means all hops of a migration have ready request-specific compiler pairs;
partial means some; zero/miss means none. The denominator is migration chains.

Wastage categories are disjoint percentages of generated compiler pairs: eviction
for non-expiry release, expiry for reservation/coherence expiry (including records
replaced after expiry), and unused for pairs remaining at simulation end. Raw
counts, denominators and release reasons are retained. Failed attempts that never
generate a pair are not counted as wasted EPR pairs.

Only capacity changes. The current application model still excludes data-qubit
teleportation, intra-core gates and destination data-memory occupancy. The 5 ms
empty-layer gap remains a timing assumption, and no preparation window is
subtracted from reported latency.
