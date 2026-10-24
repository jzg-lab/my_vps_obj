# 上游兼容与可选扩展

这里汇总同一项目中保留的 Minishop 能力，供维护兼容代码、查询历史数据和评估扩展时使用。文件保留原路径和锚点，不另建一套产品需求或实施进度；更新方式遵循[文档维护规范](../documentation.md)。

接手项目先读[接手说明](../handoff.md)与[文档总目录](../index.md)。一期沿客户与节点两条主线管理，一个账号持有多份独立服务，由管理员人工开通，不接在线支付。规则以[需求基线](../requirements.md)、[统一管理台实施指南](../admin-console-guide.md)和[产品设计](../product-design.md)为准；进度、证据及环境边界只查实施计划 §14 的[本轮本地最终验收](../implementation-plan.md#本轮本地最终验收)。旧阶段记录从[历史索引](../archive/index.md)查阅，不作为当前待办。

## 先区分业务模型

| 对象 | 上游单订阅模型 | 本项目独立服务模型 |
| --- | --- | --- |
| 套餐配置 | `TARIFFS_CONFIG_PATH` 指向 JSON，由 `TariffsConfig` 读取；没有目录时保留环境变量兼容。 | 数据库 `ServicePlan` 套餐模板。修改 JSON 目录不会替代此模板。 |
| 已开通权益 | 常规购买、续订、加购与切换围绕账号当前订阅；普通／premium 额度仍属于该模型。 | 每份 `UserService` 有自己的条款、额度、日期、连接身份和资源；同一模板可重复开通。 |
| 开通入口 | 试用、结账、礼品、激活码、邀请奖励等上游流程。 | 管理员选择客户与模板人工开通，操作规则见指南 F01／UC-04。 |
| 计量与续期 | 使用本目录所列上游周期、可结转加购与套餐切换规则。 | 使用[额度与计量契约](../development/entitlement-metering-contract.md)，不能套用上游规则。 |

独立服务模型及接口见[独立服务模型](../development/independent-services.md)，实际订阅与资源映射见[连接与资源交付](../development/service-delivery.md)。数据库能存多条旧订阅、一个套餐包含多个组或普通／premium 两个计量器，均不等于多份独立服务。

## 运行时边界

兼容源码、接口定义和文档保留，不等于相应业务入口向一期用户开放，也不是切换一个 `.env` 开关即可恢复的双模式部署教程。

- [`legacy_business.py`](../../backend/bot/app/web/webapp/legacy_business.py) 拦截旧单订阅、结账、礼品、余额等用户路由及对应管理写操作；通过身份与管理权限检查后返回 `410 legacy_business_retired`。部分管理读取保留，用于历史核查；不能据此推断所有旧界面仍可操作。
- [`web_server.py`](../../backend/bot/app/web/web_server.py) 将注册的旧支付／账号级面板 webhook 接到退役响应；支付页中“旧通知继续核对”等说明描述上游兼容流程，不承诺本项目运行时继续处理旧收款。
- [`main_worker.py`](../../backend/main_worker.py) 的默认任务与队列处理器是后台执行依据；保留旧商业 worker 类或函数不表示已调度它们。不得为恢复旧商业处理而停止独立服务的交付、计量和同步。
- [`independentServices.ts`](../../frontend/src/lib/admin/independentServices.ts) 约束旧导航与设置入口；Telegram 的对应边界见 [`telegram_service_model.py`](../../backend/bot/services/telegram_service_model.py)。隐藏入口不授权删除历史记录或免除已有资金义务。
- 主题、登录、客服、通知、广告记录等需逐项判断，不能一律归为“未启用”。广告采集不等于销售入口开放；配色与品牌设置也不依赖支付功能。

后续若要开放商业流程，须先确认其与独立服务的权益、订单、退款及迁移关系，再按项目规则实施和验收。不要通过恢复旧路由绕过这一边界。

## 单订阅与商业能力

| 参考页 | 保留内容 |
| --- | --- |
| [套餐与订阅](../features/subscriptions.md) | 单订阅生命周期、限额、续订、重签发与按天兼容。 |
| [套餐配置](../features/tariffs.md) | JSON 目录、`TARIFFS_CONFIG_PATH`、period／traffic、premium、HWID、试用和旧推荐规则。 |
| [支付](../features/payments.md) | 渠道标识、webhook、金额核对、循环付款与历史订单处理。 |
| [赠送订阅](../features/gifts.md) | 礼品购买、领取、管理员发放、撤销与退款。 |
| [激活码](../features/promocodes.md) | 固定奖励、折扣、倍数、范围、旧链接及导入兼容。 |
| [用户余额](../features/user-balance.md) | 充值、消费、转换、账本与退款；资金余额不是服务流量余额。 |
| [合作伙伴计划](../features/partner-program.md) | 伙伴归因、佣金、冻结、提现与历史义务。 |

以上商业流程不代表一期开放。日常独立服务管理应使用统一管理台；套餐模板的价格字段也不是在线支付接入证明。

## 广告与来源统计

广告记录属于保留的可选运营能力。购买、收入和转化说明沿用上游订单口径，不能把人工开通记录当作已收款订单。

- [广告概览](../features/advertising/index.md)：页面与阅读入口。
- [术语](../features/advertising/glossary.md)：接触、账号、购买和金额口径。
- [活动、链接与 UTM](../features/advertising/campaigns-links.md)：稳定链接、暂停与归档。
- [登录与付款来源](../features/advertising/attribution-auth.md)：已验证账号关联与公开受众契约。
- [广告链接优惠](../features/advertising/promocodes.md)：激活码绑定与来源快照。
- [导入广告平台指标](../features/advertising/telegram-ads-import.md)：CSV 映射、区间、修正与撤销。
- [广告报表](../features/advertising/reporting.md)：币种、费用、群组与归因限制。
- [广告 API 与示例](../features/advertising/api-examples.md)：接口、权限与虚构数据示例。
- [广告核查与限制](../features/advertising/troubleshooting-limitations.md)：排障、关闭入口与验证边界。

## 主题与公开扩展

| 参考页 | 适用边界 |
| --- | --- |
| [网页主题与外观](../features/webapp-themes.md) | 仍适用的配色、品牌、字体、深浅模式与后台外观基础；旧商店专用令牌按对应页面使用。 |
| [制作与发布自定义主题](../features/theme-packages.md) | 可选主题包、版本、资源、安装与回滚参考；不改变业务权限。 |
| [主题包中的 JavaScript](../features/theme-effects.md) | 单独授权的可选效果；`trusted-dom` 不是安全沙箱。 |
| [minishop PRO](../features/minishop-pro.md) | 单独交付扩展的公开能力及官网；核心不依赖 PRO，不收录其私有代码或契约。 |
| [插件开发](../development/plugins.md) · [插件契约](../development/plugin-contract.md) | 保留的公开扩展接口，不把独立服务二开描述为纯插件方案。 |
| [插件扩展](../development/plugin-extensions.md) · [插件界面组合](../development/plugin-ui-composition.md) | 对应扩展点与界面集成规则，不能绕过本项目权益与权限约束。 |

## 共享基础与维护参考

这些资料同时包含仍适用的基础能力，不因列在本目录就变成历史功能。各页的上游示例与本项目一期入口需分开阅读。

- 界面与账号：[网页应用](../features/web-app.md)、[管理后台参考](../features/admin-panel.md)、[登录方式](../features/login-methods.md)、[不使用 Telegram](../features/telegram-optional.md)。
- 客户支持与运维：[客服](../features/support.md)、[通知](../features/notifications.md)、[服务器状态](../features/server-status.md)、[备份](../features/backups.md)。
- 配置：[环境变量](../configuration/env-vars.md)、[安全](../configuration/security.md)、[遥测](../configuration/telemetry.md)。
- 启动与部署参考：[概览](../getting-started/overview.md)、[环境要求](../getting-started/system-requirements.md)、[启动](../getting-started/setup.md)、[部署](../getting-started/deployment.md)、[配置](../getting-started/configuration.md)。各页分别标明本项目入口和上游示例；本项目操作从[隔离开发环境](../development/project-local.md)开始，不直接重跑上游安装命令。
- 其他机器人迁移：[总览](../migrations/index.md)、[Remnashop](../migrations/remnashop.md)、[Bedolaga](../migrations/bedolaga.md)、[Remnawave TG Shop](../migrations/remnawave-tg-shop.md)。这是保留的兼容能力，迁移须另行核对来源和目标，不能覆盖独立服务权益。
- 排障：[常见问题](../troubleshooting/issues.md)、[日志](../troubleshooting/logs.md)、[维护](../troubleshooting/maintenance.md)。
- 技术契约：[HTTP API](../architecture/http-api.md)、[API 入口](../api/index.md)、[事件目录](../architecture/events.md)、[订阅网关](../architecture/subscription-gateway.md)、[Remnawave API 兼容性](../architecture/remnawave-api-compatibility.md)。协议标识与生成契约保持原义，生成产物遵循[贡献指南](../../CONTRIBUTING.md)。
