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

### Cancelled-service reconciliation and terminal settlement

Cancelled services with a retained identity may reconcile exact usage after the
same ownership, stopped-panel-state and exact-counter checks as paused services.
Reconciliation preserves `cancelled`, the identity and all previous usage; pause,
resume and renewal remain rejected. Revoked identities are not editable. The
shared entitlement synchronizer only confirms restriction for cancelled services:
it never patches their allowance/expiry or confirms their pending monthly switch.

B can replace its pending-cycle revocation blocker with this shared entry:

```python
async def settle_cancelled_service_period(
    session: AsyncSession,
    service: UserService,
    connection: ServiceConnection,
    remote: dict[str, Any],
    *,
    actor_id: int,
    now: datetime | None = None,
) -> bool:
    ...
```

The function lives in `bot.services.service_period_sync`. The caller holds the
account row lock and supplies a fresh read-back of the bound identity, confirmed
`DISABLED`, `LIMITED` or `EXPIRED`. Pass the initiating revocation administrator as
`actor_id` from B's persisted revoke order. It rejects unresolved usage errors,
ownership mismatches and invalid/reset/regressing counters. Accurate anomaly
reconciliation must finish first; no estimates or missing-history forgiveness are
introduced. The helper performs no panel calls.

For a pending cutover, the same transaction:

- Retains the old `ServiceUsagePeriod` unchanged, including original usage/quota,
  fixed cutover and **null `confirmed_at`**.
- Sets displayed post-cutover usage to accepted cumulative total minus that cutover,
  using the original pending period's next calendar bounds. Desired status,
  quota, expiry, original terms and identity remain unchanged.
- Adds one immutable `ServiceOrder(kind="settle_usage")`: the snapshot stores
  old period dates/usage, next dates, `cutover_bytes`, `usage_total_bytes`,
  `usage_raw_bytes`, `usage_lifetime_offset`, resulting `used_bytes`, bound panel
  UUID/status, observation time and `allowance_confirmed=false`. The request key
  is `settle:<service_id>:<old_cycle_started_at ISO timestamp>`.
- Clears `connection.cycle_cutover_bytes`, so existing API `cycle_pending` becomes
  false for the cancelled service. It does not clear B's revocation retry intent,
  mark the identity revoked or release an exit resource.

True means the supplied observation was accepted **in the current transaction**,
not that revocation or Node enforcement is complete. The helper flushes but does not commit.
B must first commit settlement, then reacquire the account lock and read the same
stopped identity again, retaining its ownership/cancellation checks. Any later
accepted observation must also be committed before DELETE. With no remaining cutover the helper only
accepts the fresh usage observation; it creates no second settlement order.
Rollback leaves the original pending checkpoint and usage intact. Repeated calls
under the account lock cannot grant another allowance or duplicate the audit.

Clearing the pending marker does **not** freeze final usage. After reacquiring the
lock and reading the same stopped identity again, B must accept and commit any
new bytes with `record_service_usage`/this helper before DELETE. Calling both on
the same sample adds nothing twice: after the initial settlement, both cumulative
and service usage advance by the same raw-counter delta, preserving
`used_bytes = usage_total_bytes - original_cutover_bytes`. For a cutover of 900,
the first observation of 1200 records 300 bytes; a later observation of 1225
records 325 bytes, and repeating 1225 still records 325. The original audit stays
at its own 1200-byte observation; it is not evidence that no further traffic can
arrive. Counter anomalies still block deletion until accurately reconciled. No
retry confirms an allowance. Regression:
`test_terminal_retries_count_late_bytes_once_and_block_late_counter_anomalies`.
The focused follow-up passed 18 tests and 5 subtests, scoped Ruff/mypy and docs
consistency checks. Runtime logic was unchanged; full suites/builds/browser checks
were not repeated for this test-and-contract clarification.

No schema/API fields or migration 0115 are needed. Do not edit 0113 or 0114.

UI handoff to B: `serviceChangeActions(service)` in `lib/admin/serviceChanges.ts`
returns only `reconcile_usage` for cancelled, non-revoked services with
`panel_usage_reset`/`panel_usage_regressed`; otherwise cancelled services return
no actions. Use its nonempty result to expose **Manage** independently of the
existing **Revoke** condition. The dialog defaults cancelled services to exact
reconciliation. The shared history parser accepts cancelled reconciliation and
`settle_usage`; the history dialog explains post-checkpoint/cumulative usage and
explicitly says no allowance was confirmed, rather than presenting a quota grant.
Final revoked records must use the persisted cleared checkpoint, not a fabricated
cycle confirmation. B/C own merged desktop/mobile verification.

