import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
import type { ResourcePreview } from "./resourcePreview";

const blockerKeys = new Map<string, string>(
  Object.entries({
    target_not_found: "console_resource_blocker_target_not_found",
    duplicate_service_binding: "console_resource_blocker_duplicate_service_binding",
    missing_dedicated_binding: "console_resource_blocker_missing_dedicated_binding",
    invalid_service_scope: "console_resource_blocker_invalid_service_scope",
    archived_resource_scope_unconfirmed: "console_resource_blocker_archived_scope",
    missing_service_group: "console_resource_blocker_missing_service_group",
    inconsistent_inbound_profile: "console_resource_blocker_inconsistent_inbound_profile",
    inconsistent_profile_nodes: "console_resource_blocker_inconsistent_profile_nodes",
    missing_node_profile: "console_resource_blocker_missing_node_profile",
    missing_node_inbound: "console_resource_blocker_missing_node_inbound",
    missing_group_inbound: "console_resource_blocker_missing_group_inbound",
    missing_host_inbound: "console_resource_blocker_missing_host_inbound",
    missing_host_scope: "console_resource_blocker_missing_host_scope",
    unsupported_host_address: "console_resource_blocker_unsupported_host_address",
    unknown_proposed_inbound: "console_resource_blocker_unknown_proposed_inbound",
    unknown_host_selection: "console_resource_blocker_unknown_host_selection",
    unknown_host_inbound: "console_resource_blocker_unknown_host_inbound",
    node_disabled: "console_resource_blocker_node_disabled",
    node_has_no_active_inbounds: "console_resource_blocker_node_has_no_active_inbounds",
    replacement_scope_unconfirmed: "console_resource_blocker_replacement_scope",
    replacement_service_unconfirmed: "console_resource_blocker_replacement_service",
    replacement_customer_unavailable: "console_resource_blocker_replacement_customer",
    replacement_resource_held: "console_resource_blocker_replacement_held",
    replacement_state_invalid: "console_exit_replacement_state_invalid",
    exit_replacement_in_progress: "console_exit_replacement_in_progress",
  })
);

export function resourceBlockerText(code: string, at: ConsoleNodesTranslate): string {
  const key = blockerKeys.get(code);
  if (key) return at(key);
  const sourceFailure =
    /^(metadata|nodes|hosts|groups|profiles|services|authorizations)_(unavailable|invalid|unsupported)$/.exec(
      code
    );
  if (sourceFailure) {
    const [, source, availability] = sourceFailure;
    return at(`console_resource_blocker_source_${availability}`, {
      source: at(
        source === "nodes" || source === "hosts"
          ? `console_nodes_source_${source}`
          : `console_resource_source_${source}`
      ),
    });
  }
  return at("console_resource_blocker_unknown");
}

const recoveryKeys = {
  restore_previous_inbounds_and_recheck_profile_nodes: "console_resource_recovery_inbounds",
  restore_previous_host_and_refresh_subscription: "console_resource_recovery_host",
  inverse_node_action_requires_fresh_preview: "console_resource_recovery_inverse",
  restart_has_no_automatic_rollback: "console_resource_recovery_restart",
  creation_requires_explicit_reconciliation_no_automatic_delete: "resource_ops_recovery_create",
} satisfies Record<ResourcePreview["recovery"], string>;

export function resourceRecoveryKey(recovery: ResourcePreview["recovery"]): string {
  return Object.hasOwn(recoveryKeys, recovery)
    ? recoveryKeys[recovery]
    : "console_resource_recovery_unknown";
}
