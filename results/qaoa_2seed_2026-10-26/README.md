# QAOA two-seed golden study (26 October 2026)

This is a fresh QAOA-only simulation root.  Its inputs are audited copies of the tracked T-HQA mapping corpus; no historical raw results were copied or reused as evidence.

The immutable base manifest is generated from `execution_spec.json`.  It covers mapping seeds 42/43/44, mesh XY/YX/shortest-reliable/maximum-reliability, torus Dijkstra, M=2/3/4/6/8/16/32, every legal compiler allocation, ODG/CGP/ACGP/Dynamic full-chain/Dynamic first-hop, and physics seeds 0/1.

Primary latency is arrival/eligibility to completion.  The study uses `pregeneration_buffer_ms=0.0`; no historical 5.3-ms subtraction is permitted.  Only atomically finalized raw job directories are reportable.
