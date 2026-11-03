/** Keep normal console clicks in the app while preserving native link behavior. */
export function navigateConsoleLink(event: MouseEvent): void {
  const link = event.currentTarget;
  if (
    event.defaultPrevented ||
    event.button !== 0 ||
    event.metaKey ||
    event.ctrlKey ||
    event.shiftKey ||
    event.altKey ||
    !(link instanceof HTMLAnchorElement) ||
    link.hasAttribute("download") ||
    (link.target && link.target !== "_self")
  )
    return;
  const url = new URL(link.href);
  if (url.origin !== window.location.origin) return;
  event.preventDefault();
  window.history.pushState(null, "", url);
  window.dispatchEvent(new PopStateEvent("popstate"));
}
