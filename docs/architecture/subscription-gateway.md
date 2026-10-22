# 公开订阅网关

<a id="публичный-шлюз-подписки"></a>

> 本页说明上游账号级订阅网关，供维护兼容代码时参考。本项目独立服务模式已经退役旧订阅入口，包括 `/s/` 和旧公开教程 API；不能通过下述开关绕过退役限制。当前交付以[独立服务交付](../development/service-delivery.md)为准，每份服务单独核验并提供链接，教程使用 `/api/service-guides`。本文不代表公开网关或真实 Node 已完成本项目验收。

上游网关可在商店域名提供连接链接，替代直接的 Remnawave Panel 链接。同一个 `https://app.example.com/s/<token>` 地址在浏览器打开教程，在 VPN 应用中返回订阅配置；用户可导入后通过同一地址更新。

Minishop 从 Remnawave Panel 取得配置，响应格式、HWID 设备限制和 **Response Rules** 仍由面板设置。导入及更新要求商店和面板均可访问。

## 链接如何工作

<a id="как-работает-ссылка"></a>

| 请求 | 响应 |
| --- | --- |
| 在浏览器打开 `/s/<token>` | 连接教程页面。 |
| 在 Telegram 或其他受支持服务预览链接 | 同一个教程页面。 |
| 在 VPN 应用导入或更新 `/s/<token>` | 不带 API JSON 包装的订阅配置。 |
| `/s/<token>?view=page` | 明确选择教程页面。 |
| `/s/<token>?view=subscription` | 明确选择订阅配置。 |
| `/s/<token>/<format>` | 返回 `stash`、`singbox`、`mihomo`、`json`、`v2ray-json` 或 `clash` 格式。 |

没有明确选择时，网关根据 `User-Agent`、`Accept` 等请求头决定响应。配置请求必须带非空 `User-Agent`，不支持 `HEAD`。格式后缀不能与 `?view=page` 同用。

## 配置

<a id="настройка"></a>

在上游后台打开“系统 → 设置 → 连接教程”。先验证配置交付，再切换商店向用户提供的链接。

| 设置 | 默认值 | 用途 |
| --- | --- | --- |
| `SUBSCRIPTION_GATEWAY_ENABLED` | `True` | “通过公开链接提供订阅”允许应用经 `/s/` 导入和更新；关闭后保留教程页面，但停止提供配置。 |
| `SUBSCRIPTION_LINK_MODE` | `panel` | “使用 Minishop 内置订阅链接”将机器人及教程中的链接从 `panel` 改为 `minishop`，要求网关已启用。 |
| `SUBSCRIPTION_MINI_APP_URL` | 未设置 | 用于生成 `/s/` 链接的 Web App 公开基础地址，不从客户端提交的 `Host` 获取。 |
| `SUBSCRIPTION_GATEWAY_REWRITE_PROFILE_PAGE_URL` | `False` | 将面板响应的 `profile-web-page-url` 头改为带 `?view=page` 的 Minishop 教程链接；否则保留面板设置的地址。 |

验证网关后，`.env` 配置示例：

```env
SUBSCRIPTION_MINI_APP_URL=https://app.example.com
SUBSCRIPTION_GATEWAY_ENABLED=True
SUBSCRIPTION_LINK_MODE=minishop
SUBSCRIPTION_GATEWAY_REWRITE_PROFILE_PAGE_URL=False
```

修改 `.env` 后，按[部署说明](../getting-started/deployment.md)重新创建容器。后台已保存设置可能覆盖 `.env`，应检查实际开关状态。

`minishop` 模式不会自动替换已经导入客户端的地址。面板直连链接继续有效；切换商店域名需要用户重新导入收到的 `/s/` 链接。

## 在现有安装上启用

<a id="включение-на-существующей-установке"></a>

更新在网关出现前已提供公开教程的上游安装时：

1. 在向新版 backend 转发请求前应用 `0088_bind_install_share_to_panel_link` 迁移。新增字段可为空，与旧 backend 兼容。
2. 在可访问数据库和面板的受信任运维环境执行检查：

   ```bash
   PYTHONPATH=backend python -m scripts.bind_install_share_tokens
   ```

   检查 `verified` 和 `skipped` 数量。使用同一命令加 `--apply` 保存已核验绑定，将现有活跃令牌绑定到**当前**面板链接。跳过的记录需人工处理，公开请求不会绑定旧令牌。工具无法判断链接过去是否泄露；有疑虑时重新签发访问凭据。
