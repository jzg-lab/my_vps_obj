import type { ComponentProps } from "svelte";
import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import { createUsersStore, type UsersStore } from "$lib/admin/stores/usersStore";
import type { AdminApi, AdminUserDetailResponse } from "$lib/admin/stores/usersStoreState";
import type { ApiClient } from "$lib/webapp/publicApi";
import ServiceHistorySection from "../ServiceHistorySection.svelte";
import UserDetailView from "./UserDetailView.svelte";

vi.mock("$lib/admin/context", () => ({
  getAdminServiceModel: () => ({ independent: true }),
  getSettingsStore: () => ({ features: [] }),
  getAdminApi: (): ApiClient["api"] => async () => {
    throw new Error("Server rendering must not request services");
  },
}));

const noop = () => {};
const at = (key: string) => key;
const minishopId = "ms_" + "a".repeat(32);
function detailResponse(userId = 42): AdminUserDetailResponse {
  return {
    ok: true,
    user: {
      user_id: userId,
      minishop_id: minishopId,
      account_id: null,
      avatar_url: null,
      email: null,
      first_name: null,
      is_banned: false,
      language_code: null,
      last_name: null,
      panel_user_uuid: null,
      panel_username: null,
      panel_username_state: null,
      referral_code: null,
      referred_by_id: null,
      registration_date: null,
      telegram_id: null,
      telegram_photo_url: null,
      username: null,
    },
    active_subscription: null,
    subscriptions: [],
    balance: {
      ok: true,
      amount: "0",
      amount_minor: 0,
      currency: "USD",
      currency_scale: 2,
      enabled: false,
      sources: [],
      topup_max_amount: 0,
      topup_min_amount: 0,
      topup_presets: [],
    },
    hwid_devices: { current_devices: null, max_devices: null },
    install_share_url: null,
    last_vpn_connected_at: null,
    log_count: 0,
    notification_preferences: {
      marketing_email: false,
      marketing_telegram: false,
      system_email: false,
      system_telegram: false,
    },
    panel_squad_overrides: null,
    panel_user_url: null,
    partner_attribution: null,
    recent_payments: [],
    referral: { bot_link: null, code: null, invitees_total: 0, inviter: null, webapp_link: null },
    subscription_url: null,
    telegram_notifications: {
      status: "unknown",
      blocked_at: null,
      checked_at: null,
      enabled_at: null,
    },
    total_paid: 0,
    trial: {
      active: false,
      count: 0,
      first_activated_at: null,
      last_reset_at: null,
      latest_activated_at: null,
      latest_end_date: null,
      used: false,
    },
    vpn_connection_status: "unknown",
  };
}
function lookup() {
  let resolve!: (response: AdminUserDetailResponse) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<AdminUserDetailResponse>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  const api = vi.fn<AdminApi>().mockResolvedValue({ ok: false, error: "unexpected_request" });
  api.mockImplementationOnce(() => promise);
  const store = createUsersStore({ api, at, onToast: noop });
  return { api, store, resolve, reject };
}

function viewProps(store: UsersStore): ComponentProps<typeof UserDetailView> {
  return {
    at,
    usersStore: store,
    openedUser: store.openedUser,
    // Only the identity/loading boundary is under test, not unrelated detail tabs.
    openedUserDetail: null,
    userDetailLoading: store.userDetailLoading,
    routePrefix: "/app",
    onRetry: noop,
    openedUserAvatarUrl: "",
    openAvatarPreview: noop,
    userInitials: () => "QA",
    userDisplayName: () => "Customer",
    openUserTelegramProfile: noop,
    openedUserTelegramProfileLink: "",
    openedUserTelegramProfileHint: "",
    fmtMoney: String,
    fmtDate: String,
    vpnLastConnectionLabel: () => "",
    referralInviter: null,
    referralInviteesTotal: 0,
    openRelatedUser: noop,
    subscriptionDisplayLabel: () => "",
    pretty: String,
    hwidLimitLabel: () => "",
    trafficOfLabel: () => "",
    trafficLeftLabel: () => "",
    trafficPercentValue: () => 0,
    trialSummaryText: () => "",
    fmtDateShort: String,
    paymentStatusVariant: () => "muted",
    onOpenPaymentCard: noop,
    onOpenPartnerCard: noop,
    userLogsRows: [],
    userLogsTotal: 0,
    userLogsPage: 0,
    userLogsPageCount: 1,
    userLogsPageSize: 20,
    userLogsLoading: false,
    userLogsLoaded: false,
    userActionBusy: false,
    extendTariffItems: [],
    extendTariffsLoading: false,
    userExtendDaysValid: false,
    userExtendTariffValid: false,
    extendTariffRequired: false,
    selectExtendTariff: noop,
    periodTariffItems: [],
    tariffActionDirty: false,
    tariffHwidLimitChangeAvailable: false,
    currentSubscriptionTariffLabel: "",
    userTariffActionKey: "",
    selectTariffAction: noop,
    trafficStrategyItems: [],
    trafficStrategyDirty: false,
    trafficStrategyDraftValid: false,
    trafficStrategyEditable: false,
    trafficStrategyCurrentLabel: "",
    trafficStrategyLockMessage: "",
    selectTrafficStrategy: noop,
    premiumOverrideDirty: false,
    premiumOverrideDraftValid: false,
    premiumUnlimitedDraft: false,
    regularOverrideDirty: false,
    regularOverrideDraftValid: false,
    regularUnlimitedDraft: false,
    hwidLimitDirty: false,
    hwidLimitDraftValid: false,
    hwidUnlimitedDraft: false,
    selectGrantTrafficKind: noop,
    grantTrafficGbValid: false,
    panelSquadItems: [],
    squadLabel: String,
    userSquadOverrideDraft: "",
    selectUserSquadOverride: noop,
    userExternalSquadModeDraft: "inherit",
    selectUserExternalSquadMode: noop,
    userExternalSquadUuidDraft: "",
    updateUserExternalSquadUuid: noop,
  };
}
const view = (store: UsersStore) => render(UserDetailView, { props: viewProps(store) }).body;

