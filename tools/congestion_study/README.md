# MQT Bench → qubit mapping → trace → hotspot report

This is a runnable characterization pipeline using the **supplied TraceGen
`qmap` implementation**, rather than a substitute mapper. It accepts MQT Bench
workload names or OpenQASM files, maps their normalized gate circuits with HQA,
exports the mapping and adjacent-hop trace, validates them, and produces an
HTML/Markdown report with CSV/JSON evidence. It does not change the mapper's
routing algorithm or execute adaptive routing.

Default MQT workloads, taken from the actual `mqt-bench` factories:

1. `qft` — Fourier transform.
2. `ghz` — sparse state preparation.
3. `qaoa` — dense Max-Cut interactions.
4. `vqe_real_amp` — repeated variational ansatz.
5. `cdkm_ripple_carry_adder` — Cuccaro/CDKM arithmetic.
6. `draper_qft_adder` — Fourier-basis arithmetic.

Upstream: <https://github.com/munich-quantum-toolkit/bench/tree/main/src/mqt/bench/benchmarks>.

## Defaults and qubit accounting

| Knob | Default |
|---|---|
| Mesh | `4x4`, 16 cores |
| Total physical qubits | `128`, including communication memories |
| Physical slots/core | 8, derived from total / cores |
| Communication memory slots/core | **4** |
| EPR preparation policy | **dynamic** |
| Fallback/adoption reserve within communication bank | 1 |
| Compiler preparation slots/core | 3 |
| Data slots/core | 4 |
| Initial spare data slots/core | 1 |
| Default circuit width | **48 logical qubits**, 3 initially occupied data slots/core |
| Mapping | HQA, OEE initial placement, strict validation |
| Mapping/hardware seeds | 42 |
| Reliability range used by mapper | `[0.1, 1.0]` |
| Dynamic lookahead/coherence | 8 / 10 logical layers |

The budget is **48 occupied data + 16 spare data + 64 communication = 128**.
The spare data slot is not an extra communication memory. The supplied HQA
mapper needs vacant data capacity for eviction/migration; using all 64 data
slots caused unplaceable operations on the default workloads. This pipeline
does not silently ignore those operations or borrow the communication bank.

The mapper is therefore given a four-slot **data-only** capacity per core and
one initial reserved/spare data slot. Its later placements may use the fourth
data slot, but never the four communication slots. This matters because the
mapper's own `reserved_ancilla` applies to initial placement, not a permanent
exclusion from its later assignments. Every resulting circuit layer is checked
against the data-only capacity, and the exported trace header records the full
eight-slot physical architecture.

`--spare-data-slots-per-core 0` permits a requested 64-qubit circuit on the
default architecture, but the current HQA mapper may fail at that saturation.
Such failure is reported; there is no automatic width reduction or fallback
to an incomplete mapping. To study 128 **logical** qubits with headroom and
four communication slots/core, increase the physical budget, e.g.
`--total-qubits 256 --logical-qubits 128`.

`--policy dynamic` is EPR scheduling. `--placer HQA` is qubit mapping; these
are separate decisions.

## Setup

Use Python 3.11 or newer and install into the interpreter that runs the script:

```powershell
python -m pip install -r tools/congestion_study/requirements.txt
```

The mapper is loaded from `--mapper-dir`; installing an unrelated PyPI package
called `qmap` is not needed. Locally the supplied checkout is
`C:/Users/sanje/Desktop/BTP/tracegen`. The pipeline can detect that layout,
but specifying it makes reproduction clearer. `pytket`, SeQUeNCe and QuTiP
are **not** needed for the default mapping/characterization workflow: the
adapter converts normalized Qiskit gates directly to the supplied mapper's IR.

## Run all six workloads

From the SeQUeNCe repository root:

```powershell
python tools/congestion_study/run_study.py `
  --mapper-dir C:/Users/sanje/Desktop/BTP/tracegen `
  --output output/my_congestion_study
```

Open `output/my_congestion_study/report.html`. No browser server or network
connection is needed to view the report. A Markdown overview is also written
as `report.md`.

The folder containing `run_study.py` and `hotspot_analysis.py` is portable:
copy it elsewhere and run `python path/to/run_study.py --mapper-dir ...`.

## Select workloads, sizes and seeds

```powershell
python tools/congestion_study/run_study.py `
  --mapper-dir C:/Users/sanje/Desktop/BTP/tracegen `
  --workloads qft qaoa draper_qft_adder `
  --mesh 4x4 --total-qubits 128 --memory-slots 4 `
  --policy dynamic --logical-qubits 48 `
  --seeds 0 1 2 3 4 --circuit-seed 42 `
  --output output/congestion_5seed
```

Mapping/hardware seeds change mapping randomness and link reliability draws.
They are held common across workloads for a given seed. Circuit generation
uses a separate fixed `--circuit-seed`, allowing repeated mappings of the same
circuit. That seed is passed to factories that accept `seed`; factories with
hard-coded internal randomness retain their upstream behavior. Bound circuit
parameters and transpilation also use `--circuit-seed`. Circuit and factory
hashes are recorded, so actual inputs can be compared directly.

Other mesh sizes work, provided the physical budget divides evenly across
cores and leaves at least two data slots/core. For example:

```powershell
python tools/congestion_study/run_study.py --mapper-dir C:/Users/sanje/Desktop/BTP/tracegen --workloads qft --mesh 2x3 --total-qubits 72 --memory-slots 3 --logical-qubits 24 --output output/rectangular_study
```

Use `--workload-options options.json` for factory parameters:

```json
{
  "qaoa": {"repetitions": 4, "seed": 10},
  "vqe_real_amp": {"reps": 5, "entanglement": "circular"},
  "cdkm_ripple_carry_adder": {"kind": "full"}
}
```

