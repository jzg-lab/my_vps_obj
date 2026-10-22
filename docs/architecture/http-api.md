# HTTP API 契约

<!-- 保留翻译前的章节锚点，以兼容既有链接。 -->
<a id="контракты-http-api"></a>

HTTP API 的机器可读事实来源是 `docs/openapi.json`。
文档站将它发布为 [`/openapi.json`](/openapi.json)，并在
[API → 交互式规范](/api/reference/)提供交互式浏览页面。
该文件在核心路由和内置 Web 插件注册完成后，从实际 `aiohttp` 路由器生成。
测试 `tests/contracts/test_openapi_artifact.py` 会将生成物与当前路由器比较；
如果 `docs/openapi.json` 已过时，测试就会失败。

本页说明契约的通用规则。详细模型、路径参数、内容类型及认证方案请查阅 `openapi.json`。

## API 范围

<a id="области-api"></a>

- `/api/admin/*`：Web App 内的管理后台 API。所有路由均要求账号具有有效的
  `owner` 或 `admin` 角色及登录会话。只有所有者可通过 `/api/admin/roles` 管理角色。
- `/api/auth/*`：公开登录路由，包括 Telegram Mini Apps `initData`、
  Telegram OAuth、邮箱验证码、邮件快捷登录链接、密码登录和退出登录。
- `/api/*` 中不属于 `/admin` 的路由：Mini App 用户端路由，包括个人资料、支付、
  订阅、套餐、设备、支持、优惠码和连接说明。
- `/api/subscription-guides/public/{share_token}`：通过有效订阅的分享令牌访问连接说明的
  公开只读路由。

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

管理端列表路由的页码从零开始：

- `page`：页码，最小值为 `0`；
- `page_size`：每页数量；
- `total`：元素总数。

新的类型化管理端接口按处理函数当前的逻辑限制 `page_size`。
通常上限为 `100`，日志接口为 `200`。
已迁移到类型化契约的路由会在 OpenAPI 中记录这些限制。

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
- 当前管理端模型：位于 `backend/bot/app/web/admin_api_impl/schemas.py`；
- 未来的 Mini App 模型应放在 Web App 层各业务域的模型模块中，并使用相同基类。

## 生成与检查

<a id="генерация-и-проверки"></a>

修改 HTTP 契约后，更新生成物：

```bash
PYTHONPATH=backend python -m bot.app.web.openapi
```

修改事件发布器或事件模型后，更新事件目录：

```bash
PYTHONPATH=backend python -m bot.infra.event_catalog
```

API 契约的最小检查集合：

```bash
PYTHONPATH=backend python -m pytest tests/contracts/test_openapi_artifact.py tests/contracts/test_contract_docs_accuracy.py -q
python -m ruff check backend tests
python -m ruff format --check backend tests
```

阶段交付前，应运行完整的 `pytest -q` 以完成全面检查。
