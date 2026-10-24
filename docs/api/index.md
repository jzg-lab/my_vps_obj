# API 与集成

<a id="api-и-интеграции"></a>

本页汇总同一项目的网站、管理台、事件和插件契约。首次接手先读[接手指南](../handoff.md)，
修改协议遵循[贡献指南](../../CONTRIBUTING.md)。

本项目业务对象是一账号下的多份独立服务，见[独立服务模型](../development/independent-services.md)；
管理接口按[统一管理台指南](../admin-console-guide.md)服务客户与节点两条主线。
规范同时保留上游单订阅、支付及插件契约，接口出现在 OpenAPI 中不代表独立服务模式会开放该业务。
实际启用条件以路由和运行配置为准，验收证据统一见
[实施计划 §14：本轮本地最终验收](../implementation-plan.md#本轮本地最终验收)。

## 阅读入口

<a id="быстрый-старт"></a>

- [交互式 API 规范](/api/reference/)展示当前 OpenAPI 定义，读取发布的 [`/openapi.json`](/openapi.json)。
- [HTTP 契约](../architecture/http-api.md)说明响应封装、鉴权、分页、非 JSON 路由和类型化路由规则。
- [域事件](../architecture/events.md)列出事件名、载荷模型和 Core 反应。
- [插件 API](../development/plugins.md)与[插件契约](../development/plugin-contract.md)说明扩展机制。
- [订阅网关](../architecture/subscription-gateway.md)说明上游 `/s/{token}` 凭据和转发边界，与独立服务交付分别维护。
- [Remnawave API 兼容性目录](../architecture/remnawave-api-compatibility.md)说明对外调用及版本契约。

## 权威来源

<a id="источник-правды"></a>

机器可读的 HTTP 契约存放在 `docs/openapi.json`，网站发布为 [`/openapi.json`](/openapi.json)。生成器枚举应用注册的 `aiohttp` 路由并读取类型化契约，不需要访问生产服务；契约测试检查漂移。不要手工编辑生成文件。

修改 HTTP 契约后运行生成器：

```bash
PYTHONPATH=backend python -m bot.app.web.openapi
npm --prefix frontend run generate:api-types
```

Swagger UI 只提供浏览入口。后端路由契约、生成的 OpenAPI 文件和防漂移测试共同决定实际协议。
