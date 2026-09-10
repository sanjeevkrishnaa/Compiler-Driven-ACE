# Fixed-lead study scope

Every fixed compiler policy in the 4x4 QFT work is a six-level sensitivity
study: \(\Delta \in \{1,2,3,4,5,6\}\) serialized trace sublayers. A single
fixed \(\Delta=2\) cell is a historical reference only; it is not the final
fixed-policy result for any section below.

| Report section | Backend/profile | Fixed-policy evidence required |
|---|---|---|
| Result A | ACE static 3+1, 2+2, 1+1 | six 30-seed audited cells per profile |
| 7.2 | Native static 3+1, 2+2, 1+1 | six 30-seed audited cells per profile |
| Result C | ACE shared pool, compiler cap 3 | six 30-seed audited cells; complete |
| Native shared pool | Native shared pool, compiler cap 3 | six 30-seed audited cells |
| Result D | ACE fixed compiler row | use the Result C six-lead matrix; CGP/ACGP/ODG remain non-fixed controls |

For every cell, the result artifact must bind an immutable contract, the locked
trace and serialization hashes, paired seeds 0--29, source/environment and raw
provenance, full completion, and request/pair identity audit. Compare ACE and
native only by trends within each backend; never by their raw latency values.

The cap-four wait-on-demand control is a separate capacity study. It requires
its own matched cap-three atomic-admission control before any capacity claim.
