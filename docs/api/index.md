# API 与集成

<a id="api-и-интеграции"></a>

本页汇总网站、运营后台、域事件和插件的技术契约。独立服务的一期数据模型与接口状态另见[独立服务说明](../development/independent-services.md)。

## 阅读入口

<a id="быстрый-старт"></a>

- [交互式 API 规范](/api/reference/)展示当前 OpenAPI 定义，读取发布的 [`/openapi.json`](/openapi.json)。
- [HTTP 契约](../architecture/http-api.md)说明响应封装、鉴权、分页、非 JSON 路由和类型化路由规则。
- [域事件](../architecture/events.md)列出事件名、载荷模型和 Core 反应。
- [插件 API](../development/plugins.md)与[插件契约](../development/plugin-contract.md)说明扩展机制。

## 权威来源

<a id="источник-правды"></a>

机器可读的 HTTP 契约存放在 `docs/openapi.json`，网站发布为 [`/openapi.json`](/openapi.json)。该文件由运行中的 `aiohttp` 路由生成，并由契约测试检查。不要手工编辑生成文件。

修改 HTTP 契约后运行生成器：

```bash
PYTHONPATH=backend python -m bot.app.web.openapi
npm --prefix frontend run generate:api-types
```

Swagger UI 只提供浏览入口。后端路由契约、生成的 OpenAPI 文件和防漂移测试共同决定实际协议。
