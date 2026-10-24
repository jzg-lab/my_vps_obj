<a id="миграции-с-других-ботов"></a>

# 从其他机器人迁移

本节保留迁移到 **Minishop 旧订阅模型**的兼容能力，供来源清点、历史核对和单独授权的迁移使用。当前二开项目从[隔离源码流程](../development/project-local.md)启动，一期人工开通多份独立服务，不因存在导入器而启用旧支付、余额或试用流程。

`backend/scripts/legacy_import/remnashop_sales.py` 和 `bedolaga.py` 的订阅导入目标是 `Subscription`／`subscriptions`，不是本项目的独立服务。导入旧订阅、恢复数据库或升级结构，都不等于已完成独立服务权益、连接身份和资源映射；映射规则需先明确，不能自行推断。

| 来源 | 支持范围 | 文档 |
| --- | --- | --- |
| [remnawave-tg-shop](https://github.com/kavore/remnawave-tg-shop/) | 兼容旧库的逻辑恢复与结构升级，文件及外部配置另核对 | [操作指南](remnawave-tg-shop.md) |
| [Remnashop](https://github.com/snoups/remnashop/) | 自动导入用户、订阅、付款、邀请、激活码和支持的支付设置 | [操作指南](remnashop.md) |
| [Bedolaga](https://docs.bedolagam.ru/) | 数据清点及账号、订阅、财务、礼品、运营数据的幂等导入 | [操作指南](bedolaga.md) |

## 使用顺序与边界

1. 明确来源版本、目标模型、数据范围及映射规则，分别盘点账号、旧订阅、财务历史、文件和外部面板；未知映射保持待定。
2. 在隔离副本准备目标结构与备份，先清点／dry-run，检查冲突、未映射身份、金额和数量；生产库不能用作随意重置的目标。
3. 正式迁移及切换须单独确认，备份与回退可用后才应用。上游安装器可能重启、改配置并发送通知，不是纯读取工具，也不能替换本项目源码。
4. 核对实际服务与远端权限，再安排切换。迁移成功不代表数据面连接、固定独享出口或客户端 GUI 已验收。

当前状态只查[本轮本地最终验收](../implementation-plan.md#本轮本地最终验收)；[上游参考](../upstream/index.md)和[历史索引](../archive/index.md)不提供新的生产迁移授权。
