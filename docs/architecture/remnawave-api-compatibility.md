# Remnawave API 兼容性

<!-- 由 `PYTHONPATH=backend python -m bot.services.panel_api_catalog` 生成。 -->

本目录由运行时客户端使用的同一类型化注册表生成。
不要手动修改本文件；应更新 `panel_api_contracts.py` 或
`remnawave_support.json`，再运行生成器和契约测试。

## 支持策略

Core 同时认证 2 代 API：当前代与维护代。
认证针对精确版本，已知代的新补丁或次版本在真实 CI 验证前仍标为**未验证**。
移除支持至少提前 90 天且跨 2 个 Core 版本告知，
实际移除只能发生在不兼容的 Core 发布中。

未知未来主版本采用尽力兼容模式：保留既有读写操作，因为主版本变化不一定改变 API。
完成认证前标为未验证，端点与能力回退限制客户端假设。
元数据端点临时不可用时，Core 保持该模式，依据实际标识和端点运行，不缓存错误版本判断。

## 已认证版本

| 状态 | API 代 | 精确版本 | 预设 | 能力 | 覆盖 | 来源 |
| --- | --- | --- | --- | --- | --- | --- |
| 当前 | rw3-numeric-user-id | 3.4.5, 3.4.4, 3.4.3, 3.4.2, 3.4.1, 3.3.2, 3.3.0, 3.2.3, 3.2.1, 3.2.0, 3.1.0, 3.0.0 | 3.4.5 | numeric-user-ids, user-stream, user-stream-filters, targeted-squad-bulk, connections-drop, hwid-user-id-selector, empty-success-body, multi-node-usage, multi-node-top-users, bulk-squad-update, user-tag | fixture, live-read, live-write, upgrade | [发布说明](https://f.docs.rw/t/topic/354/26) |
| 维护 | rw2-uuid-user-id | 2.8.1 | 2.8.1 | multi-node-top-users, bulk-squad-update, user-tag | fixture, live-read, live-write, upgrade | [发布说明](https://f.docs.rw/t/topic/178) |

历史预设可供人工诊断，但不受支持，也不进入认证矩阵：

- `2.8.0` — 用于人工诊断的历史预设，不属于已认证 CI 矩阵。
- `2.7.4` — 用于人工诊断的历史预设，不属于已认证 CI 矩阵。

## 出站 API 操作

2.8.1 的 `{userRef}` 是用户 UUID，3.0.0 起使用十进制数值 ID。
其他 UUID（节点、节点组、主机、订阅）仍为 UUID。

| 操作 | 方法 | 路径模板 | API 代 | 成功状态 | 响应 | 兼容说明 | 覆盖 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `system.metadata` | GET | `/system/metadata` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 稳定的版本探测，失败不视为能力结论。 | unit, live-read |
| `users.stream` | GET | `/users/stream` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 3.x 以游标流为标准并支持查找过滤；2.8 可能返回 UUID 或忽略新过滤器，Core 因此校验结果。 | unit, live-read, upgrade |
| `users.list` | GET | `/users` | rw2-uuid-user-id | 200 | 带 `response` 字段的 JSON 封装 | 流不存在或使用 UUID 时采用旧偏移分页。 | unit, live-read |
| `users.get` | GET | `/users/{userRef}` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 2.8.1 的 {userRef} 为 UUID，3.x 为数值 ID。 | unit, live-read, upgrade |
| `users.lookup.telegram` | GET | `/users/by-telegram-id/{telegramId}` | rw2-uuid-user-id | 200 | 带 `response` 字段的 JSON 封装 | 3.x 改用 `/users/stream?telegramId=...`。 | unit, live-read |
| `users.lookup.username` | GET | `/users/by-username/{username}` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 用户名查找到 3.4.5 保持稳定，3.1 起用户不存在返回 404/A063。 | unit, live-read |
| `users.lookup.email` | GET | `/users/by-email/{email}` | rw2-uuid-user-id | 200 | 带 `response` 字段的 JSON 封装 | 3.x 改用 `/users/stream?email=...`。 | unit, live-read |
| `users.create` | POST | `/users` | rw2-uuid-user-id, rw3-numeric-user-id | 200, 201 | 带 `response` 字段的 JSON 封装 | Core 不发送调用者提供的用户 UUID，3.x 返回数值 ID。 | unit, live-write |
| `users.update` | PATCH | `/users` | rw2-uuid-user-id, rw3-numeric-user-id | 200, 202, 204 | 带 `response` 字段的 JSON 封装；空 2xx 正文视为成功 | 2.8.1 选择字段为 uuid，3.x 为整数 id。 | unit, live-write |
| `users.bulk-update-squads` | POST | `/users/bulk/update-squads` | rw2-uuid-user-id, rw3-numeric-user-id | 200, 202, 204 | 带 `response` 字段的 JSON 封装；空 2xx 正文视为成功 | 按每批 500 用户更新精确节点组状态。2.8.1 传 uuids、返回 affectedRows；3.x 传数值 userIds、返回 204。空目标逐用户 PATCH，因为 3.0.0 返回 A088/500。 | unit, live-write |
| `users.status` | POST | `/users/{userRef}/actions/{enable\|disable}` | rw2-uuid-user-id, rw3-numeric-user-id | 200, 202, 204 | 带 `response` 字段的 JSON 封装；空 2xx 正文视为成功 | 路径标识遵循 UUID／数值 ID 代。 | unit, live-write |
| `users.connections.drop-v2` | POST | `/ip-control/drop-connections` | rw2-uuid-user-id | 200, 202, 204 | 带 `response` 字段的 JSON 封装；空 2xx 正文视为成功 | 2.8 请求通过 userUuids 选择用户。 | unit, live-write |
| `users.connections.drop-v3` | POST | `/connections/drop` | rw3-numeric-user-id | 200, 202, 204 | 带 `response` 字段的 JSON 封装；空 2xx 正文视为成功 | 3.x 请求通过数值 userIds 选择用户。 | unit, live-write |
| `users.delete` | DELETE | `/users/{userRef}` | rw2-uuid-user-id, rw3-numeric-user-id | 200, 202, 204 | 带 `response` 字段的 JSON 封装；空 2xx 正文视为成功 | 实体不存在的 404 视为幂等成功，路由不存在另行处理。 | unit, live-write |
| `users.revoke` | POST | `/users/{userRef}/actions/revoke` | rw2-uuid-user-id, rw3-numeric-user-id | 200, 202, 204 | 带 `response` 字段的 JSON 封装；空 2xx 正文视为成功 | 路径标识遵循 UUID／数值 ID 代。 | unit, live-write |
| `users.reset-traffic` | POST | `/users/{userRef}/actions/reset-traffic` | rw2-uuid-user-id, rw3-numeric-user-id | 200, 202, 204 | 带 `response` 字段的 JSON 封装；空 2xx 正文视为成功 | 路径标识遵循 UUID／数值 ID 代。 | unit, live-write |
| `subscription.config.resolved` | GET | `/subscriptions/subpage-config/{shortUuid}` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 按上游要求，GET 有意在 JSON 正文携带 requestHeaders。 | unit, live-read |
| `subscription-page-config.list` | GET | `/subscription-page-configs` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 全部已认证 API 代保持稳定。 | unit, live-read |
| `subscription-page-config.get` | GET | `/subscription-page-configs/{uuid}` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 全部已认证 API 代保持稳定。 | unit, live-read |
| `external-squads.get` | GET | `/external-squads/{uuid}` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 全部已认证 API 代保持稳定。 | unit, live-read |
| `hwid.devices.get` | GET | `/hwid/devices/{userRef}` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 路径 userRef 在 2.8.1 为 UUID，3.x 为数值 ID。 | unit, live-read |
| `hwid.devices.delete` | POST | `/hwid/devices/delete` | rw2-uuid-user-id, rw3-numeric-user-id | 200, 202, 204 | 带 `response` 字段的 JSON 封装；空 2xx 正文视为成功 | 正文选择器在 2.8.1 为 userUuid，3.x 为 userId。 | unit, live-write |
| `hwid.devices.stats` | GET | `/hwid/devices/stats` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 全部已认证 API 代保持稳定。 | unit, live-read |
| `hwid.devices.top-users` | GET | `/hwid/devices/top-users` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 全部已认证 API 代保持稳定。 | unit, live-read |
| `nodes.restart` | POST | `/nodes/{uuid}/actions/restart` | rw2-uuid-user-id, rw3-numeric-user-id | 200, 202, 204 | 带 `response` 字段的 JSON 封装；空 2xx 正文视为成功 | 3.x 节点标识仍为 UUID。 | unit |
| `nodes.restart-all` | POST | `/nodes/actions/restart-all` | rw2-uuid-user-id, rw3-numeric-user-id | 200, 202, 204 | 带 `response` 字段的 JSON 封装；空 2xx 正文视为成功 | 真实 CI 不执行，因为会中断全部已登记节点。 | unit |
| `nodes.list` | GET | `/nodes` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 全部已认证 API 代保持稳定。 | unit, live-read |
| `nodes.stats` | GET | `/system/stats/nodes` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 全部已认证 API 代保持稳定。 | unit, live-read |
| `system.stats` | GET | `/system/stats` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 全部已认证 API 代保持稳定。 | unit, live-read |
| `system.stats.bandwidth` | GET | `/system/stats/bandwidth` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 全部已认证 API 代保持稳定。 | unit, live-read |
| `bandwidth.nodes` | GET | `/bandwidth-stats/nodes` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 全部已认证 API 代保持稳定。 | unit, live-read |
| `bandwidth.users` | GET | `/bandwidth-stats/users/{userRef}` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 路径 userRef 在 2.8.1 为 UUID，3.x 为数值 ID。 | unit, live-read |
| `bandwidth.node-users` | GET | `/bandwidth-stats/nodes/{nodeUuid}/users` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 全部已认证 API 代保持稳定。 | unit, live-read |
| `bandwidth.nodes-users` | POST | `/bandwidth-stats/nodes/users` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 兼容 2.8.1 的多节点 top-users 聚合；在把缺失用户视为零前，先检测 topUsersLimit 是否饱和。 | unit, live-read |
| `bandwidth.nodes-usage` | POST | `/bandwidth-stats/nodes/usage` | rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 3.x 返回数值用户 ID 和所有请求节点的逐节点总量；用量快照刷新不快于上游聚合周期。 | unit, live-read |
| `internal-squads.list` | GET | `/internal-squads` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 全部已认证 API 代保持稳定。 | unit, live-read |
| `internal-squads.get` | GET | `/internal-squads/{uuid}` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 全部已认证 API 代保持稳定。 | unit, live-read |
| `internal-squads.nodes` | GET | `/internal-squads/{uuid}/{accessible-nodes\|nodes}` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 尝试上游两种路由拼写并校验响应。 | unit, live-read |
| `internal-squads.add-users` | POST | `/internal-squads/{uuid}/bulk-actions/add-many-users` | rw3-numeric-user-id | 200, 202, 204 | 带 `response` 字段的 JSON 封装；空 2xx 正文视为成功 | 3.x 每批 1000 个数值 ID 定向更新；2.8.1 相似 add-users 会作用全体，因此逐目标 PATCH。 | unit, live-write |
| `internal-squads.remove-users` | DELETE | `/internal-squads/{uuid}/bulk-actions/remove-many-users` | rw3-numeric-user-id | 200, 202, 204 | 带 `response` 字段的 JSON 封装；空 2xx 正文视为成功 | 3.x 每批 1000 个数值 ID 定向更新；2.8.1 逐用户 PATCH。 | unit, live-write |
| `hosts.list` | GET | `/hosts` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 全部已认证 API 代保持稳定。 | unit, live-read |
| `nodes.create` | POST | `/nodes` | rw3-numeric-user-id | 201 | 带 `response` 字段的 JSON 封装 | 限定 3.4.5 的资源操作；受理回执不代表实际运行已经验证。 | unit |
| `nodes.enable` | POST | `/nodes/{uuid}/actions/enable` | rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 限定 3.4.5 的资源操作；受理回执不代表实际运行已经验证。 | unit |
| `nodes.disable` | POST | `/nodes/{uuid}/actions/disable` | rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 限定 3.4.5 的资源操作；受理回执不代表实际运行已经验证。 | unit |
| `internal-squads.create` | POST | `/internal-squads` | rw3-numeric-user-id | 201 | 带 `response` 字段的 JSON 封装 | 限定 3.4.5 的资源操作；受理回执不代表实际运行已经验证。 | unit |
| `internal-squads.update` | PATCH | `/internal-squads` | rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 限定 3.4.5 的资源操作；受理回执不代表实际运行已经验证。 | unit |
| `hosts.create` | POST | `/hosts` | rw3-numeric-user-id | 201 | 带 `response` 字段的 JSON 封装 | 限定 3.4.5 的资源操作；受理回执不代表实际运行已经验证。 | unit |
| `hosts.update` | PATCH | `/hosts` | rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 限定 3.4.5 的资源操作；受理回执不代表实际运行已经验证。 | unit |
| `keygen.node` | GET | `/keygen` | rw3-numeric-user-id | 200 | 带 `response` 字段的 JSON 封装 | 限定 3.4.5 的资源操作；受理回执不代表实际运行已经验证。 | unit |

## 入站 webhook

| 事件 | API 代 | 标识处理 | Core 行为 | 覆盖 |
| --- | --- | --- | --- | --- |
| user.expires_in_72_hours / 48_hours / 24_hours | rw2-uuid-user-id, rw3-numeric-user-id | 2.8.1 使用 user.uuid；3.x 将 user.id 规范化为内部 uuid 别名 | 到期提醒及可选自动续费。 | unit |
| user.expiration | rw2-uuid-user-id, rw3-numeric-user-id | user 对象与 meta.expirationHours | 兼容事件映射到到期前后提醒阶段。 | unit |
| user.expired / user.expired_24_hours_ago | rw2-uuid-user-id, rw3-numeric-user-id | 规范化用户标识 | 订阅到期提醒，并抑制过期订阅数据。 | unit |
| torrent_blocker.report | rw2-uuid-user-id, rw3-numeric-user-id | 类型化 torrent-blocker 正文，单独解析用户标识 | 类型化安全通知，拒绝无效或过大正文。 | unit |
| 其他事件（例如 user.modified） | rw2-uuid-user-id, rw3-numeric-user-id | 存在 user 对象时使用规范化标识 | 发布至 Core 与插件事件总线，不用于生命周期通知。 | unit |

## 已认证升级

| 起始 | 目标 | 策略 | 验证 |
| --- | --- | --- | --- |
| 2.8.1 | 3.4.5 | 保留面板数据库 | `tests/qa/test_remnawave_upgrade.py` |

## 兼容规则与特殊情况

- 成功版本探测缓存五分钟，错误不缓存，使启动竞争和临时认证失败可自动恢复。
- 3.x 用户在边界规范化，数值 `id` 在内部也作为十进制字符串 `uuid` 别名提供，
  以保留面板原地升级时的历史数据库列和服务方法名。
- 识别 API 代后，用户请求在本地拒绝另一代标识，避免 3.x 校验错误洪泛，
  也避免把旧 UUID 当成用户已经删除。
- 后台套餐同步在停用订阅前，通过 Telegram、邮箱或确定性用户名重新关联旧 2.8 UUID。
  查找失败或歧义绝不创建重复用户。
- 2.8.1 使用 `/users` 偏移分页和 UUID 查找，3.x 使用游标流及过滤器。记住能力前先校验响应结构。
- A025、A062、A063 和普通用户 404 统一为空查找结果。先处理路由不存在的 404，
  使 2.8 升级 3.x 后无需重启即可切换流过滤器。
- 契约允许的修改操作接受空 202／204；非空但无效的 2xx JSON 仍为协议错误。
- 2.8.1 节点组 `add-users` 作用于全部用户，Core 不用它执行定向请求，而逐 UUID PATCH。
  3.x 使用数值 ID 批量请求。
- 日志使用注册表标签，不使用原路径，避免路径及查询中的用户标识进入日志和指标标签。

## 新 Remnawave 版本检查

1. 查看上游发布和 API 变化，判断 API 代；未来主版本可尽力兼容，但未通过真实环境验证不算认证。
2. 更新 `remnawave_support.json` 精确版本及开发预设，明确区分历史与认证矩阵。
3. 更新受影响操作契约、适配器、webhook 规范化、版本夹具及真实认证任务。
4. 对当前及维护版本运行读写冒烟；跨代时同数据库升级，检查同步后保存的用户标识。
5. 重新生成本目录和公开 API 产物，再运行全部后端及前端检查。
6. 停止某代支持时，完成策略要求的弃用告知，在不兼容 Core 版本才移除，并将预设转为历史。

清单核查日期：`2026-10-09`。
