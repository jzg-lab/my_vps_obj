const labels: Record<string, string> = {
  verify: "services_exit_verify",
  reclaim: "services_exit_reclaim",
  replace_reserve: "replacement_audit_reserve",
  replace_stop: "replacement_audit_stop",
  replace_verify: "replacement_audit_verify",
  replace_confirm: "replacement_audit_confirm",
  replace_write_result: "replacement_audit_write_result",
  replace_bind: "replacement_audit_bind",
  replace_cleanup: "replacement_audit_cleanup",
  replace_close_stop: "replacement_audit_close_stop",
  replace_reclaim: "replacement_audit_reclaim",
  replace_dispatch_skip: "replacement_audit_dispatch_skip",
};
export function exitAuditActionLabel(action: string): string {
  return Object.hasOwn(labels, action) ? labels[action] : "console_unknown";
}
export const exitAuditActionKeys = Object.values(labels);
