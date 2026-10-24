export const demoUserRoutes = [
  "home",
  // Checkout renders home with plan selection open; it still needs a page so
  // the static demo serves the route.
  "plans",
  "checkout",
  "install",
  "trial",
  "invite",
  "devices",
  "support",
  "settings",
  "login",
  "login/password",
];

export const demoAdminRoutes = [
  "stats",
  "console-overview",
  "console-operations",
  "users",
  "services",
  "nodes",
  "node-resources",
  "service-plans",
  "dedicated-exits",
  "service-history",
  "payments",
  "promos",
  "gifts",
  "partners",
  "ads",
  "broadcast",
  "logs",
  "support",
  "tariffs",
  "appearance",
  "documents",
  "translations",
  "backups",
  "plugins",
  "advanced-maintenance",
  "settings",
];

export const demoPublicRouteAliases = ["app"];
const demoAdminDetailRoutes = ["admin/settings/menu-buttons"];

export const demoPublicRoutes = [
  ...demoPublicRouteAliases,
  ...demoUserRoutes,
  "emails",
  "admin",
  ...demoAdminRoutes.map((route) => `admin/${route}`),
  ...demoAdminDetailRoutes,
];

export const demoRuntimeRoutes = [
  ...demoUserRoutes,
  "admin",
  ...demoAdminRoutes.map((route) => `admin/${route}`),
  ...demoAdminDetailRoutes,
];