3. 更新 backend 及 frontend 的 Nginx 配置，为 `/s/` 提供独立路由。分离部署时 frontend 传递 `MINISHOP_EDGE_TOKEN`，必须禁止直接访问受保护的 backend 路由，见[前后端分离部署](../getting-started/deployment.md#раздельное-размещение-frontend-и-backend)。
4. 确认公开订阅交付已启用，暂时保留 `SUBSCRIPTION_LINK_MODE=panel`，完成下述检查。旧 `.env` 或后台设置可能覆盖默认 `True`，使网关仍关闭。
5. 检查通过后，在后台或 `.env` 启用 `minishop` 模式。

全新安装不需要迁移旧令牌。

## 切换链接前的检查

<a id="проверка-перед-переключением-ссылок"></a>

使用有效的测试订阅及商店的实际公开地址，检查完整代理链路：

1. 在浏览器打开链接并检查 Telegram 预览，均应显示连接教程。
2. 导入实际使用的 VPN 客户端并再次更新，检查所需格式、HWID 设备计数和面板 Response Rules。
3. 用相同客户端请求头对比面板直连与网关响应，配置内容和允许传递的请求头应与面板一致。
4. 在测试订阅上重新签发访问凭据，旧公开链接应失效，新链接应能导入。
5. 经外部地址验证面板连接故障，客户端应得到 `5xx`，而非状态为 `200` 的代理 HTML 页面。

手动请求配置使用 `GET`，不要使用 `curl -I`：

```bash
curl --fail-with-body -A 'Happ/1.0' \
  'https://app.example.com/s/<token>?view=subscription'
```

将地址和 `<token>` 替换为自己的测试值。链接是订阅访问凭据，不要将其公开到报告、截图或客服消息中。

## 错误与诊断

<a id="ошибки-и-диагностика"></a>

| 状态 | 检查内容 |
| --- | --- |
| `400` | 配置请求需要 `User-Agent`；`view` 只能有一个值 `page` 或 `subscription`，页面请求不能带格式后缀。 |
| `404` | 令牌不存在、已撤销，或不再匹配当前有效订阅及面板链接，应从账号取得新链接。 |
| `429` | 公开教程和订阅共用请求配额已耗尽，按 `Retry-After` 重试。 |
| `502` | 上游连接失败或面板响应无效：重定向、HTML、成功状态下配置为空、配置超过 8 MiB，或全部响应头超过 64 KiB。检查 `PANEL_API_URL` 及 `/api/sub/<shortUuid>` 可达性。 |
| `503` | 网关关闭、访问校验暂不可用、并发上限耗尽，或配置的共享配额 Redis 不可用。 |
| `504` | 面板响应超时，检查 backend 到面板的连接。 |

面板也可能返回自己的错误状态。诊断参考[后端和代理日志](../troubleshooting/logs.md)、[环境变量](../configuration/env-vars.md)及[教程设置](../features/admin-panel.md#инструкции-подключения)。

## 重新签发与撤销访问

<a id="перевыпуск-и-отзыв-доступа"></a>

用户或管理员重新签发时，Minishop 撤销该面板用户的全部本地公开授权，并在请求面板**之前**保存撤销结果。即使面板报错，旧令牌仍保持撤销。已登录账号可请求与当前 `shortUuid` 绑定的新令牌；直接在面板更改 `shortUuid` 也会使旧令牌在下次访问时失效。

公开 JSON API 和配置交付每次请求都检查数据库授权及当前面板用户记录，不再使用过去的 300 秒公开缓存。

## 回退

<a id="откат"></a>

改回 `SUBSCRIPTION_LINK_MODE=panel` 只影响新发出的链接。用户客户端仍可能保存 `/s/` 地址期间，应保留网关。

紧急停止时关闭 `SUBSCRIPTION_GATEWAY_ENABLED`，配置请求将返回 `503`，用户需重新导入面板直连链接。将 backend 回退到不支持网关的版本也会破坏已导入 `/s/` 配置的更新。

## 技术契约

<a id="технический-контракт"></a>

交付服务接收服务器已授权的资源绑定和客户端请求。Remnawave 适配器请求已配置的 `/api/sub/<shortUuid>`，转发内容、状态和安全响应头，不使用通常的 `{"ok": …}` JSON 包装。它不发送管理 Bearer 令牌、不跟随重定向、不转发用户 cookies、不缓存配置，也不接受公开请求指定的上游地址。如果运维为面板保护代理配置了 `PANEL_API_COOKIE`，只使用该配置的 cookie。

响应头名称不区分大小写，包括 `user-agent`。安全响应头中的大型客户端设置不截断；面板全部响应头（含名称和分隔符）上限为 64 KiB，超限返回 `502`，不会返回缺少设置的配置。标准 Nginx 使用 128 KiB 缓冲，为商店额外响应头保留空间；外部代理也必须接受这样的响应。

frontend 之前的**每一层**外部 Nginx 都要增加响应头缓冲。内部 frontend 缓冲不能改变外部代理限制。标准 [Nginx 示例](https://gitlab.com/3252a8/remnawave-minishop/-/blob/dev/deploy/examples/nginx/nginx.conf.template)和[自有 ingress 配置](https://gitlab.com/3252a8/remnawave-minishop/-/blob/dev/deploy/docker/nginx/remnawave-minishop.conf)均为 `location ^~ /s/` 设置：

```nginx
proxy_buffer_size 128k;
proxy_buffers 8 32k;
proxy_busy_buffers_size 128k;
```

执行 `nginx -t` 检查并重新加载配置，然后再次导入。frontend 响应成功而外部出现 `502` 和 `upstream sent too big header`，说明外部代理缓冲不足。应通过公开 HTTPS 入口验证带长 `x-client-settings` 的成功配置及重复更新；短小的 `404` 响应无法验证该限制。由于地址含秘密令牌，`/s/` 必须保持 `access_log off`。

### HWID 与用量统计

<a id="hwid-и-учёт-использования"></a>

网关将 `x-hwid`、`x-device-os`、`x-ver-os`、`x-device-model` 和 `User-Agent` 转发到同一 Panel 用户的公开订阅端点。客户端地址通过 `x-remnawave-real-ip` 传递：删除传入值，替换为根据可信代理链计算的地址。自有反向代理需检查 `TRUSTED_PROXIES`，网关不信任未校验的客户端 IP 头。

对于支持的 Panel 内部 HTTP 端点，适配器自行设置相同可信地址的 `X-Forwarded-For` 及 `X-Forwarded-Proto: https`，满足面板反向代理检查。传入的对应头被移除，订阅请求不附加管理 Bearer 令牌。

Remnawave 必须启用并配置设备限制，客户端也须发送支持的 HWID。网关不会代客户端生成 HWID，并保留面板拒绝状态和 `x-hwid-*` 响应头，详见 [Remnawave 文档](https://docs.rw/features/hwid-device-limit/)。HWID 在导入或更新订阅时登记，不标识每一条 VPN 连接。流量和连接由 Panel 及其节点统计。

### 公开链接保护

<a id="защита-публичной-ссылки"></a>

令牌含 128 个随机位，与用户 ID 无关。HTML、配置和公开 JSON API 共用配额：每个 IP 每分钟 240 次，每个令牌每分钟 60 次。Redis 为多个进程和副本提供共享计数；未配置 Redis 时，各进程独立计数。已配置 Redis 故障时返回 `503`。这些限制不能替代外部代理对大规模负载的防护。

链接是访问秘密。配额和随机令牌可防止猜测，但无法阻止他人使用已经泄露的链接；泄露后必须重新签发。

配置路由不纳入 JSON OpenAPI 契约，因为响应由客户端和面板决定。JSON 路由 `/api/subscription-guides/public/<token>` 保留在上游 OpenAPI 中，保留 `config` 字段，并返回 `schemaVersion: 1` 的 `guide_document`。该文档由已校验的 Remnawave v1 配置构建，包含有序平台标识及类型化按钮目标。具体订阅授权单独解析，配置交付服务不读取教程文档。

网关响应禁止缓存和索引。标准 frontend 不记录 `/s/`、公开教程 JSON API，或 `Referer` 包含这种链接的访问日志。backend 在 URL、访问日志头和错误报告路径属性中隐藏令牌，同时保留诊断状态。标准 Nginx 对两个公开路由也关闭无法隐藏 URL 的错误日志，诊断改用安全的 backend 日志。自有外部代理也需从日志和报告中排除秘密链接。更新不会清理旧日志中的令牌，应限制访问；可能泄露时重新签发链接。
