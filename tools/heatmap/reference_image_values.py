"""Per-core percentages transcribed by hand from the project's figure "Per-core congestion across ten workloads"
(image dated 2026-10-21; demand > 4 slots/core, equal-weight mean over three mapping seeds).  Rounded to 0.1 as printed.
Order: cores C0..C15, row-major on the 4x4 mesh."""
Z = [0.0] * 16
REFERENCE = {
    "bmw_quark_cardinality": Z,
    "qft": [0.3, 20.2, 24.1, 0.3, 11.0, 50.6, 44.3, 10.1, 21.4, 52.4, 58.0, 4.8, 0.0, 2.7, 1.8, 0.0],
    "draper_qft_adder": [0.0, 4.8, 2.9, 1.0, 0.5, 11.6, 6.5, 0.2, 1.0, 15.2, 23.4, 11.1, 0.0, 1.9, 5.8, 1.2],
    "bv": Z,
    "qaoa": [1.4, 15.7, 21.3, 3.5, 20.4, 38.7, 37.6, 8.8, 8.2, 48.7, 56.0, 8.8, 0.0, 5.5, 4.5, 0.2],
    "ghz": Z,
    "cdkm_ripple_carry_adder": [0.0, 0.0, 0.0, 0.0, 0.2, 0.4, 0.6, 0.0, 0.0, 0.4, 0.6, 0.0, 0.0, 0.0, 0.0, 0.0],
    "vqe_real_amp": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.5, 0.0, 0.0, 4.5, 4.5, 0.0, 0.0, 0.0, 0.0, 0.0],
    "graphstate": [0.0, 5.6, 5.6, 0.0, 5.6, 33.3, 16.7, 0.0, 5.6, 22.2, 27.8, 0.0, 0.0, 5.6, 5.6, 0.0],
    "randomcircuit": [0.0, 0.4, 0.5, 0.0, 0.6, 2.0, 2.6, 0.2, 0.6, 3.2, 3.0, 0.1, 0.0, 0.1, 0.1, 0.0],
}
