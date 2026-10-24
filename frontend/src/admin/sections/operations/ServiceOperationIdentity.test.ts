import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import ServiceOperationList from "../services/ServiceOperationList.svelte";
import { operationFixture } from "$lib/admin/consoleServiceOperationsFixtures";
import { consoleNodeServiceFixture } from "$lib/admin/consoleNodesFixtures";
import { createConsoleServiceOperationsDemo } from "$lib/webapp/mockApi/consoleServiceOperations";
import type { ServiceOperations } from "$lib/admin/consoleServiceOperations";

describe("single-service operation identity after global navigation", () => {
  const execution = { ...operationFixture, retryable: false, status: "unknown" as const };
  const legacy = {
    ...execution,
    phase: null,
    source: "unknown" as const,
    order_id: execution.id,
    target_revision: null,
    attempt_count: null,
    attempted_at: null,
    first_failed_at: null,
    error_code: null,
    retry_block_reason: "historical_result_unknown",
  };
  const data: ServiceOperations = {
    service_id: execution.service_id,
    service_revision: 3,
    operations: [execution, legacy],
    total: 2,
    offset: 0,
    limit: 25,
  };
  it("the existing adapter returns both record types with the same ID on the first diagnostics page", () => {
    const result = createConsoleServiceOperationsDemo()(
      `/admin/console/services/${execution.service_id}/operations?limit=25&offset=0`,
      {},
      {
        owner: 0,
        services: [consoleNodeServiceFixture.service],
        archived: [],
        plans: [],
        exits: [],
        operations: [execution],
        orders: [
          {
            id: execution.id,
            service_id: execution.service_id,
            user_id: 910001,
            kind: "activate",
            actor_id: 7,
            created_at: execution.created_at,
            snapshot: {},
          },
        ],
      }
    );
    expect(result).toMatchObject({
      total: 2,
      operations: [
        { id: execution.id, phase: "entitlement" },
        { id: execution.id, phase: null },
      ],
    });
  });
  it("uses separate row identities and does not give the historical order an execution receipt", () => {
    const html = render(ServiceOperationList, {
      props: {
        at: (key: string) => key,
        data,
        pending: {
          [execution.id]: {
            user_id: 910001,
            expected_revision: 3,
            idempotency_key: "lost-receipt",
          },
        },
        readonly: false,
        disabled: false,
        onretry: () => {},
        onpage: () => {},
      },
    }).body;
    const rows = [...html.matchAll(/<tr\b[^>]*>[\s\S]*?<\/tr>/g)].map((match) => match[0]);
    const history = rows.find((row) => row.includes("console_ops_history_unknown"))!;
    expect(history).toBeDefined();
    expect(history).not.toContain("console_ops_confirm_receipt");
    expect(history).not.toContain("console_ops_uncertain_receipt");
    expect(html.match(/console_ops_confirm_receipt/g)).toHaveLength(1);
    expect(html).toContain(`data-operation-key="execution:${execution.id}"`);
    expect(html).toContain(`data-operation-key="order:${execution.id}"`);
  });
});
