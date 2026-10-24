# HTTP API 契约

<!-- 保留翻译前的章节锚点，以兼容既有链接。 -->
<a id="контракты-http-api"></a>

HTTP API 的机器可读事实来源是 `docs/openapi.json`。
文档站将它发布为 [`/openapi.json`](/openapi.json)，并在
[API → 交互式规范](/api/reference/)提供交互式浏览页面。
该文件在核心路由和内置 Web 插件注册完成后，从实际 `aiohttp` 路由器生成。
测试 `tests/contracts/test_openapi_artifact.py` 会将生成物与当前路由器比较；
如果 `docs/openapi.json` 已过时，测试就会失败。

本页说明契约的通用规则；详细模型、路径参数、内容类型及认证方案请查阅 `openapi.json`。
修改协议的流程与质量门禁以[贡献指南](../../CONTRIBUTING.md)为准，接手顺序见[接手指南](../handoff.md)。

本页同时保留上游路由分类和示例，不表示所有旧业务接口在当前项目中可用。
独立服务模式已通过 `legacy_business_middleware` 退役单订阅、支付、试用等旧业务入口；
其中 `/api/subscription-guides` 及其公开分享路径仍返回 `410 legacy_business_retired`，
不能用作独立服务教程的配置来源。当前业务接口与边界见[独立服务说明](../development/independent-services.md)。
接口已注册或出现在 OpenAPI 中，不等于通过了实际运行的中间件和业务权限检查。

## API 范围

<a id="области-api"></a>

- `/api/admin/*`：Web App 内的管理后台 API。所有路由均要求账号具有有效的
  `owner` 或 `admin` 角色及登录会话。只有所有者可通过 `/api/admin/roles` 管理角色。
- `/api/auth/*`：公开登录路由，包括 Telegram Mini Apps `initData`、
  Telegram OAuth、邮箱验证码、邮件快捷登录链接、密码登录和退出登录。
- `/api/admin/console/*`：统一管理台的客户／服务、节点／资源、操作记录和维护入口，
  仍使用上述管理员会话与角色检查，不另建认证体系。
- `/api/services`、`/api/services/{service_id}`、`/api/service-catalog`：当前账号的独立服务和套餐目录。
  订阅凭据按需经 `/api/services/{service_id}/subscription` 读取，教程配置为 `/api/service-guides`。
- 其余 `/api/*` 用户路由包含账号、安全、客服等共享能力；旧支付、单订阅、设备和营销路由
  另受旧业务停用策略限制，不能仅由路径判断可用性。
- `/api/subscription-guides/public/{share_token}`：保留的上游公开教程契约，
  在本项目独立服务模式下返回 `410 legacy_business_retired`。

## JSON 响应格式

<a id="формат-json-ответов"></a>

JSON 路由使用统一的外层封装：

```json
{ "ok": true }
```

成功响应将业务字段与 `ok` 放在同一层，例如：

```json
{
  "ok": true,
  "promo": {
    "id": 1,
    "code": "GIFT",
    "bonus_days": 7
  }
}
```

错误响应采用同样的结构：

```json
{
  "ok": false,
  "error": "invalid_payload",
  "message": "invalid_payload"
}
```

`error` 是供前端和集成测试使用的稳定错误码。
`message` 可以是供人阅读的说明，也可以重复错误码。

## 身份认证与授权

<a id="авторизация"></a>

OpenAPI 生成物描述了四种认证方案：

- `AdminSession`：管理端路由使用的 `rw_webapp_session` Cookie。
- `AdminBearer`：管理端路由使用的同一 Web App 会话的 Bearer 令牌。
- `UserSession`：Mini App 用户端路由使用的 `rw_webapp_session` Cookie。
- `UserBearer`：用户端 Web App 会话的 Bearer 令牌。

Cookie 和 Bearer 令牌由同一套 Web App 会话机制验证。
管理端 API 在验证会话后，还会检查数据库中账号当前的角色。
已验证邮箱的账号无需 Telegram ID 也可以获得权限。

公开的初始化（bootstrap）、本地化（i18n）、认证/登录（auth/login）路由及公开连接说明，
在 OpenAPI 中不设置认证方案。

## 分页

<a id="пагинация"></a>

分页按具体路由契约选择，不能把一种参数套到全部管理接口：