Workload-specific width constraints remain enforced by MQT Bench. The report
records actual circuit width; it never assumes a factory's size argument and
returned width are identical. Optional `--bench-dir PATH` uses an MQT Bench
source checkout's `src/` instead of the installed package.

## Supply your own workload

Export a Qiskit circuit to QASM, or use an existing OpenQASM 2/3 file:

```powershell
python tools/congestion_study/run_study.py `
  --mapper-dir C:/Users/sanje/Desktop/BTP/tracegen `
  --qasm C:/path/to/circuit.qasm `
  --output output/custom_workload
```

When only `--qasm` is supplied, the six MQT defaults are not also run. Use both
`--workloads` and `--qasm` to combine inputs. QASM files retain their actual
width and must fit the architecture's data bank.

The adapter binds parameters deterministically, removes final measurements,
and decomposes to `rz,sx,x,cx` with optimization level 0 by default. This avoids
unsupported multi-qubit gates being silently excluded from mapping. It rejects
mid-circuit measurement, reset and classical control: the supplied static
mapper cannot correctly preserve their semantics.

## Report contents

Each workload/seed folder contains:

- `circuit.qasm`: the exact normalized circuit passed to mapping.
- `mapping.csv`: initial mapping (`layer=-1`) and every layer's output placement.
- `mapping.npz`: compressed initial vector and layer-by-qubit placement array.
- `mapping_summary.json`: mapper algorithm, route model, validated occupancy,
  link reliabilities, cost and runtime.
- `requests.txt`: ACE-compatible initial placement and layer-grouped adjacent hops.
- `summary.json`: workload counts, overload/capacity sensitivity and routing evidence.
- `layers.csv`: every original compiler layer and demand at every core.
- `capacity_layers.csv`: overloaded core IDs, excess demand and wave counts at
  capacities 1, 2, 3, 4 and the configured banks.
- `cores.csv`: total/peak demand, overloaded-layer counts, relay share and
  unavoidable shortest-path incidence lower bounds.
- `edges.csv`: link-level total hops, active layers and peak per-layer demand.
- `preparation_schedule.csv`: request-specific offline admission for dynamic
  (default), fixed or on-demand preparation.
- `hotspots.svg` and `report.html`: offline visual report with core-layer heatmap,
  hotspot tables, largest bursts, routing evidence and delay qualification.
- `manifest.json`: success/failure status, exact input hashes and settings.

At the top level, `summary.csv`, `report.html`, `report.md` and `study.json`
compare all workload/seed runs. The study includes versions, mapper source
hashes, pipeline hashes and available Git commits. Failed inputs are named in
the report and cause a nonzero exit code; successful inputs are retained.
Rerunning in the same output directory replaces the named trial artifacts;
the overview lists only trials from the current invocation.

## Interpreting congestion and routing evidence

A hop contributes one incidence at each endpoint core. A layer is overloaded
when any core's layer demand exceeds its communication-memory bank. These are
**layer totals, not observed simultaneous occupancy**; hops of one migrating
qubit remain dependent. Compiler-bank overload is reported separately from
physical-bank overload.

The report separates fixed migration endpoints from relay traffic, counts
equal-hop shortest-path alternatives, and computes mandatory shortest-path
load lower bounds. A positive mandatory overload means shortest-path selection
alone cannot clear that layer. A zero bound does not prove a globally feasible
rerouting exists. Consecutive same-qubit hops are grouped into chains; omitted
logical gate details are not reconstructed from the communication trace.

The current ACE batch count preserves order at every core and permits one
request/core/batch. Abstract capacity-aware packing preserves same-qubit hop
order but allows more concurrent requests. It is a scheduling diagnostic, not
a new simulator capability or a predicted adaptive-routing speedup.

Default delay output consists of wave counts and the configured 5.3 ms/batch
**buffer component**. `--hop-service-ms 1.0` additionally produces explicitly
labeled constant-service timing estimates. Neither is measured physical
latency, and neither establishes how much time adaptive routing would save.

## Optional measured physical ACE stage

The default characterization has no physical-simulator dependency. If desired,
provide the repaired ACE checkout and its compatible SeQUeNCe fork:

```powershell
python tools/congestion_study/run_study.py `
  --mapper-dir C:/Users/sanje/Desktop/BTP/tracegen `
  --workloads qft --policy dynamic `
  --simulate `
  --ace-dir C:/Users/sanje/Desktop/BTP/ACE `
  --sequence-dir C:/Users/sanje/Desktop/BTP/repo/qnoc-stress-testing/SeQUeNCe `
  --output output/qft_with_physical_timing
```

This invokes ACE in a separate process with the same trace, seed, preparation
policy and communication-memory budget. Its measured request latency,
completion and makespan appear separately from the analytical components;
raw output is saved under `physical/` and `physical.log`. Incomplete physical
runs fail explicitly; increase `--stop-time-s` if needed. Other mesh sizes
require `--ace-config` matching that architecture. ACE dependencies must be
installed in the same Python interpreter used for this invocation.

The mapper's sampled link reliabilities guide mapping/path choice; optional
ACE physics uses `--ace-config`. The pipeline does not silently reinterpret
mapper reliability samples as detector efficiencies or native channel losses.

## Validation

The full six-workload default (48 logical qubits, HQA/OEE, 4x4, 128 physical
slots, four communication memories, seed 42) was executed successfully using
MQT Bench 2.3.0 and Qiskit 2.5.2. Every trace was checked for complete initial
placement, evolving qubit location, mesh adjacency and agreement with the
mapper's per-layer output. Tests cover capacity accounting, dependency order,
shortest-path lower bounds, empty traffic and malformed placement.

```powershell
python -B -m unittest discover -s tools/congestion_study/tests -v
```
