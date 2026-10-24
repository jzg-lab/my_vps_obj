"""Only classifications, never upstream bodies or arbitrary exception text."""

SAFE_RESOURCE_ERRORS = frozenset(
    {
        "resource_operation_in_progress",
        "resource_operation_not_found",
        "resource_operation_changed",
        "resource_sources_incomplete",
        "resource_preview_changed",
        "resource_write_unknown",
        "resource_write_rejected",
        "resource_partial_write",
        "resource_target_removed",
        "resource_manual_reconciliation_required",
        "resource_evidence_invalid",
        "resource_retry_not_allowed",
        "resource_recovery_invalid",
        "resource_prior_write_unknown",
        "resource_replacement_in_progress",
        "resource_dry_run",
        "resource_panel_unsupported",
        "resource_create_conflict",
        "resource_deployment_unavailable",
        "resource_idempotency_conflict",
        "invalid_resource_operation_request",
    }
)


def safe_resource_error(value: str | None) -> str | None:
    return value if value is None or value in SAFE_RESOURCE_ERRORS else "resource_write_unknown"
