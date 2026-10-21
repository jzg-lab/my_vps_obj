# 独立服务：数据模型与接口

需求依据：[需求基线 v0.9](../requirements.md)、[产品设计 v0.9](../product-design.md)。

当前已实现数据层、API 和管理员套餐/资源/开通页面，不代表节点连接已经交付。旧 `subscriptions` 的字段、支付与节点同步逻辑不作为新服务的额度来源；用户首页替换与账号生命周期接入仍需继续实现。

## 数据关系

```mermaid
erDiagram
    users ||--o{ user_services : owns
    service_plans ||--o{ user_services : opens
    user_services ||--o{ service_orders : records
    user_services ||--|| service_connections : connects
    user_services o|--o| dedicated_exits : reserves
```

- `service_plans`：可编辑模板、版本和启用状态。总流量和月度额度共用条款结构，资源类型与计量规则独立。
- `user_services`：用户实际获得的服务，保存开通条款、独立额度、用量、时间和预期状态。没有“账号只能有一份当前服务”的唯一约束。
- `service_orders`：管理员操作记录，保存操作者、请求幂等键及价格/条款/日期快照。人工开通没有伪造付款记录或付款成功状态。
- `service_connections`：每份服务独立的连接身份；创建服务只预留身份名称，面板 UUID 未创建前为空，状态为 `pending`。不会写入 `users.panel_user_uuid`。
- `dedicated_exits`：实际资源清单。IP 和节点权限组唯一，资源与服务为一对一占用；录入资源不等于通过真实出口核验。

迁移 `0107_user_services` 只追加新表和索引，不改变原有订阅记录。测试在临时 PostgreSQL schema 上重复执行迁移，验证幂等；不会运行到线上节点。

## 接口

所有接口沿用 `{ok: ...}` 响应、现有登录会话与管理员权限。用户查询始终取会话账号，不接受客户端指定他人的账号作为身份。

| 方法与路径 | 用途 |
| --- | --- |
| GET `/api/admin/service-plans` | 分页读取套餐模板 |
| POST `/api/admin/service-plans` | 创建模板 |
| PUT `/api/admin/service-plans/{plan_id}` | 以 `expected_revision` 校验版本后修改模板，只影响后续开通 |
| POST `/api/admin/services` | 管理员为指定账号开通一份服务，携带模板版本与 `idempotency_key` |
| GET `/api/admin/services?user_id=...` | 查看指定账号的多份服务 |
| GET `/api/admin/service-orders?user_id=...` | 查看该账号的开通快照 |
| GET/POST `/api/admin/dedicated-exits` | 查看或登记专用出口资源；登记后未验证 |
| GET `/api/services` | 当前账号的服务列表 |
| GET `/api/services/{service_id}` | 当前账号的某份服务；其他账号的 ID 返回 404 |

列表使用 `limit`（1～200，默认 100）、`offset`（默认 0），返回真实总数 `total`。具体请求类型见生成的 [OpenAPI](../openapi.json)，前端类型由同一文件生成，不手工维护副本。

开通操作在同一数据库事务中锁定用户、模板及指定资源，提交服务、连接身份和订单。相同用户重复提交相同幂等键与相同请求，返回原服务；键相同而条款选择不同返回冲突。客户端必须在超时重试时保留原键，明确执行另一次开通时才生成新键。

## 后台操作入口

- `/admin/service-plans`：创建、编辑套餐。资源类型和流量规则分别选择；管理员填写价格、币种、有效期和流量。流量输入使用明确标注的 GiB（1,073,741,824 字节），保存时转换为整数字节，编辑不会损失原有字节额度。价格以十进制字符串提交。
- `/admin/dedicated-exits`：登记 IP、资源池及对应节点组，查看是否绑定及是否验证。登记不会自动标为“已验证”。
- 用户详情的“Independent services / Независимые услуги”：查看每份服务，选择套餐和空闲专用资源后手动开通。同模板可再次开通；列表不汇总成账号统一余额。
- 开通前显示所选模板的额度、有效期和价格；发送模板版本，遇到并发修改提示刷新。网络或服务器错误导致结果不明时，浏览器会话保存原请求，重新打开弹窗后使用相同幂等键重试；不会自动改成另一套条款。此数据不包含连接凭据。
- 列表显示真实总数并分页；开通选择器读取全部分页，避免第 201 项以后无法选择。模板编辑和资源登记采用已有表单、下拉、对话框及表格组件。

现阶段新增入口与旧单订阅管理入口暂时并存，这是开发中的过渡状态；旧入口不管理新服务。用户首页、旧操作入口的替换和完整中文界面仍待完成，不能按最终产品交付验收。

## 当前约束与后续工作

- 用户封禁后不能新开通，用户接口不返回其可用服务；真正撤销已有连接属于后续节点执行与账号生命周期工作。
- 新服务显示等待交付。当前接口不输出订阅凭据，不将预留的身份名称当作真实连接。
- `used_bytes` 保留实际值，不截断到配置额度；尚未同步时 `last_usage_sync_at` 为空。
- 月度边界函数按北京时间保留原开通锚点，覆盖月底和闰年。周期切换与节点计量核对尚未接入，不能把此函数的测试当成月度套餐实际验收。
- 专用 IP 分配在数据库中防止重复占用，尚需证明实际网络出口的固定和独占条件。
- 账号合并、删除、全服务封禁以及旧单套餐入口的替换尚待接入。新表外键使用 RESTRICT，防止未处理连接或资源就丢弃归属；目前不要用旧删除流程清理新服务账号。

## 验证

```sh
.venv/bin/python -m pytest -q tests/unit/test_user_services.py \
  tests/contracts/test_migration_chain_snapshot.py tests/contracts/test_openapi_artifact.py

# 从本地安全配置设置 CORE_PERFORMANCE_TEST_DATABASE_URL，必须指向隔离开发库。
# 测试创建随机 schema，结束时只删除自己创建的 schema。
.venv/bin/python -m pytest -q tests/integration/test_user_services_postgres.py
```

覆盖：字段验证、模板版本冲突、条款快照、同模板多实例、重试幂等、事务回滚、账号越权、封禁、专用资源竞争和月度边界。PostgreSQL 测试实测行锁竞争；SQLite 测试不用于证明并发安全。

新增前端验证：

```sh
npm --prefix frontend run test -- src/lib/admin/servicePlans.test.ts src/lib/admin/serviceActivation.test.ts
npm --prefix frontend run test:e2e -- independent-services.spec.ts
```

覆盖额度精度、价格与资源字段校验、实际接口冲突提示、开通请求丢失响应后的幂等重试，以及桌面/手机上的模板创建编辑、同账号同模板重复开通、资源登记保留未验证状态。浏览器演示夹具不提供真实网络连接，不代替 PostgreSQL 与本地 HTTP 验证。

本地实际 HTTP 检查已通过：测试管理员下新建总量及月度各一份服务，重放开通请求返回原服务，修改模板后原服务额度/名称和订单价格保持不变，过期模板版本返回 409。记录保存在隔离开发库，名称以 `Local QA` 开头，状态为 pending，未生成节点连接凭据。
