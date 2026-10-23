# 审计日志插件

最小外部插件示例，用于检查包结构和公开钩子。只注册服务标记、订阅 `user.registered`，并在网页应用作用域发布简单健康路由，不增加业务逻辑。

<a id="установка-в-dev-окружение"></a>

## 安装到开发环境

```bash
pip install -e examples/plugins/audit_logger_plugin
```

安装后，`minishop.plugins` 入口点返回 `minishop_audit_logger` 包中的 `plugin` 对象。

<a id="что-показывает-пример"></a>

## 示例内容

- `Plugin.setup(ctx)`：访问 `PluginContext.services` 并订阅领域事件。
- `events.subscribe(...)`：公开订阅签名 `(event_name, payload: dict)`。
- `Plugin.setup_web(ctx, app, scope=WEB_SCOPE_WEBAPP)`：只在指定网页作用域添加路由。
