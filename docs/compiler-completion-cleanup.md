# Cleanup after request completion

When an application finishes a transfer, its request-specific compiler generation
is no longer useful. The controller now cancels queued retries and releases its
unused compiler reservation at the initiator, then sends a real EXPIRE message to
the peer over the classical channel. Handed-off application leases and other
targets' preparation are not released by this cleanup.

The initiating compiler reservation owns its booking and timeout while approval
is still in flight. A late approval or rejection cannot recreate cancelled rules
or decrement its quota twice. The cleanup is idempotent.

The old RSVP-expiry regression came from treating an in-place handoff as an
ordinary future reservation. Future bookings must not reset their memory's
current owner, but a handoff already owns the cached quantum state even before
the application reservation's start. A rejected handoff therefore resets its
owned state immediately. Application leases created during handoff also receive
their own timeout when rules load; initial compiler bookings do not get duplicate
timers on approval.

Already-generated pairs discarded when their target completes are classified as
`cancelled_compiler_pairs`, separately from timeout/coherence expiry. They remain
in the waste numerator:

```
waste = (expired + cancelled + remaining) / generated
generated = used + expired + cancelled + remaining
```

Cancellation before successful generation does not invent a generated or wasted
EPR pair. A generation callback at the peer can race the cancellation's actual
message delay; the peer cleans up when that message arrives.

The initial preparation lead, trace ordering, borrowing, immediate replacement,
physical fidelity/noise parameters, memory quota and 50 ms reservation duration
are unchanged. Previous sweep workbooks describe the pre-cleanup implementation
and are retained as historical evidence.

Validation before the full QAOA rerun: 186 compiler tests passed, including the
previously failing expiry-during-RSVP physical test, pending-handshake cleanup,
quota idempotency, future-memory ownership, handoff application timers, and
borrowing/replenishment in both directions. A 448-transfer QAOA L-9 prefix
completed with zero physical/order violations, zero timeout expirations and one
cancelled unused pair still counted as waste.
