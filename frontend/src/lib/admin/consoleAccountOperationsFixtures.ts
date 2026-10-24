import type { AccountOperation } from "./consoleAccountOperations";

// Explicit synthetic audit evidence for unit/browser tests, not a worker execution simulator.
export function accountOperationFixture(
  overrides: Partial<AccountOperation> = {}
): AccountOperation {
  return {
    id: "a".repeat(32),
    actor_id: 910001,
    target_id: 910002,
    user_id: 910002,
    before_banned: false,
    desired_banned: true,
    source: "administrator",
    status: "unknown",
    attempt_count: 2,
    created_at: "2026-10-24T00:00:00Z",
    attempted_at: "2026-10-24T00:02:00Z",
    first_failed_at: "2026-10-24T00:01:00Z",
    completed_at: null,
    error_code: "panel_access_unconfirmed",
    archived: false,
    needs_attention: true,
    ...overrides,
  };
}