describe("customer service owner resolution", () => {
  it("does not mount services for the unresolved minishop route placeholder", async () => {
    const { store, api, resolve } = lookup();
    const opening = store.openUser(minishopId, { skipPush: true });
    try {
      expect(store.openedUser).toMatchObject({ user_id: 0, minishop_id: minishopId });
      const html = view(store);
      expect(html).toContain(minishopId);
      expect(html).toContain('aria-busy="true"');
      expect(html).not.toContain('class="user-services');
      expect(html).not.toContain("services_activate");
      expect(html).not.toContain("services_history_title");
    } finally {
      resolve(detailResponse());
      await opening;
    }
    expect(api).toHaveBeenCalledExactlyOnceWith(`/admin/users/${minishopId}`);
    expect(store.openedUser?.user_id).toBe(42);
    expect(view(store)).toContain('class="user-services');
  });

  it.each([42, -42])(
    "keeps signed owner %s available before and after detail resolution",
    async (userId) => {
      const { store, resolve } = lookup();
      const opening = store.openUser(
        { user_id: userId, minishop_id: minishopId },
        { skipPush: true }
      );
      try {
        expect(store.userDetailLoading).toBe(true);
        expect(view(store)).toContain('class="user-services');
        expect(view(store)).not.toContain("services_history_title");
      } finally {
        resolve(detailResponse(userId));
        await opening;
      }
      expect(store.openedUser?.user_id).toBe(userId);
      expect(view(store)).toContain('class="user-services');
    }
  );

  it("keeps a failed unresolved lookup retryable without mounting services", async () => {
    const { store, reject } = lookup();
    const opening = store.openUser(minishopId, { skipPush: true });
    reject(new Error("offline"));
    await opening;
    expect(store.openedUser?.user_id).toBe(0);
    const html = view(store);
    expect(html).toContain("user_detail_retry");
    expect(html).not.toContain('class="user-services');
    expect(html).not.toContain("services_history_title");
  });

  it("does not resurrect a closed customer from a late lookup response", async () => {
    const { store, resolve } = lookup();
    const opening = store.openUser(minishopId, { skipPush: true });
    store.closeUser({ skipPush: true });
    expect(store.openedUser).toBeNull();
    expect(view(store)).not.toContain('class="user-services');
    resolve(detailResponse());
    await opening;
    expect(store.openedUser).toBeNull();
    expect(view(store)).not.toContain('class="user-services');
  });

  it("does not mount the zero owner when reopening a resolved customer by route", async () => {
    const { store, api, resolve } = lookup();
    const first = store.openUser(minishopId, { skipPush: true });
    resolve(detailResponse());
    await first;
    expect(view(store)).toContain('class="user-services');
    store.closeUser({ skipPush: true });
    api.mockResolvedValueOnce(detailResponse());
    const reopening = store.openUser(minishopId, { skipPush: true });
    try {
      expect(store.openedUser?.user_id).toBe(0);
      expect(view(store)).not.toContain('class="user-services');
    } finally {
      await reopening;
    }
    expect(store.openedUser?.user_id).toBe(42);
    expect(view(store)).toContain('class="user-services');
  });

  it("preserves the explicit null owner as read-only deleted-account history", () => {
    const html = render(ServiceHistorySection, { props: { at } }).body;
    expect(html).toContain('class="user-services');
    expect(html).toContain("services_history_title");
    expect(html).toContain("services_history_hint");
    expect(html).not.toContain("services_activate");
  });
});
