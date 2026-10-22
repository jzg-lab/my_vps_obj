# 独立服务权益与计量契约

<!-- 保留翻译前的章节锚点，以兼容既有链接。 -->
<a id="independent-service-entitlement-and-metering-contract"></a>

A/B 协作检查点，2026-10-23。基线：`ace4746328534fdd90d02eb98d85053bf7e4852d`。
本文定义实现边界，不代表真实节点已通过验收。

## 计数与限额

<a id="counters-and-limits"></a>

- 每份服务独占一个面板身份，必须采用 `NO_RESET`。不得通过重置面板计数、
  更换身份或复制账号原有身份来补充额度。
- `ServiceConnection.usage_total_bytes` 是最近一次被接受的累计有效载荷字节数观测；
  `UserService.used_bytes` 是业务周期内已确认的用量，总量套餐则覆盖服务整个生命周期。
  两者都包含上传与下载，并保留超额用量。重复样本不增加用量。
  计数回退或重置策略会触发并锁定核对错误，之后即使读到更大数值也不能自动清除。
- 面板预期限额为**绝对累计上限**：累计总量减去当前周期已用量，再加周期额度。
  首次观测前基线为零。经审计恢复计数后，使用记录的偏移映射，将逻辑累计上限换算为
  当前面板原始计数对应的上限。面板将零解释为不限量，因此额度耗尽的身份仍设置正数上限，
  并保持停用。首次月度切换后，上限不再简单等于 `quota_bytes`；
  该映射统一由 `service_panel_state.panel_traffic_limit(service, connection)` 负责。
- `matches_service_terms(remote, service, squads, connection=...)` 检查同一绝对上限、
  到期时间、精确匹配的节点组及 `NO_RESET`。B 必须传入连接对象。
  创建身份时使用相同映射，并保持停用。

## 月度切换

<a id="monthly-switch"></a>

- 日历周期通过 `monthly_period(service.starts_at, now)` 按北京时间计算；
  保留原始锚点，跳过错过的月份，不累积额度。续期不改变用量、锚点或周期。
  总量套餐不进行月度切换。
- **用户已确认的细化规则（2026-10-23）：**持久化的累计计数检查点就是计量切点。
  切点后的字节计入新周期；远端绝对上限核对成功前，页面继续展示旧周期的已确认数据。
  月度切换不暂停正常连接。
- 切换待确认期间，`ServiceConnection.cycle_cutover_bytes` 不得变化。
  任何面板写入前，`ServiceUsagePeriod` 已保存旧周期的用量与额度、固定切点及下一周期日期。
  目标上限是切点加周期额度，不是在每次重试时重新读取计数再加额度。
  因此即使计数持续增长或响应丢失，重试仍能收敛，不会重复发放额度。
- 确认后，页面改为展示新周期用量，即最新逻辑累计总量减去固定切点，并保留超额用量。
  重新启用此前停用的身份前，必须先提交这项本地变更。
  数据库提交失败时，继续重试同一个固定上限。
- 服务到期或取消后，不授予新周期额度。月度切换不会使暂停服务或被封禁账号的连接重新启用。
  待交付连接仍保持待交付。面板与节点的计数采样延迟仍需验收，不能据此承诺零超额。

## 共用资格判断与同步

<a id="shared-eligibility-and-synchronization"></a>

- `user_service_access.service_status(...)` 统一规定业务资格判断顺序：
  账号封禁或已删除、服务暂停或取消、到期、已确认额度耗尽、开始时间与准备状态、
  专用资源已核实，最后才是可用状态。仅仅用量未知不等于额度耗尽。
- `service_change_sync.synchronize_service_change(session_factory, service_id, panel)`
  是公开重试入口。A 还提供
  `synchronize_service_entitlement_locked(session, user, service, connection, panel)`，
  供已持账号锁的调用方使用，包括 B 的交付流程与账号访问控制。
  该入口重新读取归属和条款，应用预期到期时间与绝对上限，再核对后决定是否启用。
  它不会将连接标记为已就绪。
- B 负责建立交付就绪条件，并在同一账号锁内调用该共用入口；
  远端写入前必须持久化重试标记。B 不另算限额、不重置计数，也不另建启用或停用规则。
- 用量与周期处理、服务变更、账号封禁与解封、交付流程都通过账号行锁串行执行。
  等待远端操作后须重新检查时间。已知的到期、额度耗尽、暂停和封禁优先；
  未知样本不会清除用量，也不会强制断开其他条件已确认正常的服务。
  重新启用要求条款已核实且计量可用；未解决的计数异常会阻止启用。
