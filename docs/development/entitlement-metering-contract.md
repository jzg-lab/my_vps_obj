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
  After audited counter recovery, convert the logical cumulative cap back to the
  current raw panel counter using the recorded offset. Panel zero means unlimited,
  so exhausted identities use a positive cap and remain disabled.
  This is not simply `quota_bytes` after the first monthly switch. The mapping is
  owned by `service_panel_state.panel_traffic_limit(service, connection)`.
- `matches_service_terms(remote, service, squads, connection=...)` checks the same
  absolute limit, expiry, exact squads and `NO_RESET`. B must pass the connection.
  Creation uses the same mapping and remains disabled.

## Monthly switch

- Calendar bounds use `monthly_period(service.starts_at, now)` in Beijing time;
  keep the original anchor, skip missed months without accumulating allowances.
  Renewal does not change usage, anchor or cycle. Total packages never roll over.
- **User-confirmed refinement (2026-10-23):** the persisted cumulative checkpoint
  is the accounting cutover. Bytes after it belong to the new period; the page
  continues to show the old confirmed period until the remote absolute cap is
  verified. Healthy connections are not paused for rollover.
- `ServiceConnection.cycle_cutover_bytes` is immutable while a switch is pending.
  `ServiceUsagePeriod` stores the closed period's usage/quota, cutover and next
  calendar bounds before any panel write. The target is cutover plus period quota,
  not a fresh reading plus quota on every retry. Growing counters and lost replies
  therefore converge without issuing a second allowance.
- Confirmation moves the page to new-period usage (latest cumulative total minus
  fixed cutover), preserving overage. Commit this change before re-enabling a
  previously disabled identity. A failed DB commit retries the same fixed cap.
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

A3 decisions confirmed by the user on 2026-10-23: editing a template quota also
changes the current and future quota of every non-archived service opened from
that template. Existing usage is not reset; other snapshot terms are unchanged.
Counter anomaly recovery requires accurate, auditable reconciliation; estimates
are not accepted. No default forgiveness, counter reset or identity replacement
is implied.

See [independent services](independent-services.md), [requirements](../requirements.md)
and [implementation plan](../implementation-plan.md#10-剩余工作分包与协作).

## A1 cutover capability evidence and resolved tradeoff (2026-10-23)

The current adapter reads cumulative counters through
`panel_api_users.PanelApiUsersMixin.get_user_by_uuid_lookup` and separately writes
`PATCH /users` (`update_user_details_on_panel`). The write contract has no
counter precondition, period identifier, transactional sample-and-limit operation,
or application-database commit acknowledgment. `POST /users/{id}/actions/enable`
and `disable` are separate operations too. This is source/contract evidence, not
an assertion about untested Node behavior.

Let the old cumulative counter be 100, new monthly quota 1000, and the successful
PATCH cap 1100. If the read-back counter is 120 and all pre-confirmation bytes
must belong to the old cycle, the full new allowance requires cap 1120. If it is
130 at the next confirmation, cap 1130 is needed. The same issue occurs after a
lost response or failed local commit. Equal-counter retries can wait forever;
repeated rebasing can grant repeated extra traffic before a single cycle commits.

With the presently exposed API, the following cannot all be guaranteed together:
continuous connection, every byte until local confirmation billed to the old
period, bounded completion, and exactly one new full allowance across crashes.
No implementation may silently weaken one of these or pause healthy traffic.

The user explicitly accepted the persisted-checkpoint alternative after the
tradeoff was explained. This supersedes the earlier confirmation-time accounting
wording for A1. T owns the corresponding requirements/product/plan update.
Continuous traffic, lost PATCH replies and failed local confirmation commits are
covered by `tests/unit/test_service_entitlements.py`. Real Node counter latency
and enforcement are still unverified.

## B integration details

`service_ready_for_delivery(service, connection, resource, banned=..., now=...)`
checks local eligibility without changing connection state. It requires a bound
pending/ready identity, a confirmed usage observation, no usage/preparation error,
no pending entitlement change, and valid resource/service terms. The shared sync
entry returns a boolean, but B must additionally require `sync_pending == False`
and the readiness predicate before changing pending to ready: a disabled service
can be safely restricted while another term still awaits repair.

A's changes in `service_provisioning.py` are limited to importing/calling
`panel_traffic_limit` and passing `connection=connection` to `matches_service_terms`.
Preparation/delivery behavior remains B-owned. Migration 0113 also includes A3's
quota-change journal and raw-counter recovery fields; B retains 0114.
