import { adminErrorMessage } from "../errors.js";
import { builtApiPath } from "../../webapp/publicApi.js";
import type {
  AdminApi,
  AdminStoreState,
  AdminUser,
  ToastFn,
  TranslateFn,
} from "./usersStoreState.js";

export function createUsersStoreAccessActions({
  api,
  onToast,
  at,
  readStateSnapshot,
  applyState,
  invalidateUsersQueries,
  reportUserActionError,
}: {
  api: AdminApi;
  onToast: ToastFn;
  at: TranslateFn;
  readStateSnapshot: () => AdminStoreState;
  applyState: (updater: (state: AdminStoreState) => AdminStoreState) => void;
  invalidateUsersQueries: (userId?: number | string) => void;
  reportUserActionError: (error: unknown) => void;
}) {
  function requestBanToggle() {
    const s = readStateSnapshot();
    if (!s.openedUser) return;
    if (s.openedUser.is_banned) {
      applyBanToggle(false);
    } else {
      applyState((st) => ({ ...st, userBanConfirmOpen: true }));
    }
  }

  async function applyBanToggle(banned: boolean) {
    const s = readStateSnapshot();
    const openedUser = s.openedUser;
    if (!openedUser || s.userActionBusy) return;
    applyState((st) => ({ ...st, userActionBusy: true }));
    try {
      const res = await api(
        builtApiPath<"/api/admin/users/{user_id}/ban">(`/admin/users/${openedUser.user_id}/ban`),
        {
          method: "POST",
          body: JSON.stringify({ banned }),
        }
      );
      if (res?.ok) {
        invalidateUsersQueries(openedUser.user_id);
        applyState((st) => {
          const updatedUser: AdminUser = { ...openedUser, ...res.user };
          return {
            ...st,
            openedUser: updatedUser,
            users: st.users.map((u: AdminUser) =>
              u.user_id === updatedUser.user_id ? updatedUser : u
            ),
            userBanConfirmOpen: false,
          };
        });
        onToast(
          res.access_sync.pending
            ? at("account_access_saved_pending")
            : banned
              ? at("user_banned", {}, "User banned")
              : at("user_unbanned", {}, "User unbanned")
        );
      } else onToast(adminErrorMessage(res, at));
    } catch (error) {
      reportUserActionError(error);
    } finally {
      applyState((st) => ({ ...st, userActionBusy: false }));
    }
  }

  return { requestBanToggle, applyBanToggle };
}