C locale handoff (English/Russian provided): changed
`admin_services_usage_reconcile`, `admin_services_reconcile_hint`,
`admin_services_usage_reconciliation_pause_required`; new
`admin_services_settle_usage`, `admin_services_terminal_usage_hint`.

Follow-up regressions cover cancellation before reset/regression, stopped-state
verification, exact correction without re-enabling, blocked pause/resume/renew,
terminal rollback/retry, unchanged old-period evidence, final UI `cycle_pending`
and invalid ownership/counter/period guards. The authored PostgreSQL test
`test_parallel_terminal_settlement_writes_one_audit_without_confirming_allowance`
checks eight serialized retries and one immutable terminal order; execution is
reserved for the main window's isolated integrated environment. Browser and build
time remains allocated to B; this patch does not claim merged UI verification.
The follow-up full backend run passed **5,593 tests and 636 subtests**, with
**48 skipped**. Frontend unit tests passed **1,499 tests in 203 files**; full mypy,
Ruff lint/format, frontend static checks, architecture and docs consistency checks
passed. Frontend/docs builds, browser checks and the new PostgreSQL concurrency
test were not run for this follow-up because the integrated browser/build and
database slots belong to B/the main window.

## Local validation and remaining acceptance (2026-10-23)

Implementation checkpoint: `1476ddb1`. Validation used the isolated A worktree,
local SQLite/unit fixtures and the docs-demo browser runtime; no production node,
shared PostgreSQL database or real panel was mutated.

- Backend full suite: **5,587 passed, 45 skipped, 631 subtests passed**. Full mypy
  passed for 1,340 files; Ruff lint/format and architecture gates passed.
- Two subsequent entitlement regression cases cover pause/ban/expiry at rollover
  and exhaustion observed during enabling. The final entitlement module run is
  **9 passed, 3 subtests passed**, with scoped Ruff and mypy passing.
- Frontend static checks, production build and unit suite passed: **1,492 tests
  in 203 files**. The final mock fixture also passed TypeScript, ESLint and Prettier.
- Complete browser regression: **253 passed** at desktop/mobile sizes. The six
  metering scenarios cover quota edit validation, exact-reconciliation history
  and pending-cycle display; screenshots include dialogs and open action menus.
- Docs sidebar/API-sync checks, documentation build, lockfile and development
  seed checks passed. Commands are recorded in [CONTRIBUTING](../../CONTRIBUTING.md#1-гейты-качества--выбирай-по-зоне-изменений-перед-пушем).

Reproduce the focused regressions from the repository root:

```sh
python -m pytest -q tests/unit/test_service_entitlements.py tests/unit/test_service_adjustments.py
npm --prefix frontend run test:e2e -- e2e/service-metering.spec.ts
```

On macOS, use Homebrew OpenSSL before system LibreSSL in `PATH` for the full
backend suite's installer certificate tests. The browser suite normally rebuilds
the demo; `PLAYWRIGHT_SKIP_DEMO_BUILD=1` is only valid after a current-source build.

The new PostgreSQL tests in `tests/integration/test_user_services_postgres.py`
were **not run**: a scheduled disposable database is still required. They cover
idempotent migration 0113, template quota editing concurrent with activation,
and eight concurrent monthly retries with growing counters. They use
`CORE_PERFORMANCE_TEST_DATABASE_URL` and isolated disposable schemas; do not
point them at production or run against a shared stand without coordination.
Real Node enforcement, counter latency, long-lived connections and subscription
revocation still require B/D acceptance. Crash/failed-commit retry tests do not
prove safety after restoring an older whole-database backup; that belongs to E's
recovery procedure and requires independent usage evidence.

### Localization handoff to C

English and Russian base entries are present. Chinese localization must include
these 16 new or changed keys:

```text
admin_services_snapshot_hint
admin_services_usage_reconcile
admin_services_quota_reason
admin_services_quota_scope_hint
admin_services_quota_change_reason_required
admin_services_reconcile_usage
admin_services_reconcile_hint
admin_services_last_total_bytes
admin_services_verified_total_bytes
admin_services_expected_raw_bytes
admin_services_reconcile_evidence
admin_services_usage_reconciliation_changed
admin_services_usage_reconciliation_pause_required
admin_services_usage_reconciliation_unavailable
admin_services_cycle_pending
wa_services_cycle_pending
```
