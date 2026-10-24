<a id="статус-серверов"></a>

# 服务器状态与节点指标

<a id="服务器状态"></a>

客户状态页与管理员节点诊断是两个入口，不能互相代替。

| 入口 | 数据含义 |
| --- | --- |
| 客户网站“服务器状态” | 根据站点配置展示外部状态页或 Uptime Kuma／xray-checker 的公开结果，不决定客户某份服务的权益。 |
| 管理后台“运行总览”与“节点” | 通过 `/admin/console-overview`、`/admin/nodes` 查看已纳管 Node、资源关系、潜在关联服务和去重客户。 |
| 节点页“待接入节点” | 只显示人工登记的名称、地址、备注；没有在线状态、流量或客户影响指标。 |

## 管理员如何读指标

- 先核对来源、读取时间、覆盖范围和失败／过期提示。成功读取时间不等于实际采样时间，未知或无样本不补零。
- “今日／7 日／30 日”节点流量以 UTC 日历日为窗口，按 Node UUID 与节点库存合并；它不同于服务按北京时间计算的月度额度。没有流量样本也不能据此删除库存中的节点。
- 面板在线身份数不是去重客户数或设备数；服务与节点的授权关联表示潜在影响，不证明实时连接或实际故障影响。
- Node 系统内存、负载及网卡 RX/TX 属于该 Node 所见的机器与网卡。系统负载不是 CPU 使用率，网卡量包含其他流量及协议开销，不是单份服务的上传＋下载业务计费量。
- 管理连接在线不证明代理通路可用。未采集的 RTT／丢包和上游未提供的样本时间保持未知，不能用 API 请求耗时代替。

排障步骤见[管理员操作手册](../user-guide/admin-workflows.md#5-从节点查看影响范围)，指标定义见[统一管理台指南](../admin-console-guide.md#5-指标定义与数据可信度)。版本、实际证据及保留边界只查[实施计划 §14：本轮本地最终验收](../implementation-plan.md#本轮本地最终验收)。

## 客户状态页配置

客户状态页默认关闭，每次使用一个来源：外部网页（`url`）、Uptime Kuma 或 xray-checker。内置适配器的数据直接显示在网页应用内；选择 `url` 时跳转到指定页面。以下通用配置不配置管理台 Node 指标，也不探测待接入记录。

```env
SERVER_STATUS_ENABLED=False
SERVER_STATUS_SHOW_ON_HOME=False
SERVER_STATUS_PROVIDER=url
SERVER_STATUS_URL=
SERVER_STATUS_KUMA_URL=
SERVER_STATUS_XRAY_CHECKER_URL=
SERVER_STATUS_CACHE_TTL_SECONDS=30
SERVER_STATUS_STALE_TTL_SECONDS=300
SERVER_STATUS_TIMEOUT_SECONDS=5
```

设置 `SERVER_STATUS_ENABLED=True` 并选择以下一种来源。首页状态卡片需另行设置 `SERVER_STATUS_SHOW_ON_HOME=True`。

<a id="источники"></a>

## 状态来源

<a id="внешняя-страница"></a>

### 外部网页

```env
SERVER_STATUS_PROVIDER=url
SERVER_STATUS_URL=https://status.example.com
```

此模式下，Minishop 不读取或缓存服务器状态。

### Uptime Kuma

在 Uptime Kuma 创建并发布状态页，填写完整公开 URL：

```env
SERVER_STATUS_PROVIDER=uptime-kuma
SERVER_STATUS_KUMA_URL=https://status.example.com/status/services
```

允许带反向代理前缀，例如 `https://status.example.com/kuma/status/services`。Minishop 会提取前缀，通过相同路径访问 Uptime Kuma 的公开接口。地址必须使用 HTTP(S)，路径包含 `/status/<slug>`，且不能包含查询参数、片段或登录凭据。不需要 Uptime Kuma 管理员账号或 API 令牌。

旧配置中单独填写 slug 的方式仍保留兼容，但已弃用，后台不再显示或保存该字段。下次修改时，请改用完整状态页 URL。

### xray-checker

```env
SERVER_STATUS_PROVIDER=xray-checker
SERVER_STATUS_XRAY_CHECKER_URL=https://checker.example.com
```

填写 backend 容器能够访问的 xray-checker 基础 URL。同一 Docker 网络内的实例可在后台填写为 `http://remnawave-xray-checker:2112`。内部 Uptime Kuma 则需完整状态页地址，例如 `http://uptime-kuma:3001/status/services`。

管理员配置的主机和端口会获得访问许可，修改或清空 URL 后会同步更新许可。后台修改立即生效，无需重启整个服务栈。

<a id="кэш-и-диагностика"></a>

## 缓存与排障

内置适配器的成功响应缓存 `SERVER_STATUS_CACHE_TTL_SECONDS` 秒。请求出错或超时时，最近一次成功响应可以作为旧数据继续显示，最长保留 `SERVER_STATUS_STALE_TTL_SECONDS` 秒。没有缓存时，网页应用会显示错误，不猜测服务器状态。

修改 `.env` 后，重建 backend 容器并检查日志：

```bash
docker compose up -d --force-recreate backend
docker compose logs --tail=100 backend
```

Uptime Kuma 无法加载时，检查发布 URL 是否符合 `https://example.com/status/slug` 或 `https://example.com/proxy-prefix/status/slug`，并检查 DNS、TLS 和反向代理。

内部监控服务必须能从 backend 按配置的主机名和端口访问。禁止使用云实例元数据接口或在 URL 中包含密钥。后端会核对实际 DNS 地址及重定向目标；其他内部主机和端口不会自动获得访问许可。日志出现 `error_type=ValueError`、`status=-` 时，请按[出站连接规则](../configuration/security.md#其他安全要求)检查 URL、DNS 结果及重定向地址。

检查名称和状态会展示给用户，请勿在其中填写内部 IP 或运维机密。

完整参考：[环境变量](../configuration/env-vars.md#服务器状态)。
