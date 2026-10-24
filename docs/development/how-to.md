# 贡献者操作指南

<a id="рецепты-для-контрибьюторов"></a>

首次接手从[接手指南](../handoff.md)开始，再完整阅读本仓库[贡献指南](../../CONTRIBUTING.md)。
本文提供保留架构中的具体修改方法，不另立开发规范。本项目通过管理员开通独立服务，
不启用支付；支付服务商章节属于[上游兼容参考](../upstream/index.md)。
独立服务的业务接口见[数据模型与接口](independent-services.md)，运行环境见[项目本地开发](project-local.md)。

涉及客户、服务、节点、资源或后台操作时，先在[统一管理台指南](../admin-console-guide.md)中
标明对应 UC 工作包、F 流程和 UA 验收项，再复用已有生命周期服务。
结果只登记到[实施计划 §14](../implementation-plan.md#本轮本地最终验收)，不在技术页追加进度流水。

下面介绍三类常见修改的具体步骤。每项修改都以同一要求收尾：
**运行质量门禁**（CONTRIBUTING 第 1 节），让契约测试和生成物一致性检查确认各层正确衔接。

本页提供操作步骤，完整参考资料见：

- [docs/architecture.md](../architecture.md)：系统概览。
- [docs/architecture/http-api.md](../architecture/http-api.md)：HTTP 契约参考。
- [docs/architecture/events.md](../architecture/events.md)：生成的事件目录。
- [docs/development/plugins.md](plugins.md)、[plugin-contract.md](plugin-contract.md)：插件 API。
- [本仓库 CONTRIBUTING.md](../../CONTRIBUTING.md)：约定及不可违反的规则；[上游原文](https://gitlab.com/3252a8/remnawave-minishop/-/blob/main/CONTRIBUTING.md)仅供对照。
<!-- GitHub 源链接（未启用）：[CONTRIBUTING.md](https://github.com/3252a8/remnawave-minishop/blob/main/CONTRIBUTING.md) -->

---

## 添加支付服务商

<a id="добавить-платёжного-провайдера"></a>

每个服务商对应 `backend/bot/payment_providers/<name>/` 下的一个包。
包的 `__init__.py` 是**轻量入口**：声明明确的 `__all__`，不重新导出标准库或框架内容；
具体实现放在职责集中的模块里。
一致性测试（`tests/providers/test_provider_conformance.py`）就是检查清单；
以下要求未满足时，它会给出具体失败信息。

1. **创建 `config.py`。** 继承 `ProviderEnvConfig`，定义自己的 `env_prefix`
   （例如 `MYPAY_`）和字段，可按需添加展示模型。
   服务商模块是自身环境变量的唯一事实来源，**无需修改**全局 `Settings`。

2. **创建 `service.py`。** 定义 `Service` 类。使用托管支付链接的服务商继承 `HttpClientMixin`，
   实现 `create_payment(...)`、`try_reuse_pending_payment(...)`、签名，
   以及接收回调时所需的 `webhook_route(self, request)`。
   明确安全边界：未启用返回 `503`，签名错误或 IP 未授权返回 `403`，支付不存在返回 `404`。

3. **连接回调与 Web App 流程。** 如果服务商采用标准的托管链接跳转流程，
   无需手写编排；声明 `LinkPaymentDescriptor`（`shared/link_flow.py`）并委托公共实现：

   ```python
   async def create_webapp_payment(ctx):  # SPEC.create_webapp_payment
       return await run_webapp_payment(_DESCRIPTOR, ctx)


   async def reuse_webapp_payment(ctx, payment):
       return await run_reuse_webapp_payment(_DESCRIPTOR, ctx, payment)


   @router.callback_query(F.data.startswith("pay_mypay:"))
   async def pay_mypay_callback_handler(callback, settings, i18n_data, mypay_service, session):
       await run_callback_payment(_DESCRIPTOR, callback, settings, i18n_data, mypay_service, session)
   ```

   可参考 `severpay`、`lava`、`heleket`。
   如果回调时序、账单语义或创建调用契约确实不同，保留专用流程，
   并在一致性测试的 `LINKFLOW_BESPOKE` 中添加服务商名称及一行说明，写明具体差异；
   不要为个别例外改造公共执行逻辑。

4. **声明 `SPEC`（`PaymentProviderSpec`）。** 包含稳定的 `id`、`provider_key`、
   `pending_status`、Webhook 路径、入口和清单字段。
   **`id`、`provider_key`、Webhook 路径字符串会持久化**，首次确定后不要重命名。

5. **注册服务商。** 在 `backend/bot/payment_providers/registry.py` 的 `PAYMENT_PROVIDER_SPECS` 中注册。

6. **保持 `__init__.py` 为轻量入口。** 只重新导出 `SPEC`（及其变体）、
   `Service` / `Config` / `Presentation` 类、`create_service`、Web App 工厂、
   Webhook 路由、回调处理器和 `router`，并显式声明 `__all__`。
   入口约束检查会拒绝意外泄露的标准库、框架或类型符号。

7. **补充测试。** 将服务商测试放在现有测试旁；
   对 `payment_dal`、`finalize_successful_payment` 等内部符号打补丁时，
   必须作用于**`.service` 子模块**，不能通过包入口操作。
   见 CONTRIBUTING 第 5 节：修改入口的同名符号可能静默失效。

8. **运行门禁。** 执行 `python -m pytest tests/providers -q`。
   一致性测试会提示是否缺少描述符、专用流程的理由、Webhook 配置或入口修正，
   随后运行完整的 `make check`。

---

## 添加领域事件

<a id="добавить-доменное-событие"></a>

事件是在进程内事件总线上发送的扁平字典通知。总线不会抛出异常，也有意不执行验证；
结构差异由类型化模型检查。

1. **添加载荷模型。** 在 `backend/bot/infra/event_payloads.py` 中继承 `EventPayload`
   （其设置为 `extra="forbid"`），声明 `EVENT_NAME` 并为每个字段标注类型。
   时间戳使用 `datetime`，自动序列化为 ISO-8601；允许为空的字段使用 `Optional[...] = None`。
   **载荷只包含基本类型，不能包含 ORM 对象。** 订阅者根据 ID 重新读取完整数据。

2. **在事件来源处发布。** 调用 `await events.emit_model(MyEvent(...))`。
   `emit` 不抛出异常，因此订阅者失败不会破坏调用方流程。

3. **按需订阅。** 订阅者收到的原始签名为 `(event_name: str, payload: dict)`。
   这一契约保持不变，类型化模型只是新增的便利机制。

4. **在同一提交中重新生成目录。** 执行
   `PYTHONPATH=backend python -m bot.infra.event_catalog`，输出至 `docs/architecture/events.md`。
   不要手工编辑生成目录。

5. **运行门禁。** 模型与目录不一致时，`tests/contracts/test_domain_events.py`
   和文档准确性测试会失败。

---

## 添加 HTTP 接口

<a id="добавить-http-эндпоинт"></a>

API 使用手写的 `aiohttp` 路由、类型化请求/响应模型和生成的 OpenAPI 契约。
**项目没有 FastAPI，不要引入。** `{"ok": …}` 响应封装是不可破坏的传输契约。

1. **显式注册路由。** 在 `setup_subscription_webapp_routes`
   （`bot/app/web/webapp/routes.py`）或 `setup_admin_routes`
   （`bot/app/web/admin_api_impl/routes.py`）中注册。
   插件通过 `Plugin.setup_web` 在运行时添加路由。

2. **解析请求体。** 使用 `parse_body_or_400(request, MyRequest)`
   （`bot/app/web/request_parsing.py`）按 `HttpBodyModel` 验证；新接口不使用 `_read_json`。

3. **构造响应。** 使用 `HttpResponseModel` 子类及显式的 `from_orm_*` 类方法，
   该方法**只能读取已经加载的标量属性**，例如 `obj.__dict__.get("field")`。
   **不要启用**自动扫描的 `from_attributes`，它会在会话关闭后触发延迟加载。
   使用 `_ok(...)` / `_error(...)` 封装结果。

4. **注册契约。** 在 `bot/app/web/route_contracts.py` 中登记，使路由纳入 `openapi.json`。
   非 JSON 路由（CSV、二进制、multipart）声明内容类型，而非 JSON 模型。

5. **在同一提交中重新生成两个产物。** 先运行
   `PYTHONPATH=backend python -m bot.app.web.openapi`，生成 `docs/openapi.json`；
   再运行 `npm --prefix frontend run generate:api-types`，
   生成 `frontend/src/lib/api/openapi.generated.ts`。

6. **通过前端类型化客户端调用。** 使用 `lib/webapp/publicApi.ts`，
   将**字面量路径字符串**传给 `api("/api/...")`，并通过 `unwrap(...)` 解包响应。

7. **运行门禁。** `tests/contracts/test_openapi_artifact.py` 及前端生成物一致性检查
   （对生成类型执行 `git diff --exit-code`）会在契约与产物不一致时失败。
