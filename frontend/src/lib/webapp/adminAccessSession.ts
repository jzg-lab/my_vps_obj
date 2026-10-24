import { shellState } from "./shellState.svelte";
import { clearEmojiPreviewStorage } from "./emojiPreviewStorage";

export function revokeAdminAccess({
  destroyAdminMount,
  cancelAdminAssetsPrefetch,
  syncAppSectionPath,
}: {
  destroyAdminMount: () => void;
  cancelAdminAssetsPrefetch: () => void;
  syncAppSectionPath: (section: string, replace?: boolean) => void;
}): void {
  shellState.adminAccessRevoked = true;
  shellState.adminAccessVersion += 1;
  const user = shellState.data?.user;
  if (shellState.data && user && typeof user === "object") {
    shellState.data = { ...shellState.data, user: { ...user, is_admin: false } };
  }
  cancelAdminAssetsPrefetch();
  destroyAdminMount();
  void clearEmojiPreviewStorage();
  shellState.adminActiveSection = "stats";
  if (shellState.screen === "admin") {
    shellState.screen = "settings";
    shellState.activeTab = "settings";
    syncAppSectionPath("settings", true);
  }
}