- 定期核对流程会处理到期和额度耗尽，即使管理员没有发起变更。
  “确认”仅指面板读回确认。真实节点访问、长连接和订阅撤销仍须由 B/D 单独验收。

## 职责归属与待定事项

<a id="ownership-and-open-decisions"></a>

A 负责 `service_panel_state.py`、`user_service_access.py`、`service_change_sync.py`、
用量与周期核对，以及迁移 `0113`。B 使用 `0114`，并通过 T 协调共用模型与注册项。
A 的实现分包不包含订阅交付、IP 释放或中文本地化。

用户于 2026-10-23 确认的 A3 决策：修改模板额度时，同时修改所有由该模板开通且未归档服务的
当前与未来周期额度。已有用量不清零，其他条款快照不变。
计数异常恢复必须依据准确、可审计的核对结果，不接受估算；
不默认免除历史用量，不隐含重置计数或更换身份。

另见[独立服务说明](independent-services.md)、[需求](../requirements.md)
和[实施计划](../implementation-plan.md#10-剩余工作分包与协作)。

## A1 切点能力证据与已确定的取舍（2026-10-23）

<a id="a1-cutover-capability-evidence-and-resolved-tradeoff-2026-10-23"></a>

当前适配器通过 `panel_api_users.PanelApiUsersMixin.get_user_by_uuid_lookup`
读取累计计数，再通过单独的 `PATCH /users`（`update_user_details_on_panel`）写入。
写入契约不提供计数前置条件、周期标识、原子化的采样与限额设置，
也不提供应用数据库提交确认。`POST /users/{id}/actions/enable` 与 `disable`
同样是独立操作。这些是源码与接口契约证据，不是对未测试节点行为的结论。

假设旧累计计数为 100，新月度额度为 1000，PATCH 成功写入的上限为 1100。
如果读回计数已到 120，而所有确认前的流量都必须归入旧周期，
则为保证完整的新额度，上限需要改为 1120。下一次确认若计数已到 130，上限又需要改为 1130。
响应丢失或本地提交失败时也会出现同样的问题。
等待两次计数相等可能永远无法完成；每次重试重新选基线，则可能在一个周期尚未提交前反复额外补量。

现有 API 无法同时保证以下全部条件：连接不中断、直至本地确认前的每个字节都计入旧周期、
切换在有限时间内完成，以及崩溃重试后只发放一次完整的新额度。
实现不得悄悄放宽其中任何一项，也不得自行暂停正常流量。

解释这一取舍后，用户明确接受了持久化检查点方案。
该方案取代 A1 之前以确认时刻划分用量的表述；对应需求、产品设计和实施计划由 T 更新。
`tests/unit/test_service_entitlements.py` 覆盖持续流量、PATCH 响应丢失及本地确认提交失败。
真实节点的计数延迟与执行效果仍未验证。

## B 接入细节

<a id="b-integration-details"></a>

`service_ready_for_delivery(service, connection, resource, banned=..., now=...)`
只检查本地资格，不改变连接状态。它要求身份已绑定且处于待交付或就绪状态、
已有确认的用量观测、没有用量或准备错误、没有待处理的权益变更，
并且资源与服务条款有效。共用同步入口虽返回布尔值，
B 仍必须同时要求 `sync_pending == False` 且就绪判断通过，才能将待交付改为就绪：
一个身份可能已被安全停用，但其他条款仍待修复。

A 对 `service_provisioning.py` 的改动仅限于导入并调用 `panel_traffic_limit`，
以及向 `matches_service_terms` 传入 `connection=connection`。
准备与交付行为仍由 B 负责。迁移 0113 也包含 A3 的额度变更日志和原始计数恢复字段；
0114 仍由 B 使用。

### 已取消服务的核对与终止结算

<a id="cancelled-service-reconciliation-and-terminal-settlement"></a>

已取消但仍保留身份的服务，可以进行准确用量核对；
其归属、面板停用状态和精确计数检查与暂停服务相同。
核对保留 `cancelled` 状态、原身份及全部历史用量；
暂停、恢复和续期操作仍被拒绝。已完成身份撤销的记录不可编辑。
共用权益同步器对已取消服务只确认访问限制，
不会改写额度或到期时间，也不会确认待处理的月度切换。

B 可用以下共用入口处理因周期待确认而被阻塞的撤销：

```python
async def settle_cancelled_service_period(
    session: AsyncSession,
    service: UserService,
    connection: ServiceConnection,
    remote: dict[str, Any],
    *,
    actor_id: int,
    now: datetime | None = None,
) -> bool: ...
```

该函数位于 `bot.services.service_period_sync`。
调用方持有账号行锁，并提供已绑定身份的最新读回数据，
确认其状态为 `DISABLED`、`LIMITED` 或 `EXPIRED`。
`actor_id` 使用 B 已持久化的撤销订单中记录的发起管理员。
函数拒绝未解决的用量错误、身份归属不匹配、无效计数、计数重置或回退。
必须先完成准确的异常核对，不引入估算或免除缺失历史用量的规则。
该函数不调用面板。

存在待处理切点时，在同一事务中完成以下操作：

- 原 `ServiceUsagePeriod` 保持不变，保留旧用量、旧额度、固定切点，
  并保持 **`confirmed_at` 为空**。
- 将页面展示的切点后用量设为已接受的累计总量减去固定切点，
  使用原待切换周期的下一周期日期。目标状态、额度、到期时间、原始条款及身份不变。
- 新增一条不可变的 `ServiceOrder(kind="settle_usage")`：
  快照记录旧周期日期与用量、下一周期日期、`cutover_bytes`、
  `usage_total_bytes`、`usage_raw_bytes`、`usage_lifetime_offset`、
  结算后的 `used_bytes`、已绑定面板 UUID 与状态、观测时间，以及
  `allowance_confirmed=false`。请求键为
  `settle:<service_id>:<old_cycle_started_at ISO timestamp>`。
- 清除 `connection.cycle_cutover_bytes`，使已取消服务的现有 API 字段
  `cycle_pending` 变为 false。不清除 B 的撤销重试意图，
  不将身份标记为已撤销，也不释放出口资源。

返回 True 表示所提供的观测**已在当前事务中被接受**，
不表示撤销或节点执行已完成。该函数只刷新数据库会话，不提交事务。
B 必须先提交结算，再重新获取账号锁、重新读取同一个停用身份，
并继续检查归属与取消状态。此后接受的任何新观测，也必须在 DELETE 前提交。
没有待处理切点时，该函数只接纳新的用量观测，不创建第二条结算订单。
事务回滚会保留原待处理检查点和用量。
在账号锁内重复调用，不会再次授予额度，也不会重复生成审计记录。

清除待处理标记**不会**冻结最终用量。
B 重新加锁并再次读取同一停用身份后，必须在 DELETE 前使用
`record_service_usage` 或本函数接纳并提交新增字节。
对同一样本先后调用二者不会重复累计：首次结算后，
累计总量和服务已用量都按同一个原始计数增量增加，保持
`used_bytes = usage_total_bytes - original_cutover_bytes`。
例如切点为 900，首次观测为 1200 时记录用量 300；
后续观测为 1225 时记录用量 325，重复读取 1225 仍为 325。
原审计记录保留其当时的 1200 字节观测，不能据此证明之后再无流量。
计数异常仍会阻止删除，直至完成准确核对；任何重试都不会确认新额度。
对应回归测试为
`test_terminal_retries_count_late_bytes_once_and_block_late_counter_anomalies`。
这次定向补充检查通过了 18 项测试、5 项子测试，以及相关文件的 Ruff/mypy 和文档一致性检查。
运行逻辑没有变化，因此这次测试与契约澄清未重复执行全量测试、构建或浏览器检查。

无需新增数据模型或 API 字段，也无需迁移 0115。不得修改 0113 或 0114。

交给 B 的界面接入约定：
`lib/admin/serviceChanges.ts` 中的 `serviceChangeActions(service)`，
对于已取消、身份未撤销且存在 `panel_usage_reset` 或 `panel_usage_regressed` 的服务，
仅返回 `reconcile_usage`；其他已取消服务不返回操作。
用返回结果非空作为展示**管理**按钮的条件，且与现有**撤销**按钮条件分开。
弹窗对已取消服务默认选择准确核对。
共用历史解析器接受已取消服务的核对记录与 `settle_usage`；
历史弹窗解释切点后用量和累计用量，并明确说明未确认额度，不能展示成新额度已发放。
最终已撤销记录必须使用持久化后已清除的检查点，不能伪造周期确认。
合并后的桌面与手机界面由 B/C 验证。

交给 C 的本地化清单（已提供英文与俄文）：
修改 `admin_services_usage_reconcile`、`admin_services_reconcile_hint`、
`admin_services_usage_reconciliation_pause_required`；
新增 `admin_services_settle_usage`、`admin_services_terminal_usage_hint`。

后续回归覆盖：取消后计数重置或回退、停用状态核实、准确修正但不重新启用、
禁止暂停/恢复/续期、终止结算回滚与重试、旧周期证据不变、
最终界面的 `cycle_pending`，以及身份归属、计数和周期无效时的保护。
已编写的 PostgreSQL 测试
`test_parallel_terminal_settlement_writes_one_audit_without_confirming_allowance`
检查八个串行化重试只生成一条不可变终止结算记录；
运行留给主窗口的隔离集成环境。该次检查期间浏览器与构建时段仍分配给 B，
本补丁未据此宣称合并界面已验证。
该次后续全量后端检查通过 **5,593 项测试和 636 项子测试**，**跳过 48 项**。
前端单元测试通过 **203 个文件中的 1,499 项测试**；
完整 mypy、Ruff 检查与格式检查、前端静态检查、架构检查和文档一致性检查均通过。
该次后续检查未运行前端/文档构建、浏览器检查及新增 PostgreSQL 并发测试，
因为集成浏览器、构建和数据库时段由 B 或主窗口占用。

## 本地验证与待验收事项（2026-10-23）

<a id="local-validation-and-remaining-acceptance-2026-10-23"></a>

实现检查点：`1476ddb1`。验证使用 A 的隔离工作区、本地 SQLite 与单元测试夹具、
文档演示浏览器运行环境，没有修改生产节点、共享 PostgreSQL 数据库或真实面板。

- 后端全量测试：**5,587 项通过、45 项跳过、631 项子测试通过**。
  完整 mypy 检查通过，覆盖 1,340 个文件；Ruff 检查、格式检查及架构门禁均通过。
- 随后补充的两项权益回归覆盖月度切换时的暂停、封禁、到期限制，
  以及启用过程中观测到额度耗尽的情况。该次最终权益模块检查为
  **9 项测试、3 项子测试通过**，对应 Ruff 和 mypy 检查通过。
- 前端静态检查、生产构建及单元测试通过：**203 个文件中的 1,492 项测试**。
  最终模拟夹具也通过 TypeScript、ESLint 和 Prettier 检查。
- 完整浏览器回归：桌面与手机尺寸下 **253 项通过**。
  六项计量场景覆盖额度编辑验证、准确核对历史及周期待确认展示；
  截图包含弹窗与展开的操作菜单。
- 文档侧栏、API 同步检查、文档构建、锁文件和开发种子数据检查通过。
  命令见[贡献规范](../../CONTRIBUTING.md#1-гейты-качества--выбирай-по-зоне-изменений-перед-пушем)。

在仓库根目录复现定向回归：

```sh
python -m pytest -q tests/unit/test_service_entitlements.py tests/unit/test_service_adjustments.py
npm --prefix frontend run test:e2e -- e2e/service-metering.spec.ts
```

在 macOS 上，运行完整后端测试中的安装器证书测试时，
应在 `PATH` 中将 Homebrew OpenSSL 放在系统 LibreSSL 之前。
浏览器测试通常会重新构建演示环境；
只有已用当前源码完成构建时，才能使用 `PLAYWRIGHT_SKIP_DEMO_BUILD=1`。

`tests/integration/test_user_services_postgres.py` 中新增的 PostgreSQL 测试在该次检查中
**尚未运行**，仍需要安排可丢弃的测试数据库。
这些测试覆盖迁移 0113 的幂等性、模板额度修改与开通并发，
以及计数持续增长时的八个并发月度重试。
测试使用 `CORE_PERFORMANCE_TEST_DATABASE_URL` 和隔离的临时数据库模式；
不得指向生产数据库，也不得未经协调就在共享开发环境中运行。
真实节点的限制执行、计数延迟、长连接和订阅撤销仍需 B/D 验收。
崩溃与提交失败的重试测试，不能证明恢复较旧的整库备份后仍然安全；
该场景属于 E 的恢复流程，并且需要独立的用量证据。

### 交给 C 的本地化清单

<a id="localization-handoff-to-c"></a>

英文与俄文基础条目已具备。中文本地化须覆盖以下 16 个新增或修改的键：

```text
admin_services_snapshot_hint
admin_services_usage_reconcile
admin_services_quota_reason
admin_services_quota_scope_hint
admin_services_quota_change_reason_required
admin_services_reconcile_usage
admin_services_reconcile_hint
admin_services_last_total_bytes
admin_services_verified_total_bytes
admin_services_expected_raw_bytes
admin_services_reconcile_evidence
admin_services_usage_reconciliation_changed
admin_services_usage_reconciliation_pause_required
admin_services_usage_reconciliation_unavailable
admin_services_cycle_pending
wa_services_cycle_pending
```
