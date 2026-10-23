# Mapper provenance and verification

This folder is a **verbatim copy** of the qubit mapper that produced every mapped
trace used by the congestion studies in this repository: QM2026 (`qm2026` 1.0.0,
Python package `qmap`), referred to elsewhere in the repo as the *supplied TraceGen
`qmap` implementation*. HQA is `qmap/placement/HQA.py`.

Nothing under `qmap/`, `pyproject.toml`, `README.md` or `requirements.txt` has been
edited. `README.md` is the mapper's own documentation. This file and `verification/`
are the only additions.

## Where it came from

| | |
| --- | --- |
| Original location | `C:\Users\sanje\Desktop\BTP\tracegen` (recorded as `mapper_dir` in the archive's `study.json`) |
| Version control | None recorded: `mapper_git_commit` is `null` |
| Copied from | `mapper_source/` inside `results/congestion/mqt_ten_workload_congestion_results.zip` |
| License | `pyproject.toml` declares MIT. No LICENSE file or author list was shipped with it. |

## Verification (2026-10-23)

**Source identity.** When the archived traces were generated, the pipeline recorded
the SHA-256 of every `qmap/*.py` file (`mapper_source_sha256` in `study.json`). All
**49 of 49** files in this folder match. None differ, none are missing, none are extra.

**Output reproduction.** The pipeline was rerun on macOS with the recorded parameters
(10 workloads × mapping seeds 42, 43, 44) and the recorded package versions.

| | Recorded | Used |
| --- | --- | --- |
| Python | 3.14.7 | 3.14.0 |
| mqt-bench | 2.3.0 | 2.3.0 |
| qiskit | 2.5.2 | 2.5.2 |
| numpy | 2.5.1 | 2.5.1 |
| scipy | 1.18.0 | 1.18.0 |
| networkx | 3.6.1 | 3.6.1 |

All 420 per-trial files were reproduced:

| File | Result in all 30 trials |
| --- | --- |
| `requests.txt` (the trace), `circuit.qasm`, `report.html` | identical after normalising Windows CRLF line endings |
| `mapping.csv`, `layers.csv`, `cores.csv`, `edges.csv`, `capacity_layers.csv`, `preparation_schedule.csv`, `hotspots.svg` | byte-identical |
| `mapping.npz` | every array identical in name, shape, dtype and value |
| `manifest.json`, `summary.json`, `mapping_summary.json` | identical except fields listed below |

Every permitted difference was checked individually, not skipped:

- **Line endings.** The archive was produced on Windows, which writes CRLF.
- **File-hash fields.** `trace_sha256` and `normalized_circuit_sha256` each equal the
  SHA-256 of their own file in both runs. They differ only because of line endings.
- **Environment fields.** Wall-clock times, the benchmark factory's install path, and
  the Python patch version.
- **Floats** in `mapping_summary.json`: at most **5 ULP**, i.e. differences in the
  last binary digits of derived costs and link reliabilities. No routing choice
  changed: every trace is identical.

Two copies of the archive exist: the one committed in the repo, and the one shared
separately. They differ only in `SHA256SUMS.csv` and `validation.json`. All 30 traces
and all 52 mapper files are identical between them.

## How a trace is produced

Stages and the code that performs each one:

1. **Circuit.** An MQT Bench factory builds the circuit at the requested width
   (48 qubits here). Parameters are bound from a seeded RNG, and final measurements
   are removed. Mid-circuit measurement, reset and classical control are rejected.
   This is `load_circuit`, `tools/congestion_study/run_study.py:153`.
2. **Normalisation.** Qiskit transpiles the circuit to the basis `{rz, sx, x, cx}` at
   optimisation level 0 (`run_study.py:187`), then converts it to the mapper's gate
   list.
3. **Layering.** `qmap/circuit/slicer.py:64` (`slice_circuit`) places each gate in the
   earliest slice after the last slice used by any of its qubits. This is an ASAP
   schedule of the circuit's dependency DAG. **All gates are layered, single-qubit
   ones included**, so many slices contain no inter-core communication. For example,
   QFT seed 42 has 382 slices, of which 112 carry hops. A slice is a logical time
   step, not a physical duration.
4. **Mapping.** HQA processes slices in order. For each two-qubit gate whose operands
   sit on different cores, it chooses a destination core by Hungarian assignment
   (`scipy.optimize.linear_sum_assignment`), subject to the per-core data capacity,
   and moves the operands there. OEE provides the initial placement. The result is a
   placement of every qubit after every slice. Qubits *move* (teledata); gates are
   not teleported.
5. **Routing and hop expansion.** Each migration is a (qubit, source core, target
   core) move, and the endpoints may be far apart.
   `qmap/io/requests.py:25` (`build_hop_requests`) expands every migration into one
   request per link along `route_path`. For HQA that path is the **shortest hop count,
   with link reliability as the tie-breaker** (`qmap/metrics/distance.py:39`). It is
   not XY routing: only 46.7% of multi-hop routes in the archive coincide with XY.
   Every line of `requests.txt` is therefore an adjacent-core hop. The migration-level
   list, before expansion, is available from `qmap/io/traces.py:28` (`build_trace`).
6. **Consistency check.** The pipeline replays the hops and requires them to reproduce
   the mapper's placement after every layer (`run_study.py:241`).

Everything downstream starts from `requests.txt`. `compiler_trace.py` parses it, the
fixed-lead or dynamic planner schedules EPR preparations, and ACE or native SeQUeNCe
simulates them.

## Reproducing the verification

```bash
# 1. An environment matching the recorded versions (kept separate from ACE's)
python3.14 -m venv .mapper-env
.mapper-env/bin/pip install "mqt-bench==2.3.0" "qiskit[qasm3-import]==2.5.2" \
    "numpy==2.5.1" "scipy==1.18.0" "networkx==3.6.1"

# 2. Source identity (needs only numpy)
.mapper-env/bin/python mapper/verification/verify_mapper.py sources

# 3. Regenerate the archived study, then compare it trial by trial
.mapper-env/bin/python tools/congestion_study/run_study.py --mapper-dir mapper \
    --workloads bmw_quark_cardinality qft draper_qft_adder bv qaoa ghz \
                cdkm_ripple_carry_adder vqe_real_amp graphstate randomcircuit \
    --seeds 42 43 44 --output output/mapper_reproduction
.mapper-env/bin/python mapper/verification/verify_mapper.py outputs --fresh output/mapper_reproduction
```

`tools/congestion_study/run_study.py` and `hotspot_analysis.py` are byte-identical to
the pipeline copies recorded in the archive (`pipeline_source_sha256`).
