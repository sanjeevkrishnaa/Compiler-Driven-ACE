# Reservation-start guard: replacing the unexplained 5.3 ms buffer

The original ACE request manager delayed every reservation by a fixed 5.3 ms.
Git history traces that value to the original September manager; it has no
derivation from the topology, a paper, or a physical parameter.

An RSVP reservation cannot begin at the instant its application calls `start`:
the request must first traverse the source-to-neighbour classical channel and
the approval must traverse the same channel back.  Otherwise the responder
receives or completes the reservation after its requested start time and
SeQUeNCe schedules an event in the past.

The manager now uses:

```text
reservation start = request arrival
                  + 2 x max configured router classical-channel delay
                  + 1 ps event-order grace
                  + optional user-supplied experiment delay
```

The optional delay defaults to zero.  On the 4x4 ACE configuration, one
router-to-neighbour classical delay is 0.100000 ms, so the calculated guard is
0.200001 ms.  A QFT-96 seed-0 smoke run with zero optional delay completed all
4,954 requests for both ODG and Dynamic.  The raw output is ignored under
`output/qft96_zero_delay_smoke/`; this note records the mechanism rather than
promoting a one-seed smoke run as a benchmark result.

This guard is a control-plane requirement, not EPR pre-generation.  It remains
part of elapsed time and is separately visible as
`reservation_start_delay_time_ms` in the timing breakdown.
