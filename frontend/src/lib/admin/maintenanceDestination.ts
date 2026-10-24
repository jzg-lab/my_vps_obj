/** Defense in depth for a server-sanitized public URL; never derive an API origin. */
export function maintenanceDestination(value: string | null | undefined): string | null {
  if (!value || value !== value.trim() || /\s|\\/.test(value)) return null;
  try {
    const url = new URL(value);
    if (
      !["http:", "https:"].includes(url.protocol) ||
      !url.hostname ||
      url.username ||
      url.password ||
      url.search ||
      url.hash
    )
      return null;
    return url.href;
  } catch {
    return null;
  }
}
