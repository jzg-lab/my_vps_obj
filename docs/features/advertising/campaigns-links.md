<a id="кампании-ссылки-и-utm"></a>

# 活动、链接与 UTM

创建活动时填写清晰名称和唯一旧式启动代码。代码允许 2–64 个拉丁字母、数字、`_`、`-`。`ref_`、`p_`、`promo_`、`plan_`、`gift_`、`admin_`、`ticket_`、`webapp_auth_` 为其他流程保留。

在详情打开“链接”，填写广告名称、落地路径和 UTM，`utm_source` 必填。后端生成与活动关联的短代码 `ad_…`。链接的标准 UTM 与访问实际收到的参数分开保存；相同 UTM 不会自动变成新活动。

| 地址 | 示例 |
| --- | --- |
| 机器人 | `https://t.me/example_bot?start=ad_example` |
| 主 Mini App | `https://t.me/example_bot?startapp=ad_example` |
| 命名 Mini App | `https://t.me/example_bot/my_app?startapp=ad_example` |
| 网页 | `https://shop.example/shop/?campaign=ad_example&utm_source=telegram` |

命名应用需填写 BotFather 中配置的短名称。Telegram 关闭或机器人名称未知时使用网页链接。网页地址由 `PUBLIC_APP_URL` 构造，支持路径前缀、原查询参数和片段。落地路径必须是本地路径，外部地址和 `//host` 会被拒绝。

“暂停”停止记录新广告接触，“归档”保留已有历史。已发布旧代码继续作为别名；与保留命名冲突时，应新建链接并人工核对，不应改写已发布地址。

广告主按已有账号内部 ID 指定，`/my_ads` 只显示分配给该账号的活动。

继续阅读：[登录归因](./attribution-auth.md)、[优惠](./promocodes.md)。
