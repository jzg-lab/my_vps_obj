# Independent service entitlement and metering contract

A/B checkpoint, 2026-10-23. Baseline: `ace4746328534fdd90d02eb98d85053bf7e4852d`.
This defines the implementation boundary; it is not evidence of Node acceptance.

## Counters and limits

- One service owns one panel identity. `NO_RESET` is mandatory. Never reset a panel
  counter, replace an identity, or copy an account's legacy identity to refill quota.
- `ServiceConnection.usage_total_bytes` is the last accepted cumulative payload-byte
  observation; `UserService.used_bytes` is confirmed usage in the business period
  (whole lifetime for a total package). Both include upload plus download, and
  overage is retained. Duplicate samples add nothing. Regressions/reset strategies
  latch a reconciliation error; a later larger sample cannot clear it.
- The expected panel **absolute** limit is cumulative total minus current-period
  usage plus period quota. Before the first observation the baseline is zero.
  This is not simply `quota_bytes` after the first monthly switch. The mapping is
  owned by `service_panel_state.panel_traffic_limit(service, connection)`.
- `matches_service_terms(remote, service, squads, connection=...)` checks the same
  absolute limit, expiry, exact squads and `NO_RESET`. B must pass the connection.
  Creation uses the same mapping and remains disabled.

## Monthly switch

- Calendar bounds use `monthly_period(service.starts_at, now)` in Beijing time;
  keep the original anchor, skip missed months without accumulating allowances.
  Renewal does not change usage, anchor or cycle. Total packages never roll over.
- A persists a cycle transition and its cumulative checkpoint before changing a
  remote limit. The old cycle stays visible until the remote terms and checkpoint
  are read back successfully. Traffic observed before confirmation belongs to the
  old cycle, including overage. A moving counter defers confirmation and is
  reconciled on retry; it must not silently become new-period consumption.
- A successful switch archives the old cycle's actual usage and initializes the
  current calendar period once, without rollover of unused bytes. Failed/uncertain
  writes retain the old usage and a durable pending transition. Recovery checks
  the same identity and transition; it cannot blindly issue another allowance.
- No new period is granted after service expiry or cancellation. Pause/account ban
  never enables a connection during rollover. Pending delivery remains pending.
  Panel/Node sampling latency remains an acceptance item, not a zero-overage claim.

## Shared eligibility and synchronization

- `user_service_access.service_status(...)` owns the business eligibility order:
  ban/deleted owner, pause/cancellation, expiry, confirmed exhaustion, start/readiness,
  verified dedicated resource, then active. Unknown usage alone is not exhaustion.
- `service_change_sync.synchronize_service_change(session_factory, service_id, panel)`
  is the public retry entry. A also exposes
  `synchronize_service_entitlement_locked(session, user, service, connection, panel)`
  for callers already holding the account lock (B delivery and account access).
  It reads fresh ownership and terms, applies the expected expiry/absolute limit,
  then verifies before enabling. It does not mark a connection ready.
- B establishes delivery readiness and calls this shared entry under the same
  account lock, with a persisted retry marker before remote writes. B does not
  calculate another limit, reset counters, or add a separate enable/disable rule.
- Usage/period processing, service changes, account ban/unban and delivery serialize
  on the account row lock. Recheck time after remote waits. Known expiry/exhaustion,
  pause and ban take precedence; an unknown sample does not erase usage or force
  disconnection of an otherwise confirmed active service. Re-enabling requires
  verified terms and usable metering; unresolved counter anomalies block enabling.
- A periodic reconciliation path covers expiry/exhaustion even without an admin
  change. Confirmation means panel read-back only. B/D must separately validate
  real Node access, long-lived connections and subscription revocation.

## Ownership and open decisions

A owns `service_panel_state.py`, `user_service_access.py`, `service_change_sync.py`,
usage/period reconciliation and migration `0113`; B uses `0114` and coordinates
shared models/registration through T. No subscriptions, IP release or Chinese
translation are part of A.

A3 requires user decisions before implementation: whether monthly quota adjustment
changes only the current cycle or future cycles too; what auditable evidence is
required to reconcile missing traffic after a counter reset. No default forgiveness,
estimated history, counter reset or identity replacement is implied.

See [independent services](independent-services.md), [requirements](../requirements.md)
and [implementation plan](../implementation-plan.md#10-剩余工作分包与协作).