| 形式 | 典型接口 | 约定 |
| --- | --- | --- |
| `page` / `page_size` | 管理台服务、节点列表及部分上游管理列表 | `page` 从 0 开始；每页上限以各自模型为准。 |
| `limit` / `offset` | 独立服务、套餐模板、服务订单与出口审计 | `limit` 为 1～200，默认 100；`offset` 默认 0。 |
| `cursor` / `limit` | `/api/admin/console/operations` | 使用服务端返回的游标续查，不把游标当作页码或偏移。 |

返回 `total` 时，它表示相同过滤条件下的真实总数，不是当前页长度。
参数、上限和返回字段以 OpenAPI 及对应查询模型为准。

## 请求体

<a id="тела-запросов"></a>

新的类型化路由通过 Pydantic 模型描述 JSON 请求体。
处理函数通过 `parse_body(request, Model)` 读取请求；
如果 JSON 格式不正确或数据未通过模型验证，则返回 `400 invalid_payload`。

在逐步重构期间，请求模型继承 `HttpBodyModel`，并忽略额外字段（`extra="ignore"`），
以保持与现有前端的兼容性。验证某个具体业务域后，可以将对应模型收紧为
`extra="forbid"`，但只能逐个调整。

PATCH 路由必须通过 `body.model_fields_set` 区分“未提供字段”和“明确提供 `null`”。

## 非 JSON 路由

<a id="не-json-маршруты"></a>

并非所有 `/api/*` 路由都返回 JSON：

- `/api/admin/payments/export.csv` 返回 `text/csv`；
- 头像（avatar）、标志（logo）、站点图标（favicon）及部分备份路由处理二进制或 multipart 内容；
- 这些路由单独声明 `content_type`，不经过 `parse_body`。

## 缓存

<a id="кэширование"></a>

`/api/` 下的所有响应都会由 `api_no_store_middleware` 中间件
（`bot/app/web/cache_headers.py`）标记为
`Cache-Control: no-store, no-cache, must-revalidate, max-age=0`。
如果没有这个响应头，Telegram Mini App 的 WebView 缓存会在应用关闭后继续保留，
并从缓存返回重复的 GET 请求结果。例如，管理员已经停用的支付服务商按钮，
用户仍可能看到。

路由自行设置的 `Cache-Control`（例如头像的 `private, max-age=3600` 和 ETag）
会保留其缓存策略；`304` 响应不作修改。
如果机器人前面还有 CDN 或其他代理，它们不得缓存 `/api/`，并且必须透传该响应头。

## 契约存放位置

<a id="где-живут-контракты"></a>

HTTP 契约在对应业务域附近通过
`bot.app.web.route_contracts.register_contract(...)` 注册。
OpenAPI 生成器读取统一注册表，因此 `backend/bot/app/web/openapi.py`
不直接导入业务模型。

共用的 Pydantic 基类与契约定义：

- `HttpBodyModel` 和 `HttpResponseModel`：位于 `backend/bot/app/web/http_contracts.py`；
- `RouteContract`、`ok_envelope_for(...)` 和认证方案常量：位于
  `backend/bot/app/web/route_contracts.py`；
- 上游管理端模型：`backend/bot/app/web/admin_api_impl/schemas.py` 及其领域模块；
- 独立服务模型：`backend/bot/app/web/service_schemas.py` 等服务领域模块；
- 统一管理台模型：`backend/bot/app/web/admin_console_*_schemas.py`；
- 新模型放在 Web App 层对应业务域，使用同一基类，不集中堆入兼容门面。

## 生成与检查

<a id="генерация-и-проверки"></a>

修改 HTTP 契约后，更新生成物：

```bash
PYTHONPATH=backend python -m bot.app.web.openapi
npm --prefix frontend run generate:api-types
```

修改事件发布器或事件模型后，更新事件目录：

```bash
PYTHONPATH=backend python -m bot.infra.event_catalog
```

以下是 HTTP／事件改动的定向诊断命令，不替代贡献指南的修改范围矩阵：

```bash
PYTHONPATH=backend python -m pytest tests/contracts/test_openapi_artifact.py tests/contracts/test_contract_docs_accuracy.py -q
python -m ruff check backend tests
python -m ruff format --check backend tests
```

涉及产品契约或共享代码时，按[贡献指南第 1 节](../../CONTRIBUTING.md#1-гейты-качества--выбирай-по-зоне-изменений-перед-пушем)
完成相应门禁；生成物必须运行生成器，不手改。纯说明文档变更使用该节的文档检查矩阵。
