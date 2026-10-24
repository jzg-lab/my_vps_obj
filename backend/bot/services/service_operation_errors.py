"""Only known classifications may cross an administrator response boundary."""

SAFE_SERVICE_ERRORS = frozenset(
    {
        "resource_operation_in_progress",
        "exit_replacement_in_progress",
        "exit_replacement_state_invalid",
        "exit_replacement_write_unknown",
        "exit_replacement_write_failed",
        "exit_replacement_sources_incomplete",
        "exit_replacement_scope_changed",
        "exit_replacement_authorizations_unavailable",
        "exit_replacement_usage_unconfirmed",
        "exit_replacement_stop_unconfirmed",
        "exit_replacement_stop_evidence_required",
        "exit_replacement_close_evidence_required",
        "exit_replacement_interrupted",
        "exit_replacement_panel_unsupported",
        "panel_identity_unconfirmed",
        "panel_identity_missing",
        "panel_identity_conflict",
        "panel_identity_terms_mismatch",
        "panel_change_unconfirmed",
        "panel_cycle_unconfirmed",
        "panel_cycle_conflict",
        "panel_limit_invalid",
        "panel_usage_unavailable",
        "panel_usage_unconfirmed",
        "panel_usage_invalid",
        "panel_usage_regressed",
        "panel_usage_reset",
        "service_delivery_pending",
        "service_revoke_pending",
        "service_revoke_cycle_pending",
        "service_revoke_usage_unconfirmed",
        "service_revision_changed",
        "idempotency_owner_changed",
        "account_banned",
        "service_expired",
        "service_exhausted",
        "service_not_deliverable",
    }
)
CONFIRMED_SERVICE_FAILURES = frozenset(
    {
        "panel_identity_missing",
        "panel_identity_conflict",
        "panel_identity_terms_mismatch",
        "panel_cycle_conflict",
        "panel_limit_invalid",
        "panel_usage_invalid",
        "panel_usage_regressed",
        "panel_usage_reset",
        "account_banned",
        "service_expired",
        "service_exhausted",
        "service_not_deliverable",
    }
)


def safe_service_error(error: str | None) -> str | None:
    return error if error is None or error in SAFE_SERVICE_ERRORS else "unclassified_service_error"
