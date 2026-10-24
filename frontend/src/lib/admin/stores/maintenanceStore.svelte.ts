import { unwrap, type ApiClient } from "$lib/webapp/publicApi";
import { maintenanceDestination } from "$lib/admin/maintenanceDestination";

type MaintenanceState =
  { status: "loading" | "error" | "unconfigured" } | { status: "ready"; destination: string };

export function createMaintenanceStore(api: ApiClient["api"]) {
  let state = $state<MaintenanceState>({ status: "loading" });
  let request = 0;
  let controller: AbortController | null = null;

  async function load() {
    const id = ++request;
    controller?.abort();
    controller = new AbortController();
    state = { status: "loading" };
    try {
      const result = unwrap(await api("/admin/console/maintenance", { signal: controller.signal }));
      if (id !== request) return;
      if (result.destination === null) {
        state = { status: "unconfigured" };
      } else {
        const destination =
          typeof result.destination === "string"
            ? maintenanceDestination(result.destination)
            : null;
        // Only an explicit null means unconfigured; malformed responses are failures.
        state = destination ? { status: "ready", destination } : { status: "error" };
      }
    } catch {
      if (id === request) state = { status: "error" };
    }
  }

  return {
    get state() {
      return state;
    },
    load,
    dispose() {
      request++;
      controller?.abort();
      state = { status: "loading" };
    },
  };
}
