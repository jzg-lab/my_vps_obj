<a id="api-рекламы-и-примеры"></a>

# 广告 API 与示例

本页是[广告兼容参考](./index.md)，记录保留接口的参数、权限与示例。完整结构和认证要求见 [HTTP API](../../architecture/http-api.md)及 [OpenAPI 入口](../../api/index.md)；本项目退役的上游商业接口另受[运行时边界](../../upstream/index.md#运行时边界)约束。

公开 `POST /api/advertising/capture` 接受 `code`、`utm` 对象中五个许可 UTM 字段，以及可选 `event_id`。用户 ID 来自已验证会话，不能通过请求体指定。响应只包含可公开的链接与优惠上下文，访问 cookie 有效期 30 天。

管理操作位于 `/api/admin/ads`：列表参数 `page`、`page_size`、`search`、`source`、`status`；详情 `/{id}/detail`；链接、优惠版本、费用、归档、导入。`start` 包含、`end` 不包含，时间必须带时区。`period_mode=events` 选择事件，`cohort` 选择获客群组。`/{id}/export?kind=contacts|purchases|report|matches` 导出 CSV。金额最小单位以字符串传递，例如 `"123456789"` 表示 0.123456789 TON。

导入有独立预览、确认、撤销和候选接口。预览接受带 `csv`、`mapping`、`account`、`timezone`、`granularity`、`currency`、`delimiter` 的 JSON，也接受 `text/csv` 正文加查询参数。要求管理员角色，最多 1 MiB、5000 行。预览显示前 20 行规范化结果，确认应用整个已验证批次，重复确认幂等。

以下为**虚构示例**，不代表 Telegram Ads 承诺的导出格式：

```csv
start,end,ad,views,clicks,starts,cost,currency
2026-09-01T00:00:00Z,2026-09-02T00:00:00Z,qa-example,1000,50,20,4500,RUB
```

映射为 `start→start`、`end→end`、`advertisement→ad`、`impressions→views`、`clicks→clicks`、`starts→starts`、`cost→cost`、`currency→currency`。区间和累计值必须有结束时间。累计值代表一个完整区间，重叠累计不能相加。修正完全相同区间需明确允许替换。同一时段的日粒度与分钟粒度不能同时求和；夏令时切换需明确检查。

事件模式中，每行代表一次启动，不是启动计数。按时间匹配需指定机器人和窗口，即使唯一匹配也不证明身份、不发放权限。存在多个外部或本地事件时显示竞争候选。见[导入说明](telegram-ads-import.md)。
