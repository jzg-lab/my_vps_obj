<a id="список-изменений"></a>

# 更新历史

本项目及所保留的 Remnawave Minishop 上游发布历史。`dev` 包含本项目尚未发布的修改，不能据此判断生产部署状态；其后的版本条目是上游历史。

历史整理自 [GitLab 发布记录](https://gitlab.com/3252a8/remnawave-minishop/-/releases)和 [GitHub 发布记录](https://github.com/3252a8/remnawave-minishop/releases)。发布日期采用 GitLab 原始发布记录的 UTC 时间；GitHub 镜像可能较晚。未正式发布的标签不列入。

<a id="в-разработке--dev"></a>

## 开发中 · dev

下一版本的版本号和发布日期尚未确定。
[上游 dev 对比 v3.8.1](https://gitlab.com/3252a8/remnawave-minishop/-/compare/v3.8.1...dev)仅供上游追溯，不包含本项目工作区修改。

<a id="добавлено"></a>

### 新增

- **项目文档与接手入口。** 仓库 Markdown 按项目规格、日常使用、开发运维、技术参考、上游兼容与历史归档分类，新增接手指南、管理员操作手册和文档维护规则。当前实施与验收保留唯一入口，旧分工和方案调查移入归档；明确本项目源码部署与上游安装器、独立服务与单订阅功能、本地验收与生产发布的区别。新窗口和 agent 直接从根 `AGENTS.md` 接手，无需文档网页。
- **my_vps_obj 开发基础。** 二次开发项目将已确认的需求、产品设计和实施计划与 Minishop 源码共同维护。独立本地 Compose 覆盖配置构建项目镜像，隔离服务名和数据卷，默认禁用支付及对外通知。上游发布流程仅在上游仓库执行。
- **独立服务记录。** 管理员可定义共享节点或专用出口套餐模板，通过鉴权 API 和新后台页面人工开通独立服务。套餐编辑器支持两种资源类型及总量／月度额度；专用出口有资源清单，用户详情分别展示服务。每次开通保存商业条款和价格，重试返回原服务；专用出口独占预留，用户只能读取自己账号的数据。新服务在计量和交付确认前保持待处理。开通表单跨刷新保留结果不明的请求，以便幂等重试。用户首页分别展示各服务的用量、有效期、详情、超额和同步状态；下一步指引区分待开通、待同步、可导入及受限状态，额度耗尽用警示表达，旧用量与剩余额度紧邻最后确认时间。服务求助复用现有客服入口，站内草稿带入服务标识并保留未发送内容；完整标识与长说明可展开查看。脱敏套餐目录说明人工开通方式。本部署隐藏旧结算、充值和营销流程，保留账号与安全设置。账号合并只转移服务归属，不合并权益或替换连接身份。删除账号前必须释放专用出口并撤销连接；脱离账号的服务与开通历史通过后台 API 和分页归档页保留。每份服务可查看原始价格、额度和日期的开通记录，不使用现有模板条款替换；记录价格不代表付款确认。管理员可暂停、恢复或按明确记录的续期条款续期单份服务；续期保留用量与原月度锚点，乐观版本和持久请求键防止重复延长。已保存变更在失败后重试面板同步，界面区分待处理与面板已确认状态；恢复及解封不能绕过未确认变更或启用尚未准备好的服务。原开通请求范围在合并和删除后仍保留。账号封禁／解封先持久化同步任务再访问面板，中断或 worker 重启后可重试，检查所有已知身份；解封保留到期、耗尽和暂停限制。后台用户页区分待处理变更与面板确认状态并支持重试。账号同步跳过已撤销身份并保留历史；网站和 Telegram 删除账号前都要求已绑定服务完成计量撤销，不能绕过异常核对或终态结算。旧订阅／结算写操作、订阅交付及隐式登录奖励返回 HTTP 410；支付和账号级面板 webhook 停用，旧权益 worker 不再启动，排队核心事件转入死信队列，既不发放权益也不丢弃载荷。独立服务后台隐藏旧订阅操作、账号级额度和销售设置，旧筛选与深链接不再展示冲突的服务模型；保留账号生命周期操作，历史付款只读。Telegram 菜单引导用户到网站管理服务，旧权益回调、遗留输入状态和内置支付处理器在正常鉴权后停用；注册、语言及账号操作仍可用，不隐式发放订阅。拒绝预结算，收到的历史付款凭证进入现有队列供死信核对，不授予权益。专用 worker 以精确分组、额度和到期时间准备禁用的服务身份，不使用账号级身份字段。持久化不确定标记保护中断请求后的账号删除；重试核对同一身份，拒绝归属冲突，不重建已绑定却丢失的身份。准备阶段保持待处理，不启用访问。独立用量采样按服务保存累计观测，重复样本不重复计量；故障、缺失数据或计数回退时保留已确认用量及时间戳。前后台在缺少确认用量样本时显示用量与剩余未确认，不把初始零或配置额度当成已确认余额；客户与服务摘要区分尚未采集和采集失败，历史区分未配置、读取失败与无样本，无历史时不展示空图表或空数据表。资源未配置仅显示一条主提示，账号级同步与单份服务交付明确区分；采集失败保留原值、原时间及异常说明，不隐藏超额。月度边界与到期分开表达，已取消、已到期或到期不晚于下一边界时不再暗示发放下一周期额度。月度额度从持久累计检查点切换，不重置面板计数、不打断正常连接；检查点后流量归新周期，页面在面板确认后切换，重试保持同一绝对上限，已结束周期保留含超额的实际用量。定期核对无需管理员操作即可限制已确认到期／耗尽服务；准备、续期、解封和交付共用权益检查。模板额度修改为现有服务排入可审计调整，保留用量、原始条款和已结束周期；调低额度仍展示超额。服务暂停或取消且面板禁用已确认后，管理员可凭精确核查记录校正重置计数；恢复保留累计历史和计数映射，不替换身份、不自动恢复访问。取消后禁止续期和恢复；终态结算保留旧周期与固定检查点，记录后续精确用量，清除待切换状态而不虚称新额度已确认。删除身份前必须提交计量证据；撤销完成后可安全重试已提交核对，不访问已删除的面板身份、不重复校正。准备好的服务在计量确认后可申请交付，专用出口还须记录验证；持久请求使用共享权益同步器，暂停、封禁、到期和耗尽在重试后仍阻止访问。读取服务订阅时重新检查归属和面板条款，不在列表、浏览器存储或面板响应日志暴露凭据。服务详情从随包提供并验证的教程配置打开本地化客户端说明，只插入当前服务已确认链接；旧账号级教程接口继续不可用。终态取消保存撤销意图并重试原身份，保留最后接受的用量；最终计量与删除请求在移除身份前一同提交，原因不明的身份缺失保持待处理，不虚假完成撤销。已确认删除可跨面板临时故障重试，不丢弃计量证据。DELETE 后仍能读到身份时，保存新计数或异常并使旧删除证据失效，不采用其他服务的计数；停用前观察到的回退或重置保持待核对，即使后续读数变大也不抹去缺失用量。专用出口验证和人工回收记录管理员、证据及分配版本；回收要求确认身份已移除，且运营者随后提供旧连接已断开、旧配置不能重连的证据，不能仅凭面板响应释放资源。节点执行能力取决于版本和协议；公网固定独享、第三方客户端及未覆盖协议仍需专项验收，具体范围以实施计划为准。

- **简洁首页与套餐入口。** 首页沿用品牌布局，只展示已开通套餐数量和查看入口；桌面侧栏与手机底栏新增“我的套餐”，在独立页面查看用量、到期时间、订阅、教程与套餐目录。直接访问及刷新 `/services` 均可进入，不合并额度或自动选择连接。

- **统一管理台查询。** 总览将待处理操作前置，展示服务、阶段、脱敏原因与记录时间并直达对应服务诊断，节点管理离线／未知分别进入既有筛选；同时提供节点状态摘要、前三条待回复工单、多节点近 7 天日流量简图与反馈主题；完整 UTC 窗口流量对比位于节点列表，客户 → 多份服务 → 节点关系图仅位于用户详情，组／线路明细可展开；图表明确当前展示范围、缺失数据和采样覆盖，保留详情入口。节点默认方块视图并可切换审计表格，列表明确管理状态并突出流量与内存，完整标识及采集身份数可展开，桌面查询工具栏紧凑排列；侧栏“节点”返回列表，点击具体节点进入详情及服务／客户关系。客服计数读取失败显示未知并可刷新，节点详情以 Mbps 双折线展示最近 24 小时网卡 RX／TX 采样及各自峰值，主 worker 每 10 分钟采集并清理过期记录；缺少序列时明确未采集。节点详情在技术明细前以宽幅曲线和日流量柱状图展示网络采样；用户详情先呈现客户与当前页各份服务、节点的关系，再同图比较各份服务的 Panel 原始日历史并分别展示配额、周期，并与本地确认用量分开。管理员沿用网站账号进入运行概览，按客户与节点组织可折叠导航，支持键盘与手机侧栏操作；确认管理角色被撤销后卸载管理界面并清理管理数据，保留普通用户会话。客户列表逐账号展示独立服务数量、业务状态及同步摘要，观测明细可展开；未采集的活跃信息不冒充在线状态。全局服务列表支持跨客户搜索、状态筛选、排序和分页；详情展示条款快照、独立用量、同步证据及授权资源，保留原客户操作入口。节点清单、组与线路关系支持查询潜在影响服务和去重客户；客户关系卡片以站内导航进入服务详情；演示列表与详情保持每份服务的客户归属。客户详情跳转、刷新及返回保留来源查询，授权范围不冒充实际连接，节点流量不冒充服务计费量。节点详情展示 Node 所见 CPU 型号与核心数、内存、系统负载、运行时间和默认网卡速率，节点窗口流量使用明确的 UTC 查询窗口；负载不是 CPU 百分比，网卡量不是客户计费量，读取时间不替代未知采样时间，未知或未采集的指标不补零。最近流量采集身份数不冒充实时在线客户或连接数；上游返回零而缺少独立成功证据时保持未核实，即使系统指标存在也不将其判为无人在线。刷新失败保留旧值和时间，同时不维持当前在线的绿灯。概览说明各服务独立当前周期的混合汇总、异常维度重叠和归档范围，单项最近成功不冒充整体健康。手工待接入清单仅记录名称、地址和备注，可修改或删除本地登记，不连接、探测、安装或改动服务器；与已纳管节点分别展示和计数，不按同名同址自动纳管，也不计入在线节点、已采集指标或服务影响范围。概览分别展示客户、服务、交付同步和出口库存，保留来源、观测时间及未知／部分／失败状态；读取不会触发交付或用量重算，管理接口重新校验权限且不缓存到浏览器。

- **账号、服务操作与资源管理。** 管理员可在服务详情和客户服务列表查看预检、脱敏诊断、真实分页的操作记录，并对既有不确定意图进行幂等重试；归属、版本、封禁和归档冲突会阻断新请求。全局服务操作列表按客户、服务、执行阶段、状态与归档归属筛选，使用真实总数和游标分页；结果待核对与已失败分开呈现，没有执行证据的历史订单不冒充异常或成功，处理入口回到具体服务。账号封禁／解封的独立意图逐次留存操作者、变更前状态、目标状态、尝试次数、时间及脱敏结果；后续解封不覆盖封禁历史，自动重试复用原操作，旧结果不覆盖新意图。账号操作独立筛选和分页，无服务或已删除账号仍保留记录，未确认操作可进入异常视图核对。节点资源目录默认以关系卡片展示组与线路，保留审计表格；详情按入站展示已配置节点及匹配线路／授权组，可进入关联实体，完整标识和来源明细按需展开。启停、可见性及来源不完整分别标示，配置关系不冒充实时连接；登记 Node、创建组／Host、启停／重载节点及修改安全字段前，展示直接影响与可能重载的客户／服务清单，并重新核对管理员确认的范围。持久操作区分排队、上游回执、配置读回与实际通路，未知写入保留保护且不自动重放；人工证据核对资源身份，恢复原值须重新预览并创建关联操作。资源被外部删除后须人工核对才能解除对应操作的保护，解除保护不重建资源，也不宣称通路恢复。资源变更期间限制授权增加，同时保留暂停、封禁、撤销及计量处理。部署引导仅按权限生成敏感配置，不自动安装；Node 登记不等于客户端连通。高级维护入口仅使用显式配置的公开地址，不回退内部 API 地址，也不承诺单点登录（SSO）。dry-run 不伪装执行成功，原默认环境配置不变。

- **专用出口人工更换。** 两处服务管理入口共用更换流程，展示客户与服务影响，预留候选资源并保留旧资源，核对旧连接停用、用量和新出口证据后再确认切换。更换同时申请按原权益恢复，不解除封禁、暂停、到期或额度限制，不重建服务身份、不清零用量，也不自动降为共享出口。结果不明时保留原请求与资源，待核对后继续；旧资源须另行确认回收。核验记录与实际公网固定独享证明分别处理。

- **独立服务简体中文。** 网站与运营后台通过现有语言偏好和按范围加载机制提供 `zh-hans`，识别常见简体中文浏览器语言标签。账号、服务、资源和历史等核心流程提供中文，包括额度调整和用量核对；服务日期保持北京时间。切换语言同步更新文档语言，便于辅助技术识别。新邮箱账号通过验证码或登录链接注册时，沿用页面的语言 Cookie／浏览器语言选择；已有账号继续使用保存的偏好。英语和俄语继续可选，语言检查保护新增服务文案和占位符。运营页面、共享编辑器及账号／支持邮件补充中文。中文客户端指南和三语安装示例覆盖桌面、手机及支持的电视平台，注明官方下载来源与尚未验证的导入路径。中文文档正文、导航、社区目录、邮件预览、API 参考及生成的事件／面板兼容性目录同步使用中文，项目自有截图和第三方项目简介封面同步汉化，保留技术标识和历史来源。文档演示默认中文独立服务，保留已保存的语言选择；主题配色和系统字体选项同步本地化。


- **嵌套对话框键盘焦点。** 表情选择器在下一次键盘事件前接管焦点，立即按 Escape 会关闭选择器而不是父编辑器；保留已有焦点恢复断言。

- **可靠的支持处理器。** 外部集成获得所选工单所有者的受限上下文、保存后的新消息事件及分页变更核对。条件发送在同一锁内检查对话版本、状态和负责人；重复任务返回原回复。自动回复有独立来源和签名，并保留操作员的未读消息。上下文包含最近付款状态、连接、设备、系统、应用和最后服务器，注明来源及未知值。集成从与用户教程相同的配置取得专属订阅和下载链接，包含外部分组分配；最后服务器名称来自节点目录，单项读取失败不隐藏其余信息。回复支持普通按钮，任务重试同时核对文本和按钮。工单面板可一键插入带按钮的预设文本，出错或切换工单时保留编辑器内容。
  ([64ff99b6](https://gitlab.com/3252a8/remnawave-minishop/-/commit/64ff99b60416b68237049df9343cd4682af80099),
  [eaaf506d](https://gitlab.com/3252a8/remnawave-minishop/-/commit/eaaf506d3e3009b5ed4c54f412c419959421ad81),
  [74fcf09f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/74fcf09f3164d5f74dbdeedc87075ac359d1b361))

- **Mini App 套餐上限。** 购买订阅、礼品和变更套餐时，设备数、普通及高级流量以紧凑标签与名称同排显示，描述置于下方。区分未知上限、不限量和没有高级流量。流量包显示可选容量范围，使用共享元素与主题 CSS 变量。
  ([#104](https://gitlab.com/3252a8/remnawave-minishop/-/work_items/104))
  ([08ffdb12](https://gitlab.com/3252a8/remnawave-minishop/-/commit/08ffdb12f87bc052bd758ded580919f9e6138abc))

- **用户日志中的插件事件。** 公开 `PluginContext.emit_event()` 保存 `plugin:<名称>:<事件>` 来源，用户卡片增加“插件”标记。订阅者接收原载荷，载荷不复制进日志。
  ([#128](https://gitlab.com/3252a8/remnawave-minishop/-/work_items/128))
  ([1e72cc1c](https://gitlab.com/3252a8/remnawave-minishop/-/commit/1e72cc1c4d22b08c56b8a86ec2934255cf9d3eba))

- **Cryptomus。** Telegram 和网页应用支持以 RUB 或 USD 定价的加密货币账单。独立自动支付方式支持提供商的每周、每月和每三月计划，取消会停止 Cryptomus 计划。交付前验证签名、未足额付款和重复通知。不启用 P2P 快速支付系统（SBP），因为 Merchant API 未定义此方法。后台一张提供商卡片分组展示单次与自动支付设置。
  ([#95](https://gitlab.com/3252a8/remnawave-minishop/-/work_items/95))
  ([b27a7465](https://gitlab.com/3252a8/remnawave-minishop/-/commit/b27a7465fc150f1a8b0bc89e99607cccf63c6148))
  ([2aba04c2](https://gitlab.com/3252a8/remnawave-minishop/-/commit/2aba04c2ead293361af3ed2ba55e31f2d2ae2a53))

- **CisPay。** 支持银行卡、快速支付系统及加密货币单次支付；银行卡和快速支付系统可分别进行 RUB 自动支付，周期 7–360 天，支持确认取消及按提供商历史恢复已付款周期。后台提供图标与设置，一张卡片包含通用、单次和两类自动支付分组，不重复开关。
  ([#94](https://gitlab.com/3252a8/remnawave-minishop/-/work_items/94))
  ([650987c9](https://gitlab.com/3252a8/remnawave-minishop/-/commit/650987c95cb48d379b8f9f20fad6100e43667146))
- **Anore。** Telegram 与网页应用支持 RUB 和 USD 单次账单；后台可配置收银台、支付方法和外观。签名通知和状态核对检查原金额及币种，重复投递不重复授予购买权益。提供商 API 未定义循环扣款。
  ([#107](https://gitlab.com/3252a8/remnawave-minishop/-/work_items/107))
  ([880bd90d](https://gitlab.com/3252a8/remnawave-minishop/-/commit/880bd90dbc00cc332011b47ff631486b1a74677e))

- **邀请中的礼品激活计量。** 默认开启 `REFERRAL_GIFT_ACTIVATION_ENABLED`，成功激活按已有邀请关系和礼品快照为领取者与邀请者增加有效期。仅首次事件奖励时，个人购买与符合条件的激活共用一次名额；重试不重复增加。购买礼品、打开链接或旧激活不产生奖励。
  ([#108](https://gitlab.com/3252a8/remnawave-minishop/-/work_items/108))
  ([59a409c9](https://gitlab.com/3252a8/remnawave-minishop/-/commit/59a409c9daf133ec7c23161194d1bb82f3835055))

- **个人中心与 Telegram 付款历史。** 可从设置、桌面侧栏和机器人菜单进入，桌面设置入口占满容器宽度。用户分页查看自己的购买、提供商处理状态和权益发放等待状态。隐藏已过期未付款链接，点击“等待付款”可打开有效链接。翻页与刷新在表格中展示骨架屏，短页、空响应和错误时保持列表高度。悬停或点击可查看状态解释；消息和菜单按钮编辑器支持直达此页面。
  ([#55](https://gitlab.com/3252a8/remnawave-minishop/-/work_items/55),
  [#131](https://gitlab.com/3252a8/remnawave-minishop/-/issues/131))
  ([9b6d7044](https://gitlab.com/3252a8/remnawave-minishop/-/commit/9b6d7044287d9a38a3f7b4071cf36f1f0bf0c790))
  ([4962b3cb](https://gitlab.com/3252a8/remnawave-minishop/-/commit/4962b3cbcdf947d9d0da82fa3942a66638853a8f))
  ([51221a21](https://gitlab.com/3252a8/remnawave-minishop/-/commit/51221a2123502f6df1e12ab51c08c5c7c3f36ec5))

- **礼品链接二维码及图片导出。** 礼品使用共享二维码对话框，可下载当前链接的 PNG，在剪贴板支持时复制图片；复制被拒时给出明确消息，并保留下载。连接教程二维码居中，右侧紧凑按钮不影响图片位置。
  ([#123](https://gitlab.com/3252a8/remnawave-minishop/-/work_items/123),
  [#124](https://gitlab.com/3252a8/remnawave-minishop/-/work_items/124))
  ([687ba6dd](https://gitlab.com/3252a8/remnawave-minishop/-/commit/687ba6dd2ce20024c9bcd2fa5a296a2289b3cea4), [c0519541](https://gitlab.com/3252a8/remnawave-minishop/-/commit/c051954100e0198b13b57bae8146653485dfc640))

- **消息中的插件页面与短代码。** 所有按钮编辑器提供已启用扩展的用户页面；插件可增加本地化短代码，批量加载值并安全替换到消息。
  ([#126](https://gitlab.com/3252a8/remnawave-minishop/-/work_items/126))
  ([f055b7db](https://gitlab.com/3252a8/remnawave-minishop/-/commit/f055b7dbfd03add18378ede6160695dd1beeaebb))

- **后台手动合并账号。** 管理员从危险操作区搜索第二账号，比较包含最新登录方式和限制的简洁卡片，并确认保留的 ID。按通用规则迁移订阅与兼容登录方式；冲突、封禁和管理角色历史会阻止合并，结果写入日志。双方使用同一激活码不妨碍合并：保留两条历史与已增加有效期，不允许再次使用。合并事件仅在事务成功提交后发送，回滚不会触发扩展数据迁移。
  ([#96](https://gitlab.com/3252a8/remnawave-minishop/-/work_items/96))
  ([c0471f4b](https://gitlab.com/3252a8/remnawave-minishop/-/commit/c0471f4b62a14dfaa6d71b27a34df43a5d6f8ed0))

- **余额自动续期。** 余额设置移至支付系统独立卡片，提供合作伙伴计划入口。默认关闭的 `USER_BALANCE_RECURRING_ENABLED` 允许用户在所选个人／伙伴余额足以覆盖含灵活上限的完整周期时，在付款卡片启用自动续期。仅从所选来源扣款；混合支付、礼品和独立加购不会变为循环付款。余额自动续期启用时禁止资源加购。
  ([291d9e67](https://gitlab.com/3252a8/remnawave-minishop/-/commit/291d9e67da1d87e7a2ef5b831675ea67475d75ec))

- **将邀请注册奖励并入试用。** `REFERRAL_WELCOME_BONUS_ADDS_TO_TRIAL` 将邀请注册应得天数加到免费试用，而非另发订阅。机器人注册时告知总时长，应用在激活前展示；试用发放时标记奖励已用。后台邀请设置中的开关紧邻欢迎奖励天数，参与统一保存，保存前可重置。设置搜索按名称或变量名找到并高亮所有邀请设置；搜索名称与俄语／英语字段标签一致，包括欢迎奖励天数。跳转可滚动到下方字段，点击结果不取消自身滚动。默认关闭；保留 Telegram 绑定规则，试用激活前购买不授予这些天数。
  ([ac52973f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ac52973f820c417a8a0b163a5c2310cfbc46c9e8))
  ([6ee74f80](https://gitlab.com/3252a8/remnawave-minishop/-/commit/6ee74f80d0f4bb9041334450a6e3e671a8156c62), [e7a00a6f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e7a00a6fe2ceba5d65d7fbb862a81e16af493eeb), [181c82d1](https://gitlab.com/3252a8/remnawave-minishop/-/commit/181c82d1dbee601e03d8662b81d9702d8b815eb1))

- **二维码登录。** 开启 `QR_LOGIN_ENABLED` 后，新设备显示商店二维码；已登录设备通过 Telegram 或浏览器摄像头扫描，并输入新设备屏幕数字确认。二维码一次性使用，仅存哈希，只有发起登录的浏览器可取得会话。数字错误三次拒绝请求。设置展示商店公开地址；仅开启此方式时允许商店自身使用摄像头。关闭窗口取消请求，迟到响应不影响重新打开的对话框。桌面设置中的扫描按钮同样占满宽度。
  ([e167842b](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e167842b74c591d997f75e38cfd79da15e2e95cd), [992e6168](https://gitlab.com/3252a8/remnawave-minishop/-/commit/992e616823db67eabf1b96f6ffdd4d8bccfc4201), [83c8a3af](https://gitlab.com/3252a8/remnawave-minishop/-/commit/83c8a3afc7b0b3acb3805e6d6cdd2812a6b5cbdc))

<a id="изменено"></a>

### 变更

- **依赖与构建。** 更新兼容的 Python 包、网页和文档库、代码检查工具；使用标准生成器重建 lock 文件，Node 与 Docker CLI 基础镜像固定为最新不可变摘要。签名产物检查使用修复后的 Cosign 3.1.3，并验证可执行文件校验和。镜像扫描考虑漏洞库首次下载较慢的情况。
  ([3cc6b483](https://gitlab.com/3252a8/remnawave-minishop/-/commit/3cc6b483fb70a0ec97fc66a3575c4b1b344fdfd8))

- **Remnawave Panel 3.4.5。** 加入 API 认证矩阵，成为当前开发环境预设。验证真实面板读写、同库 `2.8.1 → 3.4.5` 升级及同步后订阅保留；此前认证版本继续保留。面板升级不要求调整核心设置。
  ([c5f384ce](https://gitlab.com/3252a8/remnawave-minishop/-/commit/c5f384ce751d9453b2fd5782f3f8b640d02977c0))
  ([面板变更](https://f.docs.rw/t/topic/354/26))

- **套餐邀请条款。** 多套餐条款相同时合并为一组周期并列出适用套餐；时长、奖励和访问限制不同的仍分别汇总。
  ([#125](https://gitlab.com/3252a8/remnawave-minishop/-/work_items/125))
  ([301144ca](https://gitlab.com/3252a8/remnawave-minishop/-/commit/301144ca5658820f71f1799a72ffb5b61b917c43))

- **邀请与试用。** 邀请注册所获订阅结束后可使用普通试用；该订阅期间购买或之后获得的订阅仍会关闭试用，现有有效订阅仍阻止试用。
  ([ac52973f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ac52973f820c417a8a0b163a5c2310cfbc46c9e8))

<a id="исправлено"></a>

### 修复

- **运行环境安全依赖。** Pillow 更新到 13.0.0、certifi 更新到 2026.10.19，镜像中的 pip 更新到 26.2.2；Nginx 两个构建阶段统一采用 1.30.6 的固定摘要。修复图像处理、证书信任链及 Nginx 的已披露问题，保留原有漏洞扫描门禁；发布须重新构建运行镜像，不能沿用旧依赖层。

- Wata 默认 IP 允许清单增加 `51.250.117.109`，避免该地址通知被 HTTP 403 拒绝；保留签名检查。

- 按 Telegram ID 自动合并面板记录时，保留最初手动创建的账号及名称。迁移 Minishop 套餐、上限、历史、续期同意及有效公开链接，并合并已付时长。部分失败后重试不重复增加时间，同时考虑新购买或取消。关联不明确或属于其他本地所有者的记录须人工处理。
  ([#132](https://gitlab.com/3252a8/remnawave-minishop/-/work_items/132))
  ([f21223f5](https://gitlab.com/3252a8/remnawave-minishop/-/commit/f21223f50ea87da258b1805379206807e62bf229))

- 插件表单区分新安装与更新。更新时显示保留启用／停用状态，操作名称和确认按钮不再误称会停用安装。
  ([#129](https://gitlab.com/3252a8/remnawave-minishop/-/issues/129))
  ([431e829c](https://gitlab.com/3252a8/remnawave-minishop/-/commit/431e829cdc6138132b0b15c1af3181e28abcddf1))

- 文档首页横幅、标题和按钮在手机与桌面居中；横幅适配页面宽度，按钮更紧凑，换行无多余间距。
  ([4d5740c5](https://gitlab.com/3252a8/remnawave-minishop/-/commit/4d5740c5c69ae6ee668d2cca282b1bdfe6c009a4))

- 隐藏套餐私有链接在首次购买和试用转付费时可确认价格并创建付款，包含所选额外设备。重算购物车时保留访问码；无有效码时，未分配的隐藏套餐仍不可访问。
  ([#127](https://gitlab.com/3252a8/remnawave-minishop/-/work_items/127))
  ([d3c83fe0](https://gitlab.com/3252a8/remnawave-minishop/-/commit/d3c83fe0232aa6f5fc639745ac4e3f895783c697))

- 公开订阅网关兼容 Remnawave Panel 内部 HTTP 端点：从可信客户端地址构造代理头，保留配置、HWID 和面板拒绝状态。两份外部 Nginx 示例支持较大客户端设置头，并为商店头预留空间。
  ([681a9d9d](https://gitlab.com/3252a8/remnawave-minishop/-/commit/681a9d9d4bb38ffa6e486e6768b22c23b76088cc))

- 设备进度区分有限额度、达到或超过额度、不限量和等待数据。告警按精确设备数计算，提供可访问标签，并在断开设备或刷新列表后更新；进度四舍五入为 100% 本身不表示额度耗尽。
  ([3a68326f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/3a68326fbbd469bb540d8a4fdcb9b7838e6c7df7))

- 设置中的文档列表先等待 API 响应。图标对应文档用途，顺序和链接稳定；确认缺少相应文档后才显示旧隐私与协议链接，包括空响应或旧 API 不可用的情况。
  ([17a70235](https://gitlab.com/3252a8/remnawave-minishop/-/commit/17a70235971da47cb6af2cdf3e8039e153477fd9))

- 从文档返回个人中心后，即使查询参数／哈希已不存在，Telegram SDK 仍从已保存启动上下文恢复。文档与个人中心共用全屏及安全边距生命周期，清理处理器并支持 SDK 延迟加载。普通浏览器不会因损坏数据得到 Telegram 边距；签名鉴权参数不进入公开文档链接。

- 没有已发布侧栏项目的文档，在手机切到桌面布局时仍使用完整可用宽度。仅存在菜单时显示导航列，保留适合阅读的正文宽度限制。
  ([807d2096](https://gitlab.com/3252a8/remnawave-minishop/-/commit/807d20967bf5e42edb817ca54be444e5b4c84cdb))

- 演示主题导入的 SVG 验证解析 XML 时不删除注释；拒绝无效结构、外部命名空间和编码的外部链接。OAuth 返回参数作为查询数据编码；HTTPS 客户端显式要求 TLS 1.2 或更高。表情检查使用精确 Unicode 范围，避免含糊正则区间。
  ([ce1cf256](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ce1cf256ba9848ab38458747a732eb0d9ac0b57f))

- 管理员保存的 Xray Checker、Uptime Kuma、SMTP 和 PayKilla 汇率地址，可无需重启连接精确的内部主机与端口。许可随当前设置变化，监控更新连接，汇率地址更改后不使用旧来源缓存。独立 worker 从数据库读取保存和重置后的 SMTP 与支付提供商设置。
  ([5fe9d6b8](https://gitlab.com/3252a8/remnawave-minishop/-/commit/5fe9d6b803f24cac6d0ebd6745bcdb9d44effa9c))

<a id="производительность"></a>

### 性能

- 本地检查依赖在工作副本外复用。Linux 测试环境与源码及前端构建隔离，无后台进程保留环境，使用经验证的 Docker Hub 不可变摘要镜像。旧环境清理只处理自身未运行的保留容器。CI 浏览器检查拆成两轮；完整本地环境正确排除已禁用的可选依赖。
  ([1f2b3782](https://gitlab.com/3252a8/remnawave-minishop/-/commit/1f2b3782d7c0c28873007905b731ae045ba1ca3d), [a507fd4b](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a507fd4b5bf2bc268b0438be0d5090699c5f3a2b))

<a id="при-обновлении"></a>

### 升级注意

- 通过 `CISPAY_SUBSCRIPTION_CARD_ENABLED` 和 `CISPAY_SUBSCRIPTION_SBP_ENABLED` 启用 CisPay 自动付款，提供商也须为商店开通权限。

- 迁移 `0105` 保存循环计划所有者和原始购买。Cryptomus 自动付款通过 `CRYPTOMUS_SUBSCRIPTION_ENABLED` 单独启用；提供商负责排期和扣款，标准 worker 负责确认与权益发放。

- 迁移 `0102` 保存余额自动续期同意。支付系统设置中须另行启用 `USER_BALANCE_RECURRING_ENABLED`；自动扣款要求标准 worker 运行。

- 邀请注册所获订阅结束后，用户无需人工重置即可使用试用。

## v3.8.1 — 2026-10-06

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.8.1) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.8.1)

<a id="обзор"></a>

### 概览

新增 Telegram 自定义表情与机器人菜单彩色按钮，扩展广告分析。改进跨服务器备份迁移、用户账号管理、支付、流量计量、通知和 Remnawave 同步，并加强安全性。

<a id="изменения"></a>

### 变更

* **Telegram 外观设置与表情库。** 后台可配置按钮颜色、自定义表情及菜单预览；群发、邮件和支持工单支持表情。 ([a97c04e4](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a97c04e4048e3dbdc60e33a08c40127f4cb9f09a), [1b192d57](https://gitlab.com/3252a8/remnawave-minishop/-/commit/1b192d579e34d2dfba6fb9a9c662e1d75911e8e9), [df59e047](https://gitlab.com/3252a8/remnawave-minishop/-/commit/df59e04795a3add62b164dee4a4fdbdb59b63656), [148a5d94](https://gitlab.com/3252a8/remnawave-minishop/-/commit/148a5d94a5ae5a38ad26c3b5560034efa6da390c))
* **广告分析扩展。** 活动整合链接、UTM、联系人、费用和订单来源；新增按周期与群组报表、带预览的统计导入、CSV 导出，以及通过 `/my_ads` 使用的广告主中心。 ([4b05c59f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/4b05c59fc2a3ccc78ebd3c7102c1017e14dbe330), [75cc04e5](https://gitlab.com/3252a8/remnawave-minishop/-/commit/75cc04e5b4431a3db3847205c04965a1d679043e))
* **扩展并验证后台跨服务器备份迁移。** 归档包含已安装插件和自定义主题，排除已删除包与临时文件。大型归档分片发到 Telegram，恢复时重组；无 Telegram 也可手动创建备份。 ([874f14d6](https://gitlab.com/3252a8/remnawave-minishop/-/commit/874f14d60c2ee43bd783cdb22efcb37d22b2298f), [1566e94e](https://gitlab.com/3252a8/remnawave-minishop/-/commit/1566e94e76dd765f5f167224e63703c869d35ee5), [144e467f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/144e467f093c4127f438113a0a9b1c89bc13e874))
* **改进账号与设备管理。** 用户卡片改在后台主区域打开，替代弹窗并适配手机。用户可重命名设备。不同提供商账号合并可通过重新登录、通行密钥或邮箱验证码确认，不再强制要求 SMTP。 ([cc10b4e3](https://gitlab.com/3252a8/remnawave-minishop/-/commit/cc10b4e3ca9099b1130151205802a4aeff5ad473), [d2684d42](https://gitlab.com/3252a8/remnawave-minishop/-/commit/d2684d4229c0a831201d6421dc45c37d88069d2c), [33762c9f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/33762c9f7f955349fa4286b1c0757ca9a2b65c65))
* **改进 Remnawave 同步。** 面板标识变化后重新关联会保留订阅、有效期和历史，修复不完整关联，合并相同 Telegram ID 的重复记录。确认配置已删除不再阻止发放已付款订阅。分离 API 与浏览器面板地址。 ([6b43d46f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/6b43d46fb7d1b0e2ee05307b7a3be5e9a49faf8b), [a64bc651](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a64bc65193ffd16116f57e093d482fcde405ac79), [2a1b9bd7](https://gitlab.com/3252a8/remnawave-minishop/-/commit/2a1b9bd7852124c4bfe631c7017a3d8409fb576c), [312541a8](https://gitlab.com/3252a8/remnawave-minishop/-/commit/312541a8db3862972b77f8c07898acd9c8dd0464), [331c1564](https://gitlab.com/3252a8/remnawave-minishop/-/commit/331c1564516958812d66a2c7ff97021ee4456b6a))
* **改进通知和访问凭据重发。** 通知实时使用当前订阅有效期和渠道设置，无需重启 worker；临时投递错误按渠道独立重试。重发在响应丢失后可恢复，不再次变更链接。网关正确转发客户端头，并在日志隐藏令牌。 ([a19c59d7](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a19c59d7dbfaf06485188ed6acad3b364547a6a7), [320c7d2e](https://gitlab.com/3252a8/remnawave-minishop/-/commit/320c7d2e418db6bc99e32db77e25e626c22be396), [f887ec3e](https://gitlab.com/3252a8/remnawave-minishop/-/commit/f887ec3ef8bb4d41f32c950dc8287e42767ae442))
* **修复支付流程。** 已付款但价格计算过时的 YooKassa 订单转为核查，不再无限重试。输入激活码后自动选择兼容付款方式；续期打开当前套餐。支付集成使用运营者配置的 API 地址。 ([dd397b4d](https://gitlab.com/3252a8/remnawave-minishop/-/commit/dd397b4dc31b2eb4f311e0b07176c1e285db454c), [ed8d24e6](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ed8d24e668f8d1648e5767eca0269b18dc518e3b), [8ec08e9c](https://gitlab.com/3252a8/remnawave-minishop/-/commit/8ec08e9c5bc813407e1b8273d4e545fdd74246f9), [dd20fb52](https://gitlab.com/3252a8/remnawave-minishop/-/commit/dd20fb52d0f1fe752e9913385e8430e7b04e73e7))
* **修复流量计量。** 试用后购买套餐会清除试用已用流量。可结转流量包在每次计数重置时核算，不重复扣减。首页显示试用高级流量独立额度，区块名称可配置。 ([914604e1](https://gitlab.com/3252a8/remnawave-minishop/-/commit/914604e1f7499c2e2fad73dbe63207ab5301dbee), [e328463c](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e328463cf30e1f0c3f4083fd1d66450762a1295a), [bd7c004c](https://gitlab.com/3252a8/remnawave-minishop/-/commit/bd7c004c81c4afc9f4f456d78255f4cd95a54726), [34143c04](https://gitlab.com/3252a8/remnawave-minishop/-/commit/34143c04a059ccd4ae3199fccaced22a70ebce90))
* **扩展邀请与奖励。** 新增受邀人数、增加时长统计及链接二维码。奖励持久入队，各参与方独立重试。首次购买仅计符合条件的订阅；合作伙伴限制同样适用于已有关系。有效礼品链接可在仅限邀请模式下注册。 ([e5d2495b](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e5d2495b4939eef021db575b9dc9eda8e698554c), [27217858](https://gitlab.com/3252a8/remnawave-minishop/-/commit/2721785878c52f89c409f0a50c7ff4820a1fe5f4), [118a0f67](https://gitlab.com/3252a8/remnawave-minishop/-/commit/118a0f675f3683ec0d8294c2a27e6faabeef5f6f), [269b1023](https://gitlab.com/3252a8/remnawave-minishop/-/commit/269b1023533d9ca585c8afb3d19211461c370b59), [2cf966e6](https://gitlab.com/3252a8/remnawave-minishop/-/commit/2cf966e64bd18f53d74680dfa0dc6bf58782dc9a), [7964b5e5](https://gitlab.com/3252a8/remnawave-minishop/-/commit/7964b5e5b390087d84ccbe81239aac89c04b1709))
* **改进主题和连接教程。** 管理员可独立允许用户 Mini App 主题特效，扩展安全 SVG 支持。教程加载失败可重试；价格动画设置作用于结算全部数值。 ([93b0cd50](https://gitlab.com/3252a8/remnawave-minishop/-/commit/93b0cd50b85faea85287d9bd3b3289a9efdfab3b), [8e8c2ac3](https://gitlab.com/3252a8/remnawave-minishop/-/commit/8e8c2ac3c9ef72cee1c04d691f31bbbb6184ab1a), [87adec45](https://gitlab.com/3252a8/remnawave-minishop/-/commit/87adec4534e6fed4df89be1216b3f4709a25ab5b), [c13440b3](https://gitlab.com/3252a8/remnawave-minishop/-/commit/c13440b3e12136cd382a5899033df4af92234948))
* **加强 Mini App 与集成安全。** 新增原子请求配额、浏览器来源验证及精确代理地址信任。防止管理员封禁所有者、支付密钥发往其他来源、SMTP 连接风险和 CSV 公式执行。 ([f530ca1b](https://gitlab.com/3252a8/remnawave-minishop/-/commit/f530ca1b4c700bb297b8357aeaa2e31a52f08b5f), [7689c39e](https://gitlab.com/3252a8/remnawave-minishop/-/commit/7689c39ecb939c63517d73bcb20aeaa10e4e6e02), [29a44312](https://gitlab.com/3252a8/remnawave-minishop/-/commit/29a4431201fa857b2a0fb646ded1baabc5da5899), [82735247](https://gitlab.com/3252a8/remnawave-minishop/-/commit/82735247cbf40f28dca3376296b3579cca9cfe0e), [d7d5cb3c](https://gitlab.com/3252a8/remnawave-minishop/-/commit/d7d5cb3cda59ad320970c748a78a32bb13db2a93), [c26ab8a8](https://gitlab.com/3252a8/remnawave-minishop/-/commit/c26ab8a82aac25e169d54ac980a935d04a91f41f), [bb2a88fe](https://gitlab.com/3252a8/remnawave-minishop/-/commit/bb2a88fe7dd5dcc226d6b0e40e97e702e0959471))
* **更新插件功能、依赖和文档。** Git 插件检查更新时保留所选分支；延迟导入降低启动器内存。更新依赖和构建工具，固定已修复包版本。新增 Awesome Minishop 目录并扩充指南。 ([1c1c5f8e](https://gitlab.com/3252a8/remnawave-minishop/-/commit/1c1c5f8e0b233d5d3040c90c0366f3879b0119fa), [933bad98](https://gitlab.com/3252a8/remnawave-minishop/-/commit/933bad988da9c8fbd727b8f8db5ef4f60d4fee76), [8f90cda4](https://gitlab.com/3252a8/remnawave-minishop/-/commit/8f90cda43a6f6376a53c011bcd49d620ab3262f0), [bc337981](https://gitlab.com/3252a8/remnawave-minishop/-/commit/bc3379812b370ed4420b97338fc24fce5c87f1a6), [5e741824](https://gitlab.com/3252a8/remnawave-minishop/-/commit/5e7418243e40151f620b4be475fd253a62725c13), [e3b88fa9](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e3b88fa9600b3f2bc303de391b9261bb0f9342d2))

<a id="при-обновлении-1"></a>

### 升级注意

* 新增迁移 `0094`–`0100`，涉及奖励、访问凭据重发、设备名称、广告分析、流量计量和通知。后台投递与重试要求标准 worker 运行。 ([118a0f67](https://gitlab.com/3252a8/remnawave-minishop/-/commit/118a0f675f3683ec0d8294c2a27e6faabeef5f6f), [a19c59d7](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a19c59d7dbfaf06485188ed6acad3b364547a6a7))
* 面板 API 仅 Docker 内可访问时，通过 `PANEL_PUBLIC_URL` 单独设置浏览器地址；留空保留原链接行为。 ([331c1564](https://gitlab.com/3252a8/remnawave-minishop/-/commit/331c1564516958812d66a2c7ff97021ee4456b6a))
* 自定义反向代理须在 `TRUSTED_PROXIES` 配置精确 IP／CIDR 或 `host:服务名`。将原来信任所有私网改为精确地址；标准 Docker 代理无需显式配置。 ([29a44312](https://gitlab.com/3252a8/remnawave-minishop/-/commit/29a4431201fa857b2a0fb646ded1baabc5da5899))
* 不推测恢复历史奖励或未知流量。奖励统计从新迁移开始；补算多次遗漏的重置需要完整面板历史。无需手动清理通知历史。 ([e5d2495b](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e5d2495b4939eef021db575b9dc9eda8e698554c), [e328463c](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e328463cf30e1f0c3f4083fd1d66450762a1295a), [a19c59d7](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a19c59d7dbfaf06485188ed6acad3b364547a6a7))

贡献者：wormy09（`e328463c`、`d2684d42`、`e5d2495b`、`27217858`）和 Roycce（`75cc04e5`、`933bad98`）。临时邮箱域名列表由 github-actions\[bot\] 自动更新（`96a1466e`）。

## v3.8.0 — 2026-09-30

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.8.0) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.8.0)

<a id="обзор-1"></a>

### 概览

新增独立于 Telegram 的账号、签名插件安装、公开订阅网关、信息页面和 JavaScript 主题特效。改进支付、通知、后台与性能。

<a id="добавлено-1"></a>

### 新增

- **无需 Telegram 的账号。** 核心可作为邮箱登录、独立 Minishop ID、可选 Telegram 绑定的浏览器商店运行。集中管理所有者和管理员权限；卡片、关联记录及通知使用公开 ID，迁移保留已有面板关联。 ([e060e2e9](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e060e2e98577bd5f3191a0a6b18e1a302698cc38), [ca46af6d](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ca46af6dcbf0098e697ed57a1ddb40ff580174b2), [2a045291](https://gitlab.com/3252a8/remnawave-minishop/-/commit/2a045291f42980c7d884fc843fcb79fd201ae192))
- **安装签名 ZIP 插件。** 管理器检查签名、最低核心版本与所需 API 能力，展示包设置和状态，支持删除启用包，并在进程重启后确认变更。 ([ea82a92f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ea82a92f1cc548fcc2882be30a60f180624fa53a), [d97a9358](https://gitlab.com/3252a8/remnawave-minishop/-/commit/d97a93586aa1409800168d815c989ea767cd1abf), [a498317b](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a498317bcb42ad26a956677ca1e101727e28d8d4), [98382cd6](https://gitlab.com/3252a8/remnawave-minishop/-/commit/98382cd65d216c4280bd238f7c4c7fde5088bc2c), [5f283037](https://gitlab.com/3252a8/remnawave-minishop/-/commit/5f28303741c96b31009c9cb8f5afa6c3f3ddba12))
- **扩展用户与后台区域。** 插件可增加页面、卡片、连接教程、付款后交付的外部订单、可靠后台任务、可审计权限及备份数据。已有区域支持扩展组合，考虑隐藏区域、直达链接、运行时资源及已安装扩展更新。 ([33121363](https://gitlab.com/3252a8/remnawave-minishop/-/commit/331213638460da024df4186fc60141d4cb9607cf), [af122b9d](https://gitlab.com/3252a8/remnawave-minishop/-/commit/af122b9d1332430e39c0fb5bc877226974c1d3f3), [bc8ca963](https://gitlab.com/3252a8/remnawave-minishop/-/commit/bc8ca963526433493e9bb8f8375408e530c18204), [f1f91d94](https://gitlab.com/3252a8/remnawave-minishop/-/commit/f1f91d947a6bc6836f93cb7a63e2ebcc9e6980a0))
- **后台插件翻译。** 插件文案从通用组移到独立区域，每个插件一组；插件可进一步定义带可翻译名称的嵌套分组。 ([1b5b3697](https://gitlab.com/3252a8/remnawave-minishop/-/commit/1b5b3697ad3a34be7b4ba9d86e629ccffed346d4), [0d16c02a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/0d16c02a89e09408adcf2c1acbfcc39e12322dc8))
- **公开订阅网关。** 可通过商店域名发放连接链接，后台可选择链接模式；网关默认启用，并支持较大的订阅响应头。 ([0c046b2c](https://gitlab.com/3252a8/remnawave-minishop/-/commit/0c046b2c60bf85cc7cdb316ef8f1356bc531fb2f), [8e60f1f9](https://gitlab.com/3252a8/remnawave-minishop/-/commit/8e60f1f9cb47e6b7ada0d8fe4bf964e6de0e2dea), [4969be67](https://gitlab.com/3252a8/remnawave-minishop/-/commit/4969be67e519fcf0484572ec86066bc693f509fb), [d3e63b62](https://gitlab.com/3252a8/remnawave-minishop/-/commit/d3e63b627ad4f3bfdfe658acdbd3264341187724))
- **激活码分析。** 新增搜索、状态和适用范围筛选、详情直达，以及激活历史中按币种统计的已确认付款收入。 ([caddef66](https://gitlab.com/3252a8/remnawave-minishop/-/commit/caddef66eea805e09cd844c593efb13e5b41e5d6))
- **信息页面。** 新增可管理 Markdown 页面，在 Mini App 内打开文档，编辑保留格式和状态。核心在 Windows 运行时，文档存储同样阻止并发修改。 ([d94c943a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/d94c943ae97242e45633e138204ffecd33e71029), [fc816ca6](https://gitlab.com/3252a8/remnawave-minishop/-/commit/fc816ca6d4037b6c64fdb522c3684626a800aa37), [8ff40829](https://gitlab.com/3252a8/remnawave-minishop/-/commit/8ff408292f7af1197a327e5f8b6d1c2bef471965), [de94f444](https://gitlab.com/3252a8/remnawave-minishop/-/commit/de94f444c3abc43251b6f49c27fbcd8c7fd01ac6))
- **JavaScript 主题特效。** 主题包可包含特效，扩展设置与主题管理；外观设置并发写入时保留草稿。主题库实时预览在真实首页布局叠加适配器；Mini App 打开主题预览后立即运行该主题特效，无需重启。 ([8c311f9a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/8c311f9ab3fef0cec6823b0026a36fd0d439d7d1), [b4f02e65](https://gitlab.com/3252a8/remnawave-minishop/-/commit/b4f02e6545d640ca8f2c958982259b41b8620eba), [a8b786c9](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a8b786c9ad4293bae5d4fe577a6c2e6415bb178f))
- **群发诊断。** 历史显示未送达消息详情；立即群发在管理员 HTTP 请求之外入队。 ([355a7532](https://gitlab.com/3252a8/remnawave-minishop/-/commit/355a75324205a8a98276c97c5ee9f5dcb226f922), [ffcb90d2](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ffcb90d26842b7fbc7e2dc077c0eb411670a61a4), [bb53fb70](https://gitlab.com/3252a8/remnawave-minishop/-/commit/bb53fb700b0f9130d23af7f827a5fb4d90c19b48))

<a id="изменено-1"></a>

### 变更

- **依赖。** 更新 Python 和 npm 包，前端转向 nginx 1.30 稳定分支；修复网页与文档构建中间接依赖 `brace-expansion`、`undici` 的已知漏洞。 ([bd153166](https://gitlab.com/3252a8/remnawave-minishop/-/commit/bd1531668dceb22bcb93149561cbb2e19edd5758), [ea6c8830](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ea6c88308e2fd5e1f9c9ed26c81c2b0792826327), [2b975207](https://gitlab.com/3252a8/remnawave-minishop/-/commit/2b975207e645e9b6a830e9139d863589ec7f7ba2))
- **通行密钥注册。** 设备支持时优先 EdDSA；拒绝损坏的 CBOR 与无效证明格式。 ([e060e2e9](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e060e2e98577bd5f3191a0a6b18e1a302698cc38))
- **登录与会话。** 登录方式随屏宽排列，宽按钮置于紧凑按钮之前。会话有效期可配置，默认 30 天。 ([88992d4d](https://gitlab.com/3252a8/remnawave-minishop/-/commit/88992d4d9e132982339ab6af09d0b41e85dc2838), [4a9aee9a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/4a9aee9ae7a4ebb842c977ee8d99dbc065fefc82), [e7f82c1a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e7f82c1ad9a1f4eb2d59aee27ea9de10cfeb8156))
- **用户卡片。** 简化手机布局，可直达面板用户；验证套餐变更并明确显示操作错误，封禁账号同步到面板 VPN 访问限制。 ([5cd0838c](https://gitlab.com/3252a8/remnawave-minishop/-/commit/5cd0838ca0b2a3621f69d7336bc2a60afdfe8bd8), [da0e5772](https://gitlab.com/3252a8/remnawave-minishop/-/commit/da0e577259d8cd78c11219f88a067c94a956a361), [e0e3d315](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e0e3d31505681d65a8c9932de28aa84392077aa4))
- **通知与支持。** 统一账号数据和日志跳转，在通知及对话框显示工单主题，付款通知包含付费套餐升级。日志用户按钮打开正确 Telegram Mini App 用户，包括排行榜，不生成带模板机器人名的链接。不再向封禁用户发送 Telegram 或邮件自动通知。 ([5c4636df](https://gitlab.com/3252a8/remnawave-minishop/-/commit/5c4636df4a972e92b727c33bcac660cabd88ee3b), [e193e7fc](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e193e7fc3778406e467707047466a301544ef22a), [a78a8d49](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a78a8d49596634e496e68d800a371ca5aa3f2f88), [bc0f1305](https://gitlab.com/3252a8/remnawave-minishop/-/commit/bc0f13054a8f449eb9354a05f20bc0bf351c1722), [14eebebd](https://gitlab.com/3252a8/remnawave-minishop/-/commit/14eebebda66c186465a47adbe31937983901c00b))

<a id="исправлено-1"></a>

### 修复

- **个人中心首页。** 标志尺寸受可用区域限制，使底部订阅与操作区保持贴底，不产生多余滚动。 ([a2282f31](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a2282f31da304564186aa1636caff60281521242))
- **面板同步。** 有 Telegram ID 或邮箱的面板新用户及其订阅可进入商店，无需回退稳定版。面板邮箱在验证码登录前保持未验证；与其他本地账号冲突时须人工核查。 ([3e47e2b6](https://gitlab.com/3252a8/remnawave-minishop/-/commit/3e47e2b64f04836699897dfb8408230f2c5605f6))
- **合作伙伴链接。** Google、Yandex、Discord 注册跳转时保留网页邀请代码，创建账号时应用。Telegram、邮箱及外部登录的新注册通知包含邀请伙伴。 ([1e329cf8](https://gitlab.com/3252a8/remnawave-minishop/-/commit/1e329cf88037912427005a5d11a049e5ecf3ff05))
- **事件日志。** 群通知中的用户卡片按钮先打开机器人私聊，再定向到用户卡片；机器人名未知时使用网页链接。 ([14eebebd](https://gitlab.com/3252a8/remnawave-minishop/-/commit/14eebebda66c186465a47adbe31937983901c00b))
- **账号合并。** Telegram 已绑定其他账号时，确认身份后打开邮箱验证码合并流程。浏览器与 Telegram Mini App 均支持；仅双方确认后合并订阅。 ([21d83ab7](https://gitlab.com/3252a8/remnawave-minishop/-/commit/21d83ab71c805f039742eb2513d9d8de24b3f4a0))
- **付款与循环订阅。** 支持固定付款周期；充值隐藏循环方式，余额付款选择兼容方法。取消 Tribute Creator 时引导到机器人。管理员可在 Tribute 自动续期开启时更换套餐：Shop Order 通过 API 取消；Creator 经管理员在 Tribute 取消后关闭本地续期。用户也可在 Mini App 对话框确认 Creator 取消，立即关闭本地续期而不影响已付有效期。 ([523e3646](https://gitlab.com/3252a8/remnawave-minishop/-/commit/523e36467478a56a04bdc32097009a3b2e215ff2), [0ac2488a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/0ac2488a1911fd68095fb03eae7d5f1703f8c5e8), [0de2db99](https://gitlab.com/3252a8/remnawave-minishop/-/commit/0de2db9922c2054e3fe69185adb7b9d10075c34e), [1d9e6ff0](https://gitlab.com/3252a8/remnawave-minishop/-/commit/1d9e6ff00dbcaab3885ffe31f1cfd84b767df499), [62bf0f41](https://gitlab.com/3252a8/remnawave-minishop/-/commit/62bf0f4193b708b3abf7ed3dc73289faf5093b55))
- **手机 Mini App。** 对话框、下拉菜单等浮层限制在 Telegram 安全区域；修复支持与编辑器布局、Telegram 链接和后台预览。 ([81e7a765](https://gitlab.com/3252a8/remnawave-minishop/-/commit/81e7a765748a9b92a8f83f7a9fd3c1f8516073b4), [317b72c7](https://gitlab.com/3252a8/remnawave-minishop/-/commit/317b72c78f8b520c54caad12e135ebba06531170), [29790339](https://gitlab.com/3252a8/remnawave-minishop/-/commit/297903391ad9211fce59945904cfbcd690dd76fa), [e027c982](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e027c982913d804b27ebbbc4878402d540a45af6))
- **连接教程。** Happ、INCY 应用按钮获得正确加密链接；二维码与复制始终使用 HTTP 订阅链接，不受所选应用影响，无连接按钮也可使用。页面加载失败可恢复；初始配置使用面板公开地址。 ([44054551](https://gitlab.com/3252a8/remnawave-minishop/-/commit/44054551a986449fddc7b7061067626e4534358d), [01d6661b](https://gitlab.com/3252a8/remnawave-minishop/-/commit/01d6661b61365f148cf2f42af8070037d0f6148a), [f11955cc](https://gitlab.com/3252a8/remnawave-minishop/-/commit/f11955cc8c7c3db34943b238ae96cb0e4ca99009), [04841434](https://gitlab.com/3252a8/remnawave-minishop/-/commit/0484143477b6f4ccb1da6f96fa93014658ca1ea7))
- **身份与套餐。** 保留旧账号尚未解析的面板关联，以及 Torrent Blocker webhook 的数字用户标识。套餐界面不再承诺面板不会执行的流量重置。 ([f9fbb93c](https://gitlab.com/3252a8/remnawave-minishop/-/commit/f9fbb93cbc3dc91f7aa1e10357deafd543b65914), [9192b420](https://gitlab.com/3252a8/remnawave-minishop/-/commit/9192b420ff836b5b6342a9f3407297d37bb5430f), [be3cab79](https://gitlab.com/3252a8/remnawave-minishop/-/commit/be3cab79e615686fbda81b69fa63dec617bb7802))
- **邮件群发。** 投递是否可用取决于 SMTP 就绪状态，与邮箱登录开关无关。 ([bb53fb70](https://gitlab.com/3252a8/remnawave-minishop/-/commit/bb53fb700b0f9130d23af7f827a5fb4d90c19b48))

<a id="производительность-1"></a>

### 性能

- 加快后台首次登录、翻译与插件视图加载及滑块操作。网页应用等待初始化数据，API 启动中会重试；后台在翻译就绪后显示。大型翻译组分批展开，未更改的翻译文件不再每次请求都与数据库核对。 ([0b2c5f00](https://gitlab.com/3252a8/remnawave-minishop/-/commit/0b2c5f003df18e3ea0fc9b756580f5f282a1d844), [e2b60313](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e2b603139c12f8908bf5c8cabc57581ab4592946), [0d16c02a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/0d16c02a89e09408adcf2c1acbfcc39e12322dc8), [e85b6812](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e85b68122a04e62361cb9b0bf0f9190d48c668f9))
- 备份列表只读取文件元数据，不检查所有 ZIP 内容；选定归档单独检查。列表加载不再阻塞其他后台区域请求。 ([d67a2d85](https://gitlab.com/3252a8/remnawave-minishop/-/commit/d67a2d855ca5d983d853d6c4a500fe8347c5d3d4))
- Windows 本地 Linux 后端测试把源码复制进 QA 镜像，替代较慢的绑定挂载；构建时安装并缓存依赖。 ([de94f444](https://gitlab.com/3252a8/remnawave-minishop/-/commit/de94f444c3abc43251b6f49c27fbcd8c7fd01ac6))

<a id="документация"></a>

### 文档

- 文档站新增含 dev 章节的统一更新历史，提供页头链接及侧栏底部入口。演示支持所有后台区域的直达地址和插件加载。 ([859a248e](https://gitlab.com/3252a8/remnawave-minishop/-/commit/859a248e73564affe2989a0797d84fa408888fe8), [93c7ad93](https://gitlab.com/3252a8/remnawave-minishop/-/commit/93c7ad939d50dd04f4ed08d77bd86e4442dd8810), [c0bc1a06](https://gitlab.com/3252a8/remnawave-minishop/-/commit/c0bc1a06b518010dd46c507ddc68b728142ef400), [f5594777](https://gitlab.com/3252a8/remnawave-minishop/-/commit/f559477746e080df5363a40824b74529261c79fd))

<a id="при-обновлении-2"></a>

### 升级注意

- 新增迁移 `0088`–`0093`，处理教程链接、扩展数据和独立账号身份，包括 ID 序列及面板关联来源。 ([0c046b2c](https://gitlab.com/3252a8/remnawave-minishop/-/commit/0c046b2c60bf85cc7cdb316ef8f1356bc531fb2f), [33121363](https://gitlab.com/3252a8/remnawave-minishop/-/commit/331213638460da024df4186fc60141d4cb9607cf), [e060e2e9](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e060e2e98577bd5f3191a0a6b18e1a302698cc38))
- 独立运行使用 `TELEGRAM_ENABLED=False`，须配置邮箱登录、SMTP 和应用公开地址。通过可信命令 `bootstrap_owner.py` 指定首位所有者，之后在后台通用设置管理角色。见[不使用 Telegram](docs/features/telegram-optional.md)。 ([e060e2e9](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e060e2e98577bd5f3191a0a6b18e1a302698cc38))
- 安装扩展前检查所需核心版本与能力，重启后等待状态确认。见[插件契约](docs/development/plugin-contract.md)。 ([ea82a92f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ea82a92f1cc548fcc2882be30a60f180624fa53a), [a498317b](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a498317bcb42ad26a956677ca1e101727e28d8d4))
- JavaScript 主题特效默认关闭，需要管理员单独授权。这是页面内的可信代码；授权不会随导出传递，恢复备份时重置。见[特效信任模型](docs/features/theme-effects.md)。 ([8c311f9a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/8c311f9ab3fef0cec6823b0026a36fd0d439d7d1))

## v3.7.2 — 2026-09-21

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.7.2) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.7.2)

<a id="обзор-2"></a>

### 概览

新增由 Wata 提供商排期的循环付款，扩展主题、界面、登录和通知设置。提升应用和后台速度，修复支付、迁移及归档投递。

<a id="изменения-1"></a>

### 变更

* 新增 Wata 循环支付，由提供商排期；包含独立付款方式、订阅条款快照、重复扣款、替换和终止处理。 ([05ae2e3f](https://github.com/3252a8/remnawave-minishop/commit/05ae2e3f426800d33f6c57ff4f70e9cb5533812c))
* 扩展主题系统：控制首页八个元素可见性、自定义元数据分隔符、邀请奖励列表模式及安全 SVG 导入。主题描述文件写入防止并发冲突。 ([8f555750](https://github.com/3252a8/remnawave-minishop/commit/8f5557506de881fe34f90ca9d802cc9945431ba6), [8793057b](https://github.com/3252a8/remnawave-minishop/commit/8793057bdbe4efdd3cd89effdddceb771000b367), [834d63d5](https://github.com/3252a8/remnawave-minishop/commit/834d63d5030913d19789f3ae082b0cfc297655bb), [c7c03157](https://github.com/3252a8/remnawave-minishop/commit/c7c0315773913a4d0b12e05982802a37eb6b96a3), [408171a9](https://github.com/3252a8/remnawave-minishop/commit/408171a901f87a63188549fcc1f0ceeeece4d30a))
* 扩展登录与试用设置：可为每个提供商单独建议绑定；试用激活可要求绑定 Telegram 或外部 OAuth 身份，现在任一提供商均可满足，不再只限 Telegram。 ([08110e21](https://github.com/3252a8/remnawave-minishop/commit/08110e219335b1ea50e9ecfff1894088388869f5), [73be790c](https://github.com/3252a8/remnawave-minishop/commit/73be790cc368079acaf857f789fd3fe2fcdd0ff2))
* 新增结算套餐参数体验设置：可关闭数字动画，可进入结算时直接打开参数编辑器。 ([5d5d6a71](https://github.com/3252a8/remnawave-minishop/commit/5d5d6a711b29747dd3752bd706efc0ca817f974f))
* 扩展自定义按钮和群发：分别控制 Telegram 机器人菜单、Mini App 和浏览器可见性，群发按钮链接支持按收件人个性化。 ([51e2200d](https://github.com/3252a8/remnawave-minishop/commit/51e2200d8d2734a5df701f8ddbfda6c2b1357736), [7ab91e92](https://github.com/3252a8/remnawave-minishop/commit/7ab91e924513b15143ae8301d86d9aae6bb763bc))
* 新增用户通知偏好访问控制，及管理员新工单／回复 Telegram 与日志通知独立开关。 ([d059cb4c](https://github.com/3252a8/remnawave-minishop/commit/d059cb4ca60442f48bd5ecd53fc67cc7940cabae), [87b72e8f](https://github.com/3252a8/remnawave-minishop/commit/87b72e8fd78278c198551be479c091b1561f1905))
* 加速应用与后台：批量读取权益和套餐、限制后台同步事务范围、版本化缓存、合并并行请求及缓存翻译与设置。 ([d692f179](https://github.com/3252a8/remnawave-minishop/commit/d692f17966037655d1ba58a606fff8f8bd61c529), [82c757e9](https://github.com/3252a8/remnawave-minishop/commit/82c757e984732d7823bcf5d9198059cccf6d3465), [82c17b17](https://github.com/3252a8/remnawave-minishop/commit/82c17b1769d33ddafa0943063cf7c210225f55a1))
* 支持通过自建 Telegram Local Bot API 投递大型归档，后端和 worker 共用配置。 ([13c0118f](https://github.com/3252a8/remnawave-minishop/commit/13c0118f810a51db55ff6e8b257b6442041ab66c))
* 修复支付：RollyPay 接受没有流量元数据的付款，使用缩短回调标识；Telegram 发票保留私有套餐流程；退款正确撤销关联流量充值。 ([c00b4bbf](https://github.com/3252a8/remnawave-minishop/commit/c00b4bbffdb20273e2584960a8dd8927c42a7eac), [065e302e](https://github.com/3252a8/remnawave-minishop/commit/065e302e825ee9828ceaff023236b3c5b7f28aff), [8e376168](https://github.com/3252a8/remnawave-minishop/commit/8e3761689cc45667b52071a7b3feba757e67a62e), [c201881a](https://github.com/3252a8/remnawave-minishop/commit/c201881aef43eb18341f9b59caf35656a5ba7e8c))
* 修复 Mini App 和后台：ping 历史不计缓存检查；紧凑卡片显示流量重置日期；结算不残留旧礼品横幅；纯邮箱账号隐藏不可用操作；重置用户会结束当前试用。头像刷新及关联客户跳转即时生效。 ([9aa04ef9](https://github.com/3252a8/remnawave-minishop/commit/9aa04ef9eb8d5e0812f7c41c6958728f4d74883e), [b31602c7](https://github.com/3252a8/remnawave-minishop/commit/b31602c7b9a5fe0834398a149b7b04fdcdf58ce1), [9dbadf53](https://github.com/3252a8/remnawave-minishop/commit/9dbadf533f30a459c94a837a1cf33a9832b36581), [0e2dbf5a](https://github.com/3252a8/remnawave-minishop/commit/0e2dbf5a7d0d4ee6a8cd3ad81d1a8849f786aa1b), [36912875](https://github.com/3252a8/remnawave-minishop/commit/3691287568ff227cdc84dc564ae34e83623aab6f), [5d88dd32](https://github.com/3252a8/remnawave-minishop/commit/5d88dd321d1e7ac718329c1adfc87a177505b3a2), [35fd9ad5](https://github.com/3252a8/remnawave-minishop/commit/35fd9ad546cde195b48434847fdb86113f245328))
* 加固安装器和旧数据迁移：向导输入与 Compose 隔离，预检和切换更安全；规范化 Bedolaga 面板 URL，迁移后保留并验证订阅链接。 ([faf06604](https://github.com/3252a8/remnawave-minishop/commit/faf06604c35c1d5fec46fb25cc9a770dab92341b), [227399d2](https://github.com/3252a8/remnawave-minishop/commit/227399d2e135d577a38113b84eec0aea8bc03739), [f7f437e5](https://github.com/3252a8/remnawave-minishop/commit/f7f437e5bafccff48e90133e93f12616aea9b604), [39c4c11a](https://github.com/3252a8/remnawave-minishop/commit/39c4c11acf67fca7fe2a66908cba05926c43b5f8))
* 更新核心发布：新增 GHCR 镜像渠道，临时发布／开发环境故障支持重试；加强依赖与安全流程，更新网页／文档依赖。 ([7784bf60](https://github.com/3252a8/remnawave-minishop/commit/7784bf60848cdfad4866d91629ba55ac8dfa38a6), [cb2ecdec](https://github.com/3252a8/remnawave-minishop/commit/cb2ecdec742deb13f297ce0f13e92e581cdd25f3), [74739e1b](https://github.com/3252a8/remnawave-minishop/commit/74739e1be249ce21026a148d89b614e03a01cded), [4a9f6606](https://github.com/3252a8/remnawave-minishop/commit/4a9f6606cf5c9eb44713fe8848564d8561c9d109))

<a id="при-обновлении-3"></a>

### 升级注意

* 新增迁移 `0087_add_wata_subscriptions`，创建 Wata 循环订阅状态表。
* Wata 循环付款要求终端侧开通订阅并启用 `WATA_SUBSCRIPTION_ENABLED`。
* 大型 Telegram 归档可配置 `TELEGRAM_BOT_API_BASE_URL`；自建 Bot API 须独立运行，并可从后端和 worker 访问。
* 新增 `*_LOGIN_RECOMMENDED`、`USER_NOTIFICATION_PREFERENCES_ENABLED`、`SUPPORT_ADMIN_TELEGRAM_NOTIFICATIONS_ENABLED` 和结算展示参数。旧 `TRIAL_WITHOUT_TELEGRAM_ENABLED` 保留为 `TRIAL_WITHOUT_OAUTH_ENABLED` 的废弃别名。
* 依赖更新由 `dependabot[bot]` 提供：[dfc8642c](https://github.com/3252a8/remnawave-minishop/commit/dfc8642ce9038a123fdfb8a93b07b3ca7b7e9fc5)、[b98b6096](https://github.com/3252a8/remnawave-minishop/commit/b98b6096741c8988e698b6ec018003f2e43693ad)、[98f80543](https://github.com/3252a8/remnawave-minishop/commit/98f8054327779664fb5549b448b626a63f09fdbb)。

## v3.7.1 — 2026-09-14

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.7.1) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.7.1)

<a id="обзор-3"></a>

### 概览

扩展 WebApp 主题设置菜单，新增 Bedolaga 迁移、隐藏套餐购买链接和 Discord 登录。认证 Remnawave Panel 3.4.4，改进后台操作及支付稳定性。

<a id="изменения-2"></a>

### 变更

* 扩展 WebApp 外观库和主题运行时：主题选择、自定义 CSS 变量及变体设置、透明度、通用颜色编辑器、包导出、预览保存和详细导入诊断。 ([f84f658](https://gitlab.com/3252a8/remnawave-minishop/-/commit/f84f658b9b0836476c4e4e484d11162f1425d492), [245e80a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/245e80a203d1da104c561f80f1314fac4a2346cb))
* 新增安全 Bedolaga 导入：账号、套餐、订阅、财务历史、礼品、支持工单、广告及伙伴数据；支持演练、结果核对、备份及受控环境切换。 ([9c4e5f4](https://gitlab.com/3252a8/remnawave-minishop/-/commit/9c4e5f48402980daf8adb834fae01466c8c0ed38))
* 扩展 Remnashop 导入：纯邮箱账号、OAuth 身份、用户余额、分组与个人覆盖设置、流量激活码、广告链接及额外财务核查。 ([d16bf91](https://gitlab.com/3252a8/remnawave-minishop/-/commit/d16bf912bf53bf23c7346c29a7c99aa54ba3c6bc))
* 隐藏套餐支持私有链接；管理员可创建、撤销或重建唯一链接，无需在公共目录发布套餐。 ([5367bb4](https://gitlab.com/3252a8/remnawave-minishop/-/commit/5367bb4b290b3d5d2694c6cad455e2ffed9dad3e))
* 激活、续期和更换订阅时同步用户套餐标签到 Remnawave Panel；后台核对已有用户，保留手动分配标签。 ([31f8735](https://gitlab.com/3252a8/remnawave-minishop/-/commit/31f87357787aadb528cc35c0379289ce5ad11318))
* 新增 Discord OAuth2 登录与绑定；邮箱验证码完整输入后自动验证。 ([89d0289](https://gitlab.com/3252a8/remnawave-minishop/-/commit/89d028944a10d6c7df8ca92e2614ca57e4b97c0b), [08b179c](https://gitlab.com/3252a8/remnawave-minishop/-/commit/08b179c4e162309b410eb5b7ea9c24c824f78ff7))
* Minishop 用户卡片可直接打开对应 Remnawave Panel 用户。 ([9481486](https://gitlab.com/3252a8/remnawave-minishop/-/commit/94814866d2fdfb7edfb34dd08df52d435361d3ee))
* 认证 Remnawave Panel 3.4.4 兼容性，包含用户标签和从 2.8.1 升级场景。 ([203d6ea](https://gitlab.com/3252a8/remnawave-minishop/-/commit/203d6ea26c751a9bb3d65e41d8140f4df2ea35f5))
* 修复后台：保留所选工单状态，付款详情打开正确用户卡片，停用周期不再回到套餐编辑器。 ([e0c8c42](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e0c8c422320f2c7eb77b3e407f57f9853d1e2096), [b42b377](https://gitlab.com/3252a8/remnawave-minishop/-/commit/b42b3776b9df2d571d3ee41ea98f65e0f961010c), [e726d56](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e726d562eb52daeed5ca4cdc72b832b6719dd7eb))
* 修复本地配置初始化前的 RollyPay 元数据加载；确认对话框已有取消操作时，去除重复关闭按钮。 ([0641d2f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/0641d2fcd351645ce94e79187d1336501374a67b), [595fd5d](https://gitlab.com/3252a8/remnawave-minishop/-/commit/595fd5dcce6f2f07e7fcdcae47ba46324d11024a))

<a id="при-обновлении-4"></a>

### 升级注意

* 新增环境变量 `DISCORD_OIDC_ENABLED`、`DISCORD_OIDC_CLIENT_ID` 和 `DISCORD_OIDC_CLIENT_SECRET`。
* 追加数据库迁移 `0086_panel_tariff_tag`，不修改已有迁移。
* Node.js 最低版本提高至 24。 ([7dd95fb](https://gitlab.com/3252a8/remnawave-minishop/-/commit/7dd95fbfea89af0965f1465ad44be5a4d11017d0))
* GitLab 成为主要源码托管；发布 dev 镜像后，流水线可触发下游使用方构建。 ([93c82c4](https://gitlab.com/3252a8/remnawave-minishop/-/commit/93c82c41ac51f161bce38262387a2e8377cb99ec), [3c53718](https://gitlab.com/3252a8/remnawave-minishop/-/commit/3c5371898e1e69237c4087f83c718e84b2e5842b))
* 更新 OpenAPI、API 类型、事件目录和设置清单。
* 外观库及 Node.js 24 迁移贡献者：[BADtochka](https://gitlab.com/BADtochka)。

## v3.7.0 — 2026-09-09

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.7.0) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.7.0)

<a id="обзор-4"></a>

### 概览

新增用户余额、礼品订阅、Google／Yandex／通行密钥登录，改进后台自定义应用主题安装。扩展套餐、支付、通知和用户管理工具。

<a id="изменения-3"></a>

### 变更

- **用户个人余额：** 支持提供商充值，全部或部分支付订阅、续期、流量和设备，差额使用外部方式支付。后台提供余额、流水、金额调整及个人／伙伴余额互转，同时保留提现限制。 ([d27a105d](https://gitlab.com/3252a8/remnawave-minishop/-/commit/d27a105d85dc30e168b945177816ac8ebc662dca), [b5593216](https://gitlab.com/3252a8/remnawave-minishop/-/commit/b5593216dff2e2234beca6ade0e20d36a6b568f5))
- **礼品订阅：** 为他人购买，通过链接转赠或邮件交付，激活时起算有效期。已付套餐、时长和上限不受后续目录变化影响。管理员可免费创建、查看历史，撤销未激活的已付礼品，并将实付金额退至购买者个人余额。 ([0a0d9ce4](https://gitlab.com/3252a8/remnawave-minishop/-/commit/0a0d9ce4401f9b7283d3308c0e75bf1ed19738cd), [2634d527](https://gitlab.com/3252a8/remnawave-minishop/-/commit/2634d52743e519de040838e4798fd945f9dd4438), [8a605b4f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/8a605b4febd3bd848ef8286d2eb6cff1e6f2a9d1))
- **扩展登录与安全：** Google、Yandex ID、通行密钥、多种登录方式绑定、通知已验证邮箱选择，以及同时确认新旧邮箱的主邮箱变更。没有绑定邮箱也可重发订阅链接，新链接保留在应用，并尽可能通过邮件或 Telegram 发送。 ([3c626bc4](https://gitlab.com/3252a8/remnawave-minishop/-/commit/3c626bc42b52efdac620b9c5de917e0687823024), [6072ee38](https://gitlab.com/3252a8/remnawave-minishop/-/commit/6072ee384e98a25420c97dbaa77e955445debdab), [3b1067b9](https://gitlab.com/3252a8/remnawave-minishop/-/commit/3b1067b9c694b2632a8be6b90ddb618b920f3597))
- **扩展套餐与试用配置：** 新购买支持精确天数；可由后台分配隐藏套餐，并允许所有者续期。新增付费试用及转付费策略：保留剩余试用天数，或从付款时重新起算。 ([aad14cb4](https://gitlab.com/3252a8/remnawave-minishop/-/commit/aad14cb42652d8f2ef79fe973e2fcf6c6f83c69d), [a666d271](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a666d271cdd970a40accc8dd9fcc6769bc2ed100), [91de1b61](https://gitlab.com/3252a8/remnawave-minishop/-/commit/91de1b612b79c6b32e0942c442d5be5cea8ff89f), [aded3a6a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/aded3a6a520420e252cb32dab4c7bf5c84095150))
- **RollyPay、OxaPay 及新购买流程：** 公开套餐购买链接可在登录后继续；支持取消未完成付款并释放激活码，可配置支付按钮顺序。后台可手工确认付款或撤销已记录权益，保存操作日志并检查安全回滚条件。 ([b3a0b61a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/b3a0b61a5ac29165ad54ff9f6fe9ee5ea90184be), [2ba558dd](https://gitlab.com/3252a8/remnawave-minishop/-/commit/2ba558dd21fe2bea10ed44e6eb33dd474e0f9969), [957a1255](https://gitlab.com/3252a8/remnawave-minishop/-/commit/957a1255f13f2fb38392709f0bc5d63e106ef7ba), [ea20ed68](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ea20ed686b1438308f97c9235ce7ffa6592444d9), [51f34dcb](https://gitlab.com/3252a8/remnawave-minishop/-/commit/51f34dcb8f88b5ee1cb0ea11cc28bd8efcc7e358), [abd93f8f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/abd93f8f19f4d80f61579bd751c5dc340a70586d))
- **主题库及界面配置扩展：** 从 ZIP 或公开 GitHub／GitLab 仓库安装主题，支持预览、保留设置更新、回滚和导出自有副本。提供浅色和深色设置。
- 机器人菜单与应用支持可本地化自定义按钮，例如频道链接，可选择图标、链接、顺序和显示位置。 ([ea2d84dc](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ea2d84dcea5f30c8fc82ad9bb55f882670e0ed29), [fc62f743](https://gitlab.com/3252a8/remnawave-minishop/-/commit/fc62f7435f2415bf40893d568f1f3a11fc59e821), [7ebdb48a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/7ebdb48a0adb74692fbfd99aaab7dd292f5d6646), [bd16c908](https://gitlab.com/3252a8/remnawave-minishop/-/commit/bd16c90876f8808e1777f12c1d132f203fa97415), [1e276ca9](https://gitlab.com/3252a8/remnawave-minishop/-/commit/1e276ca9b606c57942b77aabf8e6fb31c30b3a9c))
- **个人中心更新：** 可选紧凑订阅、流量和余额汇总，包含额度重置日期，适合开启较多功能的页面；服务器状态支持 Uptime Kuma、xray-checker 或外部页面，首页卡片可独立配置。设备列表显示客户端名称和最后活跃时间。 ([5b5be71c](https://gitlab.com/3252a8/remnawave-minishop/-/commit/5b5be71c90fb25f7edeae10ed3ea2372e7929fe5), [f5a010d5](https://gitlab.com/3252a8/remnawave-minishop/-/commit/f5a010d53a4a3612528f7c22ac570abfa3b7e10b), [d99101aa](https://gitlab.com/3252a8/remnawave-minishop/-/commit/d99101aa1f4fed71206897e7d3fc5f0f42d58902), [98cf37be](https://gitlab.com/3252a8/remnawave-minishop/-/commit/98cf37beaeb11c31e36f5a70e1fe5967e59f4813), [b9326281](https://gitlab.com/3252a8/remnawave-minishop/-/commit/b93262816643957836130c197ed246a375bf8e4b), [360337b6](https://gitlab.com/3252a8/remnawave-minishop/-/commit/360337b6e1b71391dda531e9d097de2232dac7ae))
- **通知管理：** 管理员按类别选择 Telegram／邮件渠道，用户按渠道独立控制系统及营销消息。邮件提供无需登录的通知管理链接，可退订群发。新增设备接入、设备上限通知，群发考虑已屏蔽机器人的用户。 ([a02c9bc9](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a02c9bc9b8f26901ce3c2aaece2db01d83d35195), [7c932561](https://gitlab.com/3252a8/remnawave-minishop/-/commit/7c932561f07189d56f4d6ed7468d0063d1347089), [6fac76da](https://gitlab.com/3252a8/remnawave-minishop/-/commit/6fac76da4a3c2e514602ab8b08a036ec90ca07f5), [72bf7663](https://gitlab.com/3252a8/remnawave-minishop/-/commit/72bf76637f19e7414c3dc97714962d8112912895))
- **扩展消息、群发与支持：** 工单、回复、内部备注及管理员私信支持图片；更新会话展示、工单状态和群发详细历史。没有 Telegram 的用户可接收邮件私信，发送历史保留在用户卡片。 ([0ca7680d](https://gitlab.com/3252a8/remnawave-minishop/-/commit/0ca7680de4005e3dfccdf04aaac019f093238101), [3df7d9ae](https://gitlab.com/3252a8/remnawave-minishop/-/commit/3df7d9aeb4801e3ecd1b9cc2353ff120e432159e), [a4c4c0e0](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a4c4c0e06c2e3df29ee36339e5c498ec6b779b40), [995ab888](https://gitlab.com/3252a8/remnawave-minishop/-/commit/995ab8889eec21a7475bc0d67c65cfda140a4f32), [3592c727](https://gitlab.com/3252a8/remnawave-minishop/-/commit/3592c72753c89042a6956594f198d5ac331bf06a))
- **后台改进：** 统一表格与移动卡片，按用户搜索付款、展示购买明细、一键复制标识。用户卡片显示设备占用；有效期可增加、减少或指定日期。扩展用户操作和付款日志，保留审计历史。 ([03b2a770](https://gitlab.com/3252a8/remnawave-minishop/-/commit/03b2a7708b07cbdf9a50f7275d852deeadae3bfb), [cc7c06b8](https://gitlab.com/3252a8/remnawave-minishop/-/commit/cc7c06b8cdf7ed0a803ac6580b91c04c1e602f25), [ccb5f109](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ccb5f109a235fa1ddbb50f9defef7c978dd728d3), [766ec398](https://gitlab.com/3252a8/remnawave-minishop/-/commit/766ec3980852f05d0cca17052b55df31eea26c2b), [95ef32c5](https://gitlab.com/3252a8/remnawave-minishop/-/commit/95ef32c5d22c54d1254d68c2ad0b213036de93d6), [bd17f2d5](https://gitlab.com/3252a8/remnawave-minishop/-/commit/bd17f2d5964d999c8b290bd93e6f34a58af0bd0e), [a8f09d17](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a8f09d175abd12ee5490dd79f620437c18c4414e))
- **修复支付与同步：** FreeKassa 回调、Platega／Pally 金额币种校验和购买时激活码输入重置。套餐分组及上限变化应用到有效订阅，面板用户同步保持事务完整。 ([e7d4d02a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e7d4d02a81c2f64c67e0346a28852a30d3b49ce5), [e95f269a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e95f269ac515daa6e42ca1553ad8c5c858bddfc5), [1c20764a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/1c20764a6ea50d5c4fe90a1d527ead1f72701f96), [595ffb34](https://gitlab.com/3252a8/remnawave-minishop/-/commit/595ffb342b5fdf510ac4dd27f8084f58208e04d8), [5475e944](https://gitlab.com/3252a8/remnawave-minishop/-/commit/5475e9443642a917bd98c350332140053bc20c01), [18a3fad7](https://gitlab.com/3252a8/remnawave-minishop/-/commit/18a3fad72e6910fb6038c8d96ef4fc3a0c33114d), [c8841771](https://gitlab.com/3252a8/remnawave-minishop/-/commit/c88417713563a0b6ffb428a1d4062e0231a98674))
- **备份恢复更新：** 归档包含应用版本及迁移历史；恢复到独立空库，补齐迁移后切换，保留原库。自定义主题与主题库设置纳入备份。 ([bb15f564](https://gitlab.com/3252a8/remnawave-minishop/-/commit/bb15f56408748ac07c9dd15c9e1238e7fce884aa), [ea2d84dc](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ea2d84dcea5f30c8fc82ad9bb55f882670e0ed29))

<a id="при-обновлении-5"></a>

### 升级注意

- **套餐与数据库升级。** 为新登录方式、余额、礼品、按天周期、通知和审计追加迁移，不修改已有迁移。升级前备份数据库和套餐目录，暂停新付款，协调更新后端、worker 和前端。旧账单与外部循环订阅保留日历条款。新按天订单不使用当前 Tribute、Platega 快速支付系统和 RollyPay 外部订阅适配器，改用可用单次付款。产生按天订单后，回滚版本必须理解新字段与购买快照。 ([aad14cb4](https://gitlab.com/3252a8/remnawave-minishop/-/commit/aad14cb42652d8f2ef79fe973e2fcf6c6f83c69d))
- **新增设置。** 个人余额（`USER_BALANCE_ENABLED`）、Google／Yandex／通行密钥和服务器状态（`SERVER_STATUS_ENABLED`）须单独启用，默认关闭。付费试用使用 `TRIAL_PAYMENT_ENABLED`、`TRIAL_PAYMENT_PRICE`、`TRIAL_PAYMENT_STARS_PRICE`；转付费有效期策略使用 `TRIAL_DAYS_STRATEGY`。礼品购买由 `GIFTS_ENABLED` 控制，默认开启。迁移启用四个用户通知开关，管理员全局限制仍生效。
- **主题。** `WEBAPP_THEMES_DIR` 应位于持久卷，后端须有写权限。已手工安装主题继续支持；导入时单独转入主题库管理。 ([ea2d84dc](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ea2d84dcea5f30c8fc82ad9bb55f882670e0ed29), [bf362688](https://gitlab.com/3252a8/remnawave-minishop/-/commit/bf3626887cf4f65a9bc952d14cc626a29bbf3beb))
- **数据库恢复。** 用目标版本维护命令 `bash scripts/restore-backup.sh <归档.zip>` 替代运行中的 HTTP 恢复。命令停止后端／worker，需要 `CREATEDB` 权限及两份数据库空间。后台保留归档创建、上传、下载及 Compose 目录单独恢复。 ([bb15f564](https://gitlab.com/3252a8/remnawave-minishop/-/commit/bb15f56408748ac07c9dd15c9e1238e7fce884aa))
- **交付与文档。** 镜像发布移到 GitLab CI，主要仓库为 Docker Hub；安装器优先 GitLab，并支持替代来源。文档增加稳定版／dev 切换，以及统一的登录、支付和新功能指南。 ([13e49987](https://gitlab.com/3252a8/remnawave-minishop/-/commit/13e499872134b7c2dd9191f3073bceaed7343ef4), [2f2a10d0](https://gitlab.com/3252a8/remnawave-minishop/-/commit/2f2a10d0236dc8c0abcc66647cfc8255a501dfaf), [e8566271](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e8566271d022233c62f80731195944f7c3cd8b0d), [246f8780](https://gitlab.com/3252a8/remnawave-minishop/-/commit/246f8780d467f5fbbac83f9345934d23589353a8), [d88e3215](https://gitlab.com/3252a8/remnawave-minishop/-/commit/d88e32154e0cbf40b6ec594aa905f7246231ad50), [8ea3b18f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/8ea3b18fb4b62823ce8767a8a2290526ce5b230b))
- **贡献者：** 感谢 **BADtochka** 实现服务器状态、安装器替代来源及礼品退款；感谢 **BAD.** 参与礼品订阅实现。 ([d99101aa](https://gitlab.com/3252a8/remnawave-minishop/-/commit/d99101aa1f4fed71206897e7d3fc5f0f42d58902), [246f8780](https://gitlab.com/3252a8/remnawave-minishop/-/commit/246f8780d467f5fbbac83f9345934d23589353a8), [8a605b4f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/8a605b4febd3bd848ef8286d2eb6cff1e6f2a9d1), [2fc89ecb](https://gitlab.com/3252a8/remnawave-minishop/-/commit/2fc89ecb1e0641fa7b7532ddd39cf9c1e3c7a8fc), [f2f1c0c7](https://gitlab.com/3252a8/remnawave-minishop/-/commit/f2f1c0c795c5e7f286d1e855aaed4ed083575532))

## v3.6.1 — 2026-08-18

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.6.1) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.6.1)

<a id="обзор-5"></a>

### 概览

新增订阅灵活结算、新支付方式选择和群发历史。改进付款恢复及界面体验。

<a id="изменения-4"></a>

### 变更

- 按周期套餐结算前可选择普通／高级流量最终上限和额外设备；本地预览价格，服务端为整个购物车报价。
- 重做套餐编辑器界面，支持配置灵活上限。
- 可选择支付菜单外观：默认紧凑下拉列表，或原来的独立按钮；保留顺序与图标，为不可用方法展示已配置最低金额。
- Platega 支持配置独立银行卡付款按钮。
- 加强付款与自动续期恢复：调用提供商前保存周期和发送意图，重启继续已有付款；激活或释放结算前核查外部账单状态。
- 新增群发历史：内容、受众、渠道、排期、状态和进度；计划任务可改期或取消。
- 改进 Mini App：考虑 Telegram 全屏安全区和浮层；可发送伙伴页面入口按钮；激活码区域置顶；其他计划启用时将伙伴入口移到设置。
- 改进后台：修复广告活动注册与付款人数指标，图表增加动画并改进图例。
- 修复 Remnawave 订阅关联：同一 Telegram ID 对应多个面板用户时使用已保存本地关系，不把合成标记当作真实身份。
- 提高运行时设置韧性：单个提供商配置错误不再阻止其他设置应用。
- 更新文档与构建：增加可独立安装的 PRO 扩展概览，自动生成 README 界面截图，并检查 npm lock 一致性。

<a id="при-обновлении-6"></a>

### 升级注意

- 追加迁移 `0062`–`0065`：群发历史、旧用户代码核对、结算快照及灵活上限。已有迁移不修改、不重排。
- Mini App 默认采用支付方式下拉列表，使用 `PAYMENT_METHODS_DISPLAY_MODE=buttons` 可恢复原按钮布局。
- 新增可选设置 `PAYMENT_METHODS_DISPLAY_MODE`、`PLATEGA_CARD_ENABLED` 和 `PLATEGA_CARD_METHOD`，没有新增必填环境变量。

<details>
<summary>变更来源与贡献者</summary>

* feat: flexible checkout, payment recovery and broadcast history by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/82


**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.6.0...v3.6.1

</details>

## v3.6.0 — 2026-08-12

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.6.0) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.6.0)

<a id="обзор-6"></a>

### 概览

新增合作伙伴计划，认证 Remnawave 3.x 兼容性，扩展付款流程并加强安装、鉴权和数据恢复可靠性。

<a id="изменения-5"></a>

### 变更

- 新增可配置合作伙伴计划：申请审核、独立链接、客户归因、冻结期佣金、按币种余额、人工提现及用户页面。
- 支持伙伴余额全额或混合付款，包含资金预留、取消补偿、重试处理及正确外部收入核算。
- 支持 Remnawave API 3.0–3.2.3：数字用户 ID、从 2.8.1 安全升级、自适应 API 能力、批量操作及后台兼容性指示。
- 扩展 Platega：更多付款方式和快速支付系统循环订阅，单独记录授权、续期、取消与重复回调。
- 改进付款：复用待结算、遵守提供商最低金额、安全取消旧账单、托管结算可靠重试及创建前检查 FreeKassa 就绪。
- 扩展套餐和高级流量：独立重置策略、按订阅起点正确计算滚动周期、结转加购余量，明确区分零额度与不限量。
- 扩展激活码和邀请：机器人续期可用个人码，增加普通／高级流量，新用户可选套餐，控制链接可见性并在群发中搜索代码。
- 改进应用与后台：表格排序、收入图表新范围及状态、自适应设备卡片、更好的空／加载状态、手机布局、对比度和附加主题覆盖。
- 改进鉴权与 Telegram：Bot API／OAuth 支持 SOCKS5 代理、限制网络等待、缓存 JWKS，账号合并正确迁移支持历史。
- 加强运维安全：恢复前归档、原子数据库恢复、自动迁移及序列校正，诊断 `/app/data` 挂载不一致，恢复和同步使用独立锁。
- 安装向导增加 Docker 最低版本检查、安全更新 Compose 插件、启动前配置验证，以及验证 TLS 证书的 eGames 后远程面板支持。
- 改进部分界面区域和元素。

<a id="при-обновлении-7"></a>

### 升级注意

- 追加迁移 `0057`–`0061`：Platega 订阅、伙伴计划、客户流量奖励及伙伴余额付款。不修改或重排已有 `0056`。
- 伙伴计划需要 `PARTNER_REQUISITES_ENCRYPTION_KEY` 和 `PARTNER_REQUISITES_KEY_ID`，默认关闭。
- 新增 `TELEGRAM_BOT_PROXY_URL` 和 `TELEGRAM_OAUTH_USE_BOT_PROXY`。
- 安装器最低要求：Docker Engine 25.0+、Docker Compose 插件 2.20.2+；不再支持独立 `docker-compose` 命令作为运行时。
- 更新 OpenAPI、前端类型、事件目录及设置清单。
- 贡献者：`wormy09`（`5eb78c87`）实现合并账号时迁移支持历史；`dependabot[bot]`（`632603f9`）更新前端依赖。

<details>
<summary>变更来源与贡献者</summary>

* fix: reassign support history when merging accounts by @wormy09 in https://github.com/3252a8/remnawave-minishop/pull/75
* build(deps): bump the npm_and_yarn group across 2 directories with 1 update by @dependabot[bot] in https://github.com/3252a8/remnawave-minishop/pull/78
* feat: partner program, Remnawave 3.x and expanded payments by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/81


**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.5.8...v3.6.0

</details>

## v3.5.8 — 2026-07-31

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.5.8) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.5.8)

<a id="обзор-7"></a>

### 概览

新增 Tribute 支付、安全 YooKassa 自动续期重试、未完成付款核查与恢复、HWID 包月度流量奖励、高级额度快速执行及断开会话。界面增加群发／支持／用户卡片的带按钮消息编辑器，后台导航可扩展。

<a id="изменения-6"></a>

### 变更

- 新增 **Tribute**：主要使用 Shop API，按本地金额动态创建订单（单次、循环、普通／高级流量、HWID 设备、套餐升级差价）；备用 Creator 订阅与 Digital Products；共用 `/webhook/tribute` 并验证 HMAC-SHA256；套餐编辑器可“从 Tribute 获取”并核对价格币种；提供标志及设置页。
- YooKassa 自动续期安全重试：周期队列固定金额、银行卡和请求体；技术重放仅在 30 分钟内使用同一 `Idempotence-Key`，确认 `canceled` 后最多一次资金尝试，默认演练；备用排期器无需面板 webhook，新增 `subscription.auto_renew_failed` 和重试通知；修复循环付款收据字段。
- 新增付款核查与恢复：Mini App 展示未完成付款并沿已保存链接继续；优先交付未完成付款，结算填入之前代码；worker 核查 Wata、CryptoPay、Stripe、LAVA、Pally、PayKilla 和 SeverPay 过期订单，含没有已保存链接的订单。
- HWID 包新增月度流量奖励（每包 `traffic_bonus_gb`），保存于付款和加购记录，按有效加购叠加，按 `valid_from`／`valid_until` 生效，跨面板月度重置保留；新增全量订阅基础流量上限一次性重算脚本。
- 恢复按套餐判断的设备加购：机器人和网页共用可用性服务，精确说明阻止原因（功能关闭、无有效订阅、套餐缺失／停用／变化、不限量、没有包），创建账单前再次检查，并诊断已付流量加购未到账原因。
- 改进高级额度执行：在完整 worker 周期间，快速复查用量达到 `TARIFF_PREMIUM_FAST_WATCH_PERCENT` 的订阅；通过 `POST /api/ip-control/drop-connections` 断开高级节点既有会话并设冷却；防范不完整节点统计，后台提示缺少 `CAP_NET_ADMIN` 的节点。
- 新增面板冲突诊断：第三方覆盖设备／流量上限时暂停订阅同步并显示健康面板；保存面板 webhook 载荷快照、按内容去重事件、拒绝无效 API 响应，正确将 `LIMITED` 视为有效订阅。
- 扩展消息：群发、支持、插件共用消息契约；各语言分别定义正文与按钮，最多四个按钮，支持链接、机器人激活码、Mini App 激活码、任意 Mini App 目标和命名页面。新增选择套餐／周期的结算路由；群发受众分组并配图标，可选具体套餐及扩展受众；用户卡片可直接发送私信。
- 支持和群发改用可视化编辑器：Telegram 支持的 HTML 子集格式，旧消息可点击链接，按可见文本计数；管理员可切换 HTML 源码、插入个性化短代码和用户专属链接，并为回复添加按钮；侧栏显示等待工单。
- 扩展并改进后台：扩展可添加导航组、现有区域标签页及用户卡片标签页；调整部分区域位置，显示设置值来源（数据库或 `.env`），新增安全恢复的订阅／套餐关联核对、套餐变更结果预览及卡片重置订阅链接。窄屏列表使用卡片，浮层后方只保留一个活动滚动区。
- 新增订阅链接重发：应用路由发送新链接和教程到邮箱，设置提供确认对话框与按钮，管理员也可在用户卡片重置。
- 区分个人和通用激活码：可选所有者，列表分组通用代码并标记一次性代码；消息按钮下拉区分两类，历史向客户显示代码最初为谁签发。
- 改进 Mini App 和 API：页面按需加载，模块构建拆包；所有 `/api/` 响应标记 `no-store`，避免 Telegram WebView 使用旧数据；首次加载和后台深链接保留导航。
- 修复计费与订阅：付款时冻结升级差价计算，核对面板实际权益，保留演练激活状态及续期起始日期，付费激活移除试用分组，变更套餐同步设备上限；Stars 仅在 Telegram Mini App 使用；激活码价格按所选提供商格式显示，更新 torrent 限制 worker 设置。
- 更新安装器与运维：单独验证 Remnawave 集成（安全请求 `/system/stats`、检查 `PANEL_API_COOKIE` 格式、跳过而非使用 `change_me`）；等待上游代理就绪，Caddy 日志过滤 webhook 密钥；备份保存并恢复套餐目录。单个提供商环境变量错误不再阻止全部已保存设置，面板列出 `not_applied`。
- 新增试用设备上限配置；更新 astro、js-yaml、brace-expansion，所有质量门禁固定 ruff，CI 通知已配置镜像使用方。
- 修复已有套餐用户的高级分组发放：仅配置 `premium_squad_uuids`，未配置 `premium_monthly_gb` 或额外流量包时也正确处理。

<a id="при-обновлении-8"></a>

### 升级注意

- **数据库迁移 0046–0056**（只追加，不改已有迁移）：循环付款归因、HWID 流量奖励快照、激活码所有者、工单富文本、Tribute webhook 状态、套餐升级报价快照、面板权益快照、有效订阅起点恢复、结算生命周期、自动续期重试状态和套餐关联审计。
- **新增环境变量**（`.env.example`）：`AUTO_RENEW_RETRY_ENABLED`、`AUTO_RENEW_RETRY_DRY_RUN`、`AUTO_RENEW_SCHEDULER_ENABLED`、`AUTO_RENEW_MAX_FINANCIAL_ATTEMPTS`、`AUTO_RENEW_MAX_TRANSPORT_REPLAYS`、`AUTO_RENEW_WORKER_TICK_SECONDS`、`AUTO_RENEW_WORKER_BATCH_SIZE`、`AUTO_RENEW_RETRY_GRACE_HOURS`、`AUTO_RENEW_SCHEDULER_LEAD_HOURS`。分阶段启用：先设 `AUTO_RENEW_RETRY_ENABLED=True`，保留 `AUTO_RENEW_RETRY_DRY_RUN=True`；核查 worker 日志后再关闭演练。
- 已记录但未加入 `.env.example`：`TRIBUTE_*`（后台配置）、`TARIFF_PREMIUM_FAST_*`、`TARIFF_PREMIUM_DROP_CONNECTIONS*`、`HWID_DEVICE_TRAFFIC_BONUS_GB`（废弃回退，新奖励配置在 `tariffs[].hwid_device_packages`）。
- 要在高级额度耗尽后断开会话，Remnawave 节点须拥有 `CAP_NET_ADMIN`（`cap_add: NET_ADMIN`），否则已有连接继续工作。
- Tribute 循环 Shop Order 在提供商侧固定价格。有有效订单关联时，不得停用、删除或重命名套餐，也不得修改 `TRIBUTE_SHOP_ID`。
- 为已有全量订阅启用 HWID 流量奖励时，须一次性运行 `backend/scripts/resync_traffic_limits.py`。
- 贡献者：@wormy09——订阅链接重发（`fc73adbf`、`04f029c9`、`66c06731`）、HWID 月度流量及重算脚本（`fab09cb8`、`24735eee`）、`LIMITED` 处理（`1ef4751b`）、加购未到账诊断（`112c4b2c`）、覆盖设置提示翻译（`c5d0d287`）、当前 ruff 适配（`240709e8`、`0439829f`）。依赖更新：@dependabot（`3a94667e`、`e619c83f`）。

<details>
<summary>变更来源与贡献者</summary>

* feat(webapp)：从 Mini App 重发订阅链接并发送邮件，作者 @wormy09：https://github.com/3252a8/remnawave-minishop/pull/63
* fix(i18n)：补齐后台流量覆盖设置的空提示，作者 @wormy09：https://github.com/3252a8/remnawave-minishop/pull/65
* build(deps): bump astro from 7.0.9 to 7.1.3 in /docs-site in the npm_and_yarn group across 1 directory by @dependabot[bot] in https://github.com/3252a8/remnawave-minishop/pull/66
* feat(devices)：为有效 HWID 设备加购每月增加流量，作者 @wormy09：https://github.com/3252a8/remnawave-minishop/pull/64
* chore(lint): satisfy current ruff on dev by @wormy09 in https://github.com/3252a8/remnawave-minishop/pull/69
* fix(sync): treat LIMITED panel status as an active subscription by @wormy09 in https://github.com/3252a8/remnawave-minishop/pull/68
* build(deps): bump astro from 7.0.9 to 7.1.4 in /docs-site in the npm_and_yarn group across 1 directory by @dependabot[bot] in https://github.com/3252a8/remnawave-minishop/pull/67
* Tribute payments, safe auto-renew recovery, checkout resume and admin messaging by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/70
* fix(tariffs): sync unrestricted squad access by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/71

**贡献者**
* @wormy09 made their first contribution in https://github.com/3252a8/remnawave-minishop/pull/63

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.5.7...v3.5.8

</details>

## v3.5.7 — 2026-07-18

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.5.7) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.5.7)

<a id="изменения-7"></a>

### 变更

- 新增可选 Torrent Blocker 报告通知，通过 Telegram 和邮件独立控制渠道，支持冷却、可选 IP 展示、本地化模板及后台设置。webhook 按类型化结构验证，忽略过期／重复事件；单渠道失败不会重复另一渠道已成功投递（感谢 @rez-code，`6d559679`）。
- 扩展后台用户筛选：今日注册、受邀请、有效／停用／到期／已付／试用／无付款订阅。仪表盘计数可打开对应列表，筛选保存在 URL。
- 改进仪表盘、日志及列表：统一卡片和骨架屏，新增日志计数及筛选清除，调整手机表格和行高。
- 修复 Wata 状态轮询：搜索改用 `/v2/transactions`，合并最终状态查询，同对象并行 GET 合并并缓存，遵循 `Retry-After`。
- 套餐新增 `legacy_keys`，重命名后已有付款和订阅仍可处理。别名唯一性验证、后台编辑及 API 契约均覆盖。
- 规范化 Telegram 菜单支持链接，自动将 `@username` 和 `t.me/username` 转为完整 HTTPS 地址。
- 修复后台集成：Redis 阻塞队列读取不再与客户端超时冲突；订阅同步区分 `last_connected_at` 更新和主要字段变化。
- 更新文档、知识图谱及新设置、筛选、套餐别名、Wata、Redis、通知投递的定向测试。

<a id="при-обновлении-9"></a>

### 升级注意

- 新增 `TORRENT_BLOCKER_NOTIFICATIONS_ENABLED`、`TORRENT_BLOCKER_TELEGRAM_NOTIFICATIONS_ENABLED`、`TORRENT_BLOCKER_EMAIL_NOTIFICATIONS_ENABLED`、`TORRENT_BLOCKER_NOTIFICATION_COOLDOWN_SECONDS` 和 `TORRENT_BLOCKER_NOTIFICATION_INCLUDE_IP`。总开关默认关闭。
- 接收事件要求 Remnawave Panel／Node 2.7+、Xray-Core 26.3.27+、已配置 Node Plugin、`NET_ADMIN`、nftables 和匹配的 `PANEL_WEBHOOK_SECRET`。
- API 契约增加 `legacy_keys`，更新 OpenAPI、前端类型和设置清单；不涉及数据库迁移。
- 贡献者：@rez-code（`6d559679`）——Torrent Blocker 通知。

<details>
<summary>变更来源与贡献者</summary>

* feat(notifications): add torrent blocker alerts by @rez-code in https://github.com/3252a8/remnawave-minishop/pull/60
* Dev by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/62

**贡献者**
* @rez-code made their first contribution in https://github.com/3252a8/remnawave-minishop/pull/60

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.5.6...v3.5.7

</details>

## v3.5.6 — 2026-07-16

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.5.6) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.5.6)

<a id="обзор-8"></a>

### 概览

扩展套餐管理，改进支持和订阅一致性，加固支付处理与 webhook 队列。

<a id="изменения-8"></a>

### 变更

- 扩展套餐管理：拖动排序决定目录顺序，重做后台套餐区域。
- 每个套餐可设置独立流量重置策略，应用于面板用户创建、激活、续期和套餐变更；旧目录继续使用全局设置。
- 改进支持：输入指示和已读状态、防止重复回复，修复手机会话滚动。
- 修复 Remnawave 订阅一致性：正确发放试用、核查已保存面板权益、变更套餐替换受管理分组、重新关联用户后重算结转流量。
- 提高 YooKassa 可靠性：worker 在 webhook 延迟／丢失时恢复付款，兼容旧自动续期，保存支付方法，避免无法解决的记录堵塞队列。
- 修复付款身份：外部 ID 按提供商限定唯一，查询包含提供商；统一本地化描述。
- 加固 webhook 队列：原子去重入队，处理后确认，临时错误重试后才转死信队列。
- Happ Crypt4 链接加密进入核心，使用兼容 RSA 本地生成，不依赖面板 API。
- 通过语言文件恢复支付方法名、订阅描述和高级流量区的俄语默认值；源码与运行时回退仍为英语。
- 新增现成 Angie 反向代理配置，自动 ACME／TLS，支持安装向导并提供文档；分离内外 webhook 端口。感谢 @alldevic（`590cce65`）。
- 加固 Docker 发布链：核查发布来源及状态，创建来源证明、检查摘要与元数据，版本晋升生成不可变镜像清单。
- Remnawave 开发预设更新到 2.8.1，更新后端／前端／文档依赖及架构检查；扩展付款、队列、订阅、支持和套餐定向测试。

<a id="при-обновлении-10"></a>

### 升级注意

- 追加迁移 `0045_scope_provider_payment_ids`，把 `provider_payment_id` 唯一性改为 `(provider, provider_payment_id)` 组合。
- 新增 `WEB_SERVER_INTERNAL_PORT`；自定义 Compose 须检查主机 `WEB_SERVER_PORT` 与内部监听端口匹配。
- 队列新增 `WEBHOOK_QUEUE_MAX_ATTEMPTS`、`WEBHOOK_QUEUE_RETRY_BASE_SECONDS`、`WEBHOOK_QUEUE_RETRY_MAX_SECONDS`，默认 `5`、`1.0`、`30.0`。

<details>
<summary>变更来源与贡献者</summary>

* ci: harden release image provenance by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/55
* fix(ci): publish release manifests from promotion jobs by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/56
* feat(deploy): add Angie reverse proxy profile with native ACME auto-TLS by @alldevic in https://github.com/3252a8/remnawave-minishop/pull/57
* tariff controls, support presence and resilient payments by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/58

**贡献者**
* @alldevic made their first contribution in https://github.com/3252a8/remnawave-minishop/pull/57

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.5.4...v3.5.6

</details>

## v3.5.4 — 2026-07-14

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.5.4) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.5.4)

<a id="обзор-9"></a>

### 概览

加固付款流程、账号并发处理和安装器；改进后台预览和支持通知跳转。

<a id="изменения-9"></a>

### 变更

- 加强付款确认：激活前核对提供商确认金额、币种及最终状态；拒绝少付或错误币种，多付也只激活原订单。加密资产保留精确十进制金额，法币正确舍入。
- 成功付款串行完成：锁和条件更新防止并发 webhook／状态刷新造成重复激活与通知。
- Telegram 付款前重新验证当前报价及允许的套餐变更方式；订单内容取自持久记录，不使用回调元数据。组合付款将设备费与订阅费分开。
- 加固账号与一次性操作：合并使用稳定锁，拒绝跨账号重复使用同一用户代码，保留已付有效期但不叠加免费时长。邮箱验证码和魔法链接仅可消费一次。
- 安装向导必填 TLS 输入失败时终止；检查 Caddy／Nginx 端口发布和上游可用性，修复代理网络连接。成功导入后源库断开目标网络，恢复数据权限，建议停止旧 Remnashop 而不删除数据。
- 扩展插件 API：新增 v1，在运行钩子前核对兼容范围，提供稳定安装 UUID，严格限制唯一权益提供器。后台扩展区域可在受限状态保持可见。
- 改进后台与支持：管理员 Telegram 群发预览包含配置按钮；群支持／日志通知中的工单和用户卡片链接打开正确 Mini App 路由。
- 加强网页安全：封禁用户不能继续后台会话；位于 Cloudflare 后时，仅在最近代理跳点属于官方网络后接受 webhook 真实客户端 IP。
- 加固 Docker 发布：基础镜像固定摘要，运行时转为 Ubuntu 24.04 + Python 3.12，新增 SBOM／来源证明及完整 Trivy 扫描。发布标签通过晋升已验证摘要发布到 GHCR 与 Docker Hub。

<a id="при-обновлении-11"></a>

### 升级注意

- 加载器在多个权益提供器或声明的插件 API 范围不兼容时终止启动；外部插件应显式声明包含 v1 的范围。
- 依赖 `python:3.12-slim` 细节的派生镜像须适配后端／worker 转为 Ubuntu 24.04。

<details>
<summary>变更来源与贡献者</summary>

* harden payments, accounts and install flow by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/54


**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.5.3...v3.5.4

</details>

## v3.5.3 — 2026-07-10

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.5.3) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.5.3)

<a id="обзор-10"></a>

### 概览

本版重点：重做后台群发（编辑器、个性化、行内按钮、邮件渠道），新增 Overpay 及设置中的提供商链接／标志，支持前后端分离与受保护上游，手动用户分组覆盖、可配置流量重置策略，以及套餐切换／额度修复。

<a id="изменения-10"></a>

### 变更

- 重做后台群发：富文本编辑器、个性化短代码、最多四个可排序行内按钮（链接／机器人或应用激活码），提供“管理员”测试受众。
- 网页后台新增邮件渠道设置。
- 新增 Overpay 支付提供商。
- 后台和应用展示支付提供商官网及标志；CryptoPay 改用自有 HTTP 客户端，去除有漏洞 SDK 及 `certifi<2024` 限制；提供商设置本地化。
- 防止后台日志重复显示付款消息。
- 支持前后端分离部署：浏览器可见 API 基址、由可信代理而非浏览器注入 edge 令牌的受保护上游；新增 `rathole`、`split-protected-upstream` 示例，统一 Compose 网络命名（感谢 @BADtochka，`a238319`、`c563543`）。
- 新增用户手动面板分组覆盖，同步时保留，用户卡片提供独立控件与布局。
- 新增按用户配置流量重置策略及对齐重置周期；应用流量汇总展示当前策略和锚点。
- 后台设置可搜索，用户卡片与设置清单拆分区域；危险操作始终最后，仅限邀请移到通用设置。
- 新增核心活动信号：`bot.started`、`plans.viewed` 领域事件及面板最后连接时间 `subscription.last_connected_at`。
- 修复套餐切换与额度：切换规则、权益同步失败保护、手动 HWID 上限与覆盖下高级加购余额保留、试用与面板流量分别核算，以及 HWID 套餐切换换算。
- 改进应用：深链接直接应用增加时长的激活码，相关链接给出解释而非结算错误；Brotli 资源压缩、修复加载卡住、完善流量汇总，恢复本地到期提醒。
- 更新安装部署：接入已有 Nginx／Caddy 和 Pangolin 开关，tgshop 通过数据库导出迁移，防止数据库密码不同步，并加强迁移启动诊断。
- 更新文档和开发工具：刷新 API 参考及插件契约，新增 graphify 代码图谱流程与产物，CI 检查 OpenAPI 同步。

<a id="при-обновлении-12"></a>

### 升级注意

- 追加迁移 `0042_release_archived_promo_codes`、`0043_add_user_panel_squad_overrides`、`0044_add_subscription_last_connected_at`，不修改已有迁移。
- 新增环境变量（见 `.env.example`）：`WEBAPP_API_BASE_URL`、`WEBAPP_BACKEND_UPSTREAM`、`WEBAPP_BACKEND_UPSTREAM_HOST`、`MINISHOP_EDGE_TOKEN`、`MINISHOP_EDGE_TOKEN_HEADER`，用于分离部署和受保护上游。
- 删除 `aiocryptopay` 和 `certifi<2024` 固定限制，`certifi` 提高到 `>=2024.7.4`；CryptoPay 使用自有客户端。更新前端 `package-lock.json`（tiptap 编辑器）。
- 更新前端 nginx（edge 令牌、分离上游）与 Dockerfile，调整 Compose 并新增部署示例。
- 贡献者：@BADtochka——独立 API 基址与 Docker 网络命名（`a238319`、`85a9160`、`a122c73`、`0be145b`、`c563543`、`e9dbb18`）。

<details>
<summary>变更来源与贡献者</summary>

* feat: support split backend API base by @BADtochka in https://github.com/3252a8/remnawave-minishop/pull/52
* broadcast overhaul, Overpay provider and split-deploy support, plan changes fixes by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/53


**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.5.2...v3.5.3

</details>

## v3.5.2 — 2026-07-03

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.5.2) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.5.2)

<a id="обзор-11"></a>

### 概览

此版本主要调整架构：
- 通过共享链接流程统一支付提供商；
- 前端全面迁移至 TypeScript + Svelte 5 runes；
- 全仓类型及静态检查，并修复流量充值、安装教程和应用鉴权。

<a id="изменения-11"></a>

### 变更

- 修复机器人流量充值：恢复订阅核心拆分时丢失的购买按钮处理器；与 Mini App 一致，使用量达到 80% 才显示菜单按钮；旧按钮展示剩余流量并刷新菜单，不再静默失败。普通与高级流量共用可用性检查，开关标签和提示本地化。
- 后台用户卡片新增可复制安装教程链接；鉴权教程路由发现面板重置链接导致短 UUID 过期时重新获取，避免分组专属配置回退全局默认。
- 修复应用界面和鉴权：隐藏停用标签页、刷新设备缓存、限制挂起鉴权请求、启动时先监听应用再请求 Telegram、流量提醒使用面板重置日期。
- 调试操作日志发送到日志聊天，新增 `message_log_notifier` 投递服务。
- 支付提供商改为共享链接流程：CloudPayments、Pally、Platega 统一；YooKassa 回调拆模块，新增按变体区分上下文与创建前回调钩子、共享 webhook 安全工具及 Wata 按配置描述器。
- 前端全面转为 TypeScript 和 Svelte 5 runes：迁移剩余应用／后台／入口模块及测试，为存储、协调器、组件补类型，新增禁止自有 JS 架构门禁，拆分 PaymentDialogs、mockApi、previewMock、AppModeContent。
- 收紧类型与静态检查：mypy 覆盖全仓（`scripts`、`backend/scripts`、完整 `tests/`），`type: ignore` 仅保留一个边界例外；启用完整 ruff 组（UP、W、C4、SIM、PIE、PERF、RUF、LOG、G、PLE、T10）；pytest 将警告视为错误，覆盖率使用分支模式且下限只能提高。
- 拆分大型模块：`user_dal` 按读取／合并／写入拆分，迁移器改包（迁移链与引擎，快照固定 ID 顺序），`import_legacy` 改包；拆分应用教程、主题目录及后台激活码编辑，抽出 worker 共用套餐流量通知投递。
- 为后台套餐响应及剩余自由结构补类型，或标为非 JSON；重新生成 `openapi.json`、`openapi.generated.ts`。
- 新增空操作可观测性扩展点，不改变行为。
- 更新开发部署：一条命令启动开发环境，固定 Node 与工具版本，启动时更频繁健康检查，恢复 npm 10 lock 兼容性。
- 更新文档：英文贡献入口、架构说明、流量充值可用条件及用户文案本地化要求；当时删除 `CHANGELOG.md`，改由提交和 PR 记录历史。

<a id="при-обновлении-13"></a>

### 升级注意

- 本版本没有数据库结构、迁移或环境变量变化；仅将迁移器重构为包，41 个迁移 ID 与顺序不变，由快照测试固定。升级无需手动步骤。
- 前端仅使用 TypeScript，Node 和工具版本已固定，贡献者须使用对应 Node。

<details>
<summary>变更来源与贡献者</summary>

* link-flow payments, all-TypeScript frontend, repo-wide typing & fixes by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/50


**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.5.1...v3.5.2

</details>

## v3.5.1 — 2026-07-01

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.5.1) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.5.1)

<a id="изменения-12"></a>

### 变更

- 扩展激活码：按比例调整套餐价格、时长与流量倍数、额外有效期、仅付款时应用、最低时长／流量及整单或结算范围条件，并支持归档。
- 保存激活码效果与结算快照：应用效果、基础金额、价格调整、已付时长和流量，供历史与正确计算使用。
- 后台新增激活码使用审计，以及机器人／网页应用的使用链接生成。
- 兼容 Remnawave 2.8：重做面板 webhook，增加节点与 HWID API 工具及版本化开发预设（2.7.4、2.8.0）。
- 套餐 worker 与通知考虑流量重置设置；预警包含重置详情，并保护重置通知。
- 加速并稳定后台：优化加载与响应，用户列表减少转换，改用更现代的 Svelte runes 响应模式。
- 改进套餐及激活码编辑器：套餐标签页、紧凑代码编辑、有效期奖励模式、目录与已上传外观资源保存，以及不限量显示。
- 改进鉴权：会话 bearer 令牌回退，契约要求会话令牌。
- 修复后台和网页应用界面问题。
- 修复 Remnashop 导入：安全解析试用标记、保留试用套餐分配与后台包私有字段，正确解析 HWID 设备响应。
- 更新工具及依赖：Postgres 固定 17.6、Redis 客户端 7.4.1，更新 prettier-plugin-svelte、Tailwind、typescript-eslint，扩展单元／契约／集成测试。

<a id="при-обновлении-14"></a>

### 升级注意

- 追加迁移 `0038`–`0041`：扩展代码效果、激活与结算快照、付款奖励模式标记；幂等迁移器自动应用。
- Postgres 镜像固定 `17.6`；自行固定 Compose 标签时请同步更新。
- 兼容 Remnawave 2.8，开发环境新增 2.7.4／2.8.0 预设；无新增生产必填变量。

<details>
<summary>变更来源与贡献者</summary>

* Feature/bonus extension by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/47
* Feature/remnawave 2.8.0 by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/48
* Activation-code effects, Remnawave 2.8 support and admin panel updates by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/49


**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.5.0...v3.5.1

</details>

## v3.5.0 — 2026-06-27

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.5.0) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.5.0)

<a id="обзор-12"></a>

### 概览

除注册访问控制、试用高级流量规则、机器人菜单开关及流量重置通知外，本版包含大规模内部重构：契约类型化、Svelte 5 runes 迁移、巨型文件拆分及支付提供商包化。

<a id="изменения-13"></a>

### 变更

- 新增注册访问控制 `REGISTRATION_INVITE_ONLY_ENABLED`，开启后新公开注册必须有有效邀请链接；已有用户仍可通过 Telegram、应用、邮箱验证码、魔法链接和密码登录。
- 新增试用高级访问规则：独立高级流量上限 `TRIAL_PREMIUM_TRAFFIC_LIMIT_GB` 和高级 Internal Squads `TRIAL_PREMIUM_SQUAD_UUIDS`，对高级分组应用额度。
- 可关闭 Telegram 机器人菜单，仅保留少量按钮并引导使用网页应用。
- 普通与高级套餐新增流量额度重置通知，面向上一周期已耗尽或接近耗尽的用户。
- 修复支付：保存成功状态、失败尝试详情、日志权益单位、抑制过时失败通知，防止提供商启动循环导入。
- 修复后台／Mini App：首次加载后表格行渲染、浅色主题表面变量、标志加载指示居中、明确设置标签、防止无变化存储更新。
- 改进安装向导诊断。

<a id="рефакторинг-и-инфраструктура"></a>

### 重构与基础设施

- **HTTP 类型化契约与 OpenAPI：** 后台与应用路由使用 pydantic 请求／响应模型替代自由结构，生成 `docs/openapi.json` 和 `frontend/.../openapi.generated.ts`，提供类型化路径构造、路由契约注册及 CI 检查。
- **领域事件契约：** 每事件一个 pydantic 模型（`extra="forbid"`），通过 `emit_model` 发布，可重新生成事件目录。
- **Svelte 5 runes 迁移：** 所有组件与存储转为 runes，删除旧 `export let`、`$:`、插槽和动态组件（改为 snippets），构建与静态检查固定仅 runes 模式，删除表格 runes 桥接。
- **拆分 `App.svelte`：** runes 外壳状态存储，抽出数十个运行时／操作／辅助／视图模块（启动、恢复、鉴权、激活、Telegram、导航、计费深链接等），应用外壳转为 TypeScript。
- **后端类型：** 覆盖处理器、服务、支付提供商、数据库、中间件、配置、键盘和网页插件；mypy 在全部强制范围通过，CI 扩大范围。
- **支付提供商包化：** yookassa、stripe、wata、paykilla、heleket、platega、lava、severpay、freekassa、pally、cryptopay、cloudpayments、stars 各自独立包；共享链接流程引擎与提供商描述、webhook 处理、仅导入兼容门面及一致性契约。
- **巨型文件拆分：** 后台区域、邮件模板、套餐流量 worker、面板 API、订阅生命周期、后台同步、用户启动、订阅核心及计费／鉴权／资源路由。
- **架构边界：** 检查门面与运行时模块导入边界，解除门面运行时依赖，`config` 提供类型化设置视图，网页响应一致性门禁，测试固定公开门面接口。
- **测试与 QA：** 按职责重组测试，Vitest 覆盖率、Playwright 模拟端到端冒烟门禁、统一开发／QA Compose 环境及提供商 webhook／链接流程契约。
- **基础设施与工具：** `.gitattributes` 统一 LF，聚合质量命令、根检查脚本对齐 CI、CI 契约检查。
- **文档：** 文档站交互式 API 参考、提供商／事件／端点操作指南、贡献者及智能体指南、架构概览和安全基础说明。

<a id="зависимости-и-безопасность"></a>

### 依赖与安全

- **高危安全修复：** `@playwright/test` 从 `^1.50.1` 升到 `^1.55.1`（lock 解析为 1.61.1），修复 GHSA-7mvr-c777-76hp：Playwright 下载、安装浏览器时未验证 SSL 证书。未解决 Dependabot 告警为 0。
- **后端：** `sqlalchemy[asyncio]` 2.0.49 → 2.0.51，YooKassa SDK 3.10.1 → 3.11.0；此前同范围更新 `pydantic-settings` 2.14.1 → 2.14.2。
- **前端开发工具更新：** eslint 10.6.0、svelte 5.56.4、vite 8.1.0、svelte-check 4.7.1、typescript-eslint 8.62.0、prettier 3.9.0、eslint-plugin-svelte 3.20.0、svelte-eslint-parser 1.8.0、@tanstack/svelte-query 6.1.35、@internationalized/date 3.12.2、tailwindcss／@tailwindcss/cli／@tailwindcss/vite 4.3.1；按 prettier 3.9.0 格式化。
- **lock 整理：** 重新生成一致的 `frontend/package-lock.json`，使所有前端 CI 任务可运行 `npm ci`。

<a id="при-обновлении-15"></a>

### 升级注意

- 新增 `REGISTRATION_INVITE_ONLY_ENABLED`、`TRIAL_PREMIUM_TRAFFIC_LIMIT_GB`、`TRIAL_PREMIUM_SQUAD_UUIDS`；开发／QA 新增 `DEV_POSTGRES_PORT` 和 `QA_*`。**无新数据库迁移。**

<details>
<summary>变更来源与贡献者</summary>

* chore(deps): bump the pip group across 2 directories with 1 update by @dependabot[bot] in https://github.com/3252a8/remnawave-minishop/pull/40
* Feature/api refactor by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/41
* Feature/architecture hardening by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/42
* Feature/architecture refactoring by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/43
* Feature/provider orchestration unification by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/44
* Feature/svelte runes by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/45
* Registration gate, trial premium rules, typed API contracts + large refactor by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/46


**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.4.10...v3.5.0

</details>

## v3.4.10 — 2026-06-19

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.4.10) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.4.10)

<a id="обзор-13"></a>

### 概览

大幅改进安装器和 Remnashop 迁移，新增 Pally、扩展 Wata Crypto，加速并缓存订阅教程，修复教程细节，后台表格转为数据表并修复其他问题。

<a id="изменения-14"></a>

### 变更

- 扩展 `scripts/install.sh`：DNS／TLS 配置、eGames 反向代理、面板凭据自动发现、迁移步骤预填与本地化、日志遮蔽数据库凭据、处理 EOF 及保留下载路径。
- 重做 Remnashop 导入 `import_legacy.py`：套餐配置、用户激活码快照、用户外键及订阅链接令牌、可选清空目标库、保留 Telegram 状态、读取 root 所有环境文件、完成报告及支付提供商映射。
- 新增 Pally 支付提供商。
- Wata 可增加 Wata Crypto 付款按钮。
- 改进订阅教程：缓存配置与可用教程、精简载荷并加快加载，支持外部分组、面板自定义子页面配置及默认教程回退。
- 后台备份／付款／本地区域使用带响应式分页的数据表，增加可操作错误提示及描述，缓存健康检查与日志，改进拖动排序手势。
- 面板 API 支持 Cookie 头（经 eGamesAPI／remnawave-reverse-proxy 访问），规范化 Remnawave 流量策略。
- 修复支付计费：保存 YooKassa 设备元数据及发票设备数，机器人提供商菜单使用付款币种，接入 HWID 加购。
- 修复通知：抑制已被替代订阅的到期消息，网页应用通知入队。
- 更新 caddy／newt／nginx／no-proxy 部署示例和 eGames nginx 关联，将 nginx 配置同步到运行中容器。

<a id="при-обновлении-16"></a>

### 升级注意

- 新增可选 `PANEL_API_COOKIE`，用于面板 API Cookie 请求头。
- 新增教程缓存 TTL：`SUBSCRIPTION_GUIDES_CONFIG_CACHE_TTL_SECONDS`、`SUBSCRIPTION_GUIDES_RESOLVED_CACHE_TTL_SECONDS`、`SUBSCRIPTION_GUIDES_PUBLIC_CACHE_TTL_SECONDS`，默认 300 秒。

<details>
<summary>变更来源与贡献者</summary>

* feat: add Pally payment provider by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/38
* feat: installer DNS/cert & migration overhaul, Pally/Wata payments, guide caching by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/39


**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.4.9...v3.4.10

</details>

## v3.4.9 — 2026-06-17

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.4.9) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.4.9)

<a id="обзор-14"></a>

### 概览

新增 Stripe、CloudPayments、LAVA Business、带功能注册表的内部插件／扩展 API、经反应器处理副作用的进程内事件总线、应用主题自定义，并改进后台、应用和付款完成处理。

<a id="изменения-15"></a>

### 变更

- 新增 Stripe、CloudPayments、LAVA Business，支持 Stripe／CloudPayments 循环扣款及共享循环模块；经注册表接入并在后台配置。
- 加强 YooKassa 续期：自动续期控件、循环提供商及全提供商共享循环／成功机制。
- 新增内部插件／扩展 API：加载器、规格、worker／队列／迁移／语言钩子、内置 lknpd／telemetry、功能权益注册及扩展文档。
- 新增进程内领域事件总线，副作用经事件反应器路由，覆盖账号生命周期和有效期奖励。
- 新增权益服务并重做付款完成：通知延迟到事务提交，先确认权益到期再本地成功，验证面板到期更新，记录提供商创建错误。
- 支持默认应用主题自定义，合并深色和浅色主题。
- 改进后台：区域注册管理、设置深链接、用户窗口分配套餐、保存操作草稿、续期控件分组、加快打开、挂载时加载功能标记。
- 改进应用：按订阅匹配教程，不限量时隐藏额度卡片，提供服务器状态链接和标签。
- 改进邮件：安全内嵌 PNG 标志、元数据、站点图标与本地化。
- 修复邀请计量，邀请有效期只发放一次（新增 `referral_welcome_bonus_claimed_at`）；邀请与用户代码处理转事件模型。
- 更新 CI／Docker／部署：Node 24 actions、修复 pip-audit、健康检查不产生僵尸进程、运行时包含 `curl`、恢复 GitHub Actions dev 发布、全量扫描面板分页间隔可配置，删除 `.gitlab-ci.yml`。
- 扩展 Stripe／CloudPayments／LAVA、领域事件与反应器、插件、权益、支付 webhook、自动续期和主题测试。

<a id="при-обновлении-17"></a>

### 升级注意

- 数据库新增 `users.referral_welcome_bonus_claimed_at`，包含迁移。
- Dockerfile 安装后强制升级 `certifi`（受 `aiocryptopay==0.4.8` 固定限制，pip-audit 忽略 PYSEC-2024-230），运行时保留 `curl` 供健康检查。

<details>
<summary>变更来源与贡献者</summary>

* provider: lava by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/30
* chore(deps-dev): bump esbuild from 0.28.0 to 0.28.1 in /frontend in the npm_and_yarn group across 1 directory by @dependabot[bot] in https://github.com/3252a8/remnawave-minishop/pull/31
* Feature/cloudpayments by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/33
* Feature/stripe by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/35
* New payment providers, plugin/extension API and domain event bus by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/36
* chore(deps-dev): bump the npm_and_yarn group across 1 directory with 2 updates by @dependabot[bot] in https://github.com/3252a8/remnawave-minishop/pull/34
* chore(deps-dev): bump vite from 8.0.12 to 8.0.16 in /frontend in the npm_and_yarn group across 1 directory by @dependabot[bot] in https://github.com/3252a8/remnawave-minishop/pull/37


**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.4.8...v3.4.9

</details>

## v3.4.8 — 2026-06-10

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.4.8) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.4.8)

<a id="обзор-15"></a>

### 概览

v3.4.7 之后（`v3.4.7..HEAD`）：新增 PayKilla、Telegram 更新防刷、支持旧 tg-shop／Remnashop 迁移的 shell 向导及后台配置诊断，改进支付、套餐和 Mini App。

<a id="изменения-16"></a>

### 变更

- 新增 PayKilla：支持币种兑换、最低付款检查、发票文本清理及正确传递套餐币种。
- 改进支付提供商：按提供商身份复用未完成账单／链接，无需重启应用全局请求超时，连接重试与恢复，交易支持“待处理”（感谢 @BADtochka，`234fc695`、`3170b966`、`766f2a57`、`e3f35a46`）。
- Telegram 机器人防刷：前置检查，按消息／回调／行内／`/start` 限频，付款和试用回调冷却，丢弃非私聊更新，后台可配置。
- 新增 `scripts/install.sh` shell 向导，支持旧 remnawave-tg-shop 及 Remnashop 导入：用户、代码、支付设置、旧邀请代码兼容。**该版本 Remnashop 迁移仍在开发，未充分测试，务必备份。**
- 后台新增配置诊断服务、问题横幅及 Telegram webhook 告警刷新。
- 改进后台：缓存“从未订阅”“未连接 VPN”群发受众计数，显示用户 VPN 活跃与试用历史、单用户 HWID 上限覆盖、改进分页并修复用户弹窗生命周期（感谢 @BADtochka，`9adcbf10`）。
- 套餐编辑器支持购买周期与流量包顺序、统一价格行、拖动排序及更好手机布局。
- 改进 Mini App：到期倒计时、稳定手机导航、哈希不可变资源及旧缓存清除、试用激活页、邮件与深链接主题强调色、按视口缩放标志。
- 纯邮箱用户支持试用及邀请欢迎时长，修复邮箱头像，关闭邮箱鉴权时隐藏登录／绑定表单；代码与邀请奖励分配默认套餐。
- 改进邮件：内嵌上传标志及新版品牌模板。
- 新增基于 docker-mailserver 的本地 SMTP Compose 示例（感谢 @austnv，`bd7361e9`）。
- 加强安全：正确解析代理链后 webhook 与提供商允许清单的客户端 IP（感谢 @BADtochka，`f07031f3`、`cc74ddec`），按安全公告更新 pyjwt、certifi、aiohttp。
- 改进构建部署：减少 Docker 层变动，将哈希应用资源放入后端镜像，新增 GitLab CI dev 镜像，修复 nginx 路由正则。
- 遥测新增官方／自定义镜像标记，用于匿名统计。

<a id="при-обновлении-18"></a>

### 升级注意

- 数据库结构有变化，所含迁移自动执行。
- 新增 `TELEGRAM_ANTIFLOOD_*` 及冷却设置、`PAYMENT_REQUEST_TIMEOUT_SECONDS`、`PANEL_API_*` 超时、`MIGRATION_REMNASHOP_*`、`TRIAL_WITHOUT_TELEGRAM_ENABLED`、`DISPOSABLE_EMAIL_DOMAINS`。
- 当时 `TRUSTED_PROXIES` 默认扩展到 Docker／局域网／Kubernetes 私网范围，升级须核对是否适合拓扑。
- 贡献者：@BADtochka（支付、代理安全、后台修复，共 24 次提交），@austnv（docker-mailserver 示例，`bd7361e9`、`c733d830`）。

<details>
<summary>变更来源与贡献者</summary>

* remnashop migration feature, install wizard by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/23
* chore(deps): bump the pip group across 2 directories with 1 update by @dependabot[bot] in https://github.com/3252a8/remnawave-minishop/pull/25
* 新增 Docker Mailserver 本地 SMTP 支持，作者 @austnv：https://github.com/3252a8/remnawave-minishop/pull/26
* 支付文档及 FreeKassa 域名替换，作者 @BADtochka：https://github.com/3252a8/remnawave-minishop/pull/27
* feat: harden Telegram bot anti-flood handling by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/28
* PayKilla provider, Telegram anti-flood, install wizard and Remnashop migration (test) by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/29

**贡献者**
* @austnv made their first contribution in https://github.com/3252a8/remnawave-minishop/pull/26
* @BADtochka made their first contribution in https://github.com/3252a8/remnawave-minishop/pull/27

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.4.7...v3.4.8

</details>

## v3.4.7 — 2026-06-01

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.4.7) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.4.7)

<a id="обзор-16"></a>

### 概览

新增多币种套餐及按币种筛选提供商、安全面板写入演练（开发及迁移前测试）、可退出匿名安装遥测，改进后台用户管理，修复频道、深链接网关、流量加购和邮件本地化。

<a id="изменения-17"></a>

### 变更

- 多币种 JSON 套餐支持 `default_currency`（`usd`、`eur`、`usdt` 等）、通用价格和流量包字段，旧 `*_rub` 为别名。支付方法按币种筛选，**系统 → 套餐**显示当前币种的方法／服务／可用性矩阵。
- 面板写入演练：`PANEL_WRITE_MODE=dry_run`／`auto` 与 `APP_RUNTIME_MODE` 可读取真实面板，仅验证和记录用户写操作（`[PANEL DRY-RUN OK] would PATCH ...`），日志遮蔽密钥与 ID。
- 新增可退出匿名遥测：worker 每日以 PostHog 格式发送版本、系统／架构、Python、语言、已启用提供商和用户量区间；通过 `TELEMETRY_ENABLED` 或**后台 → 系统**开关关闭，无需重启。
- 扩展后台用户管理：筛选、列排序、列表指标、卡片邀请关系及用户详情弹窗 `UserDetailModal`。
- 后台可重置试用资格而不删除历史，新增 `trial_eligibility_reset_at` 和迁移 0033。
- 新增“订阅已到期”群发受众。
- 登录页可选择语言，恢复手机后台语言选择器。
- 新增 `message_audit`，审计机器人实际对外消息投递。
- 邮件更新：支持模板本地化、从模板渲染预览、文档演示预览区域，生成预览不再依赖机器人运行环境。
- 修复付款流量：统一加购流程和不限量覆盖，恢复数据库后执行迁移，恢复等待邮箱验证码页面。
- 修复必需频道检查：`REQUIRED_CHANNEL_ID` 规范为 `-100…`，可靠识别频道访问错误。
- 修复手机体验：应用启动提示期间深链接网关保持打开，增大续期按钮。
- CI dev 镜像仅标记 `dev`，不再生成 `dev-<sha>`。
- 扩展多币种、遥测、面板演练、后台指标／权益／试用重置、消息审计、频道规范化与支付提供商注册测试。

<a id="при-обновлении-19"></a>

### 升级注意

- 数据库迁移 `0033_add_trial_eligibility_reset_marker` 新增 `users.trial_eligibility_reset_at`，自动应用。
- 新增 `TELEMETRY_ENABLED`、`TELEMETRY_ENDPOINT`、`TELEMETRY_API_KEY`、`TELEMETRY_INTERVAL_HOURS`，以及 `APP_RUNTIME_MODE`、`PANEL_WRITE_MODE`、`PANEL_DRY_RUN_VALIDATE_REMOTE`、`PANEL_DRY_RUN_SYNTHETIC_CREATE`。Heleket／Platega／SeverPay 使用自定义币种时维护 `*_SUPPORTED_CURRENCIES`。
- 遥测默认开启，可通过 `TELEMETRY_ENABLED=False`、清空端点／密钥或后台开关退出。不发送个人数据或密钥。

<details>
<summary>变更来源与贡献者</summary>

* Feature/multicurrency by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/18
* Feature/telemetry by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/19
* Enhance admin users and subscription workflows by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/20
* Improve admin UX, trial reset behavior, and channel subscription checks by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/21
* Multicurrency (future-proof feature), panel dry-run mode (dev feature), install telemetry and admin user tools by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/22


**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.4.6...v3.4.7

</details>

## v3.4.6 — 2026-05-30

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.4.6) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.4.6)

<a id="обзор-17"></a>

### 概览

订阅统计按有效／付费／试用／免费拆分，新增镜像构建、PR 检查和安全扫描 GitHub Actions，修复 Telegram 探测通知和文档演示路由。

<a id="изменения-18"></a>

### 变更

- 按访问类型分别统计有效、付费、试用和免费订阅；无有效订阅用户计为非活跃。`user_dal` 按提供商及面板状态分类，使用按用户聚合子查询。
- 后台与行内统计适配新分类：文本报告增加行和图标，行内模式传递 `active`／`free`，卡片说明展示有订阅用户数。
- 后台统计卡片以活跃用户为主指标，标签显示总用户占比，底部分列付费、免费、试用；更新卡片标签。
- Telegram 聊天可达性改用 `get_chat`，不发送探测消息，用户不再收到测试通知；删除相关按钮和文案。
- 修复文档演示：运行时输出 `app/index.html` 而非 `app.html`，更新 Cloudflare Pages 重写及路由生成，消除无扩展名与 `.html` 重定向循环。
- 新增可复用 Docker 构建发布、dev／正式镜像、PR CI、安全 Trivy 扫描和依赖审查 GitHub Actions。
- 更新英语／俄语统计条目及演示模拟 API，提供完整用户统计字段。
- 扩展 `user_dal` 订阅分类和 Telegram 通知测试，更新 Svelte 开发依赖。

<a id="при-обновлении-20"></a>

### 升级注意

- 无数据库结构或环境变量变化。
- 新 CI／CD GitHub Actions 需要仓库标准包／镜像仓库权限。

<details>
<summary>变更来源与贡献者</summary>

* ci: add GitHub Actions for image builds, PR checks and security scans by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/13
* chore(deps-dev): bump svelte from 5.55.5 to 5.56.0 in /frontend in the npm_and_yarn group across 1 directory by @dependabot[bot] in https://github.com/3252a8/remnawave-minishop/pull/14
* Split subscription stats by access type, CI/CD pipelines and notification/docs-demo fixesDev by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/15

**贡献者**
* @dependabot[bot] made their first contribution in https://github.com/3252a8/remnawave-minishop/pull/14

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.4.5...v3.4.6

</details>

## v3.4.5 — 2026-05-30

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.4.5) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.4.5)

<a id="обзор-18"></a>

### 概览

**v3.4.4** 之后：跟踪 Telegram 投递并提醒启动机器人，面板 webhook 镜像订阅生命周期及邮件副本，按套餐周期发放邀请时长，后台面板 webhook 设置、爬虫屏蔽及明显界面改进。

<a id="изменения-19"></a>

### 变更

- 新增 Telegram 通知状态：`users` 增加状态／检查时间（迁移 0032），`telegram_notifications` 提供 `enabled/needs_start/blocked/unknown`，Mini App 横幅提醒启动机器人接收通知。
- 新增 `subscription_lifecycle_notifications`，通过面板 webhook 和邮件同步到期／逾期提醒；`user_email_notifications` 同步用户邮件通知。
- 改进邮件续期流程，扩展 `email_templates`，新增 `SUBSCRIPTION_EMAIL_NOTIFICATIONS_ENABLED`。
- 邀请奖励按套餐周期配置 `referral_bonus_days_inviter`／`referral_bonus_days_referee` 并验证，按周期计算，机器人按套餐分组显示。
- 面板 webhook 设置进入**后台 → 系统 → 设置**及设置清单；明确面板 webhook／订阅日志，更新 `WEBHOOK_URL`（`/webhook/panel`）配置文档。
- 修复面板 webhook：查询失败时保留订阅，消除订阅 worker 死锁，扩展 `panel_api_service` 日志。
- 屏蔽爬虫与 AI 机器人：`robots.txt` 包含 GPTBot、ClaudeBot、PerplexityBot 等，nginx 所有 location 增加 `X-Robots-Tag: noindex`，前端镜像包含 `robots.txt`。
- 改进应用：范围／颜色／文件控件、重做滚动区，更新设备／邀请／支持／鉴权页面；不活跃设备隐藏流量汇总，关闭邮箱鉴权仍显示 Telegram 登录。
- 改进后台日志用户卡片，标准化网页控件和套餐编辑器。
- 修复高级流量字节格式、YooKassa 及共享成功／webhook 处理。
- 更新文档与演示：dev 演示运行时、通知表、部署示例及 Compose。
- 其他：`RUB_PRICE_*` 默认 200／600／1200／2400，语言覆盖按文件内容重载，`.gitattributes` 规范前端行尾。

<a id="при-обновлении-21"></a>

### 升级注意

- 迁移 `0032_add_telegram_notification_status` 为 `users` 增加四列，自动应用。
- 新增 `SUBSCRIPTION_EMAIL_NOTIFICATIONS_ENABLED`，套餐新增 `referral_bonus_days_inviter`／`referral_bonus_days_referee`。`RUB_PRICE_1/3/6/12_MONTH(S)` 默认值从未设置改为 200／600／1200／2400。
- 面板 webhook 需要 `PANEL_WEBHOOK_SECRET`，Remnawave Panel 设置 `WEBHOOK_URL = WEBHOOK_BASE_URL + /webhook/panel`。
- 前端 Dockerfile 将 `robots.txt` 复制进镜像。

<details>
<summary>变更来源与贡献者</summary>

* Telegram delivery tracking, subscription lifecycle mirroring and per-tariff referral bonuses by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/12


**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.4.4...v3.4.5

</details>

## v3.4.4 — 2026-05-28

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.4.4) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.4.4)

<a id="обзор-19"></a>

### 概览

新增备份、文档交互式演示，改进应用和后台，修复支付／HWID，新增本地订阅通知。

<a id="изменения-20"></a>

### 变更

- 新增备份系统：后台手动创建、归档 worker、投递备份／日志聊天、恢复归档、ZIP 安全检查及配置文档。
- 备份 Compose 目录需要在后端和 worker 挂载 `${COMPOSE_BACKUP_SOURCE:-.}:/app/compose-source:${COMPOSE_RESTORE_MODE:-rw}`。
- 更新文档和演示：独立演示运行时、全屏路由、手机导航、应用／后台／鉴权／设备／备份模拟场景及最新文档。
- 改进应用：紧凑流量与状态卡片、正确套餐操作、耗尽状态、强制操作激活对话框，以及计费操作后设备刷新。
- 改进鉴权和本地化：共用邮箱验证码确认页、演示 Telegram 登录、保存账号语言及切换语言后的后台视图，更新英语／俄语翻译。
- 新增默认品牌资源及应用／后台外观的备用图标和标志。
- 支持工单保留草稿，修正消息间距与宽度，加快回复完成。
- 修复付款及 HWID 加购：日期序列化、webhook 幂等、已付周期、提供商边界情况，以及 YooKassa HWID 付款集成。
- 新增本地订阅通知 worker：到期前提醒、到期处理及试用流量耗尽通知。
- 更新部署／Docker：优化层缓存，加入备份恢复依赖及 Compose 备份挂载。
- 扩展备份恢复、备份 worker、订阅通知、支付 webhook、HWID 加购、账号语言和应用资源测试。

<details>
<summary>变更来源与贡献者</summary>

* Update and structurize docs by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/5
* Backups, docs demo, and Mini App improvements by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/7

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.4.3...v3.4.4

</details>

## v3.4.3 — 2026-05-26

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.4.3) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.4.3)

<a id="mini-app-и-инструкции-подключения"></a>

### Mini App 与连接教程

- Mini App 内置安装教程：`/install`、公开 `/s/<token>`、二维码、深链接按钮及普通连接链接回退。
- 从 Remnawave Panel 加载 Subscription Page 配置，后台可用 JSON 覆盖。
- 付款／试用／激活码后的机器人按钮可直接引导连接教程。
- 新增应用预览元数据、后台标题设置及 iOS 主屏幕图标。

<a id="runtime-переводы"></a>

### 运行时翻译

- 后台新增运行时翻译编辑器。
- 无需修改 `locales/*.json` 即可覆盖翻译，存入数据库并镜像到 `data/locales-overrides.json`。
- 翻译键按受众和区域分组。

<a id="платежи"></a>

### 支付

- 稳定 Wata：付款链接、预付款 webhook、待付款链接重试／复用、状态刷新、过期链接及正确保存提供商交易 ID。
- Wata 链接 TTL 改用分钟，配置为 `WATA_LINK_TTL_MINUTES`。
- 修复 YooKassa 网页付款和 HWID 设备加购。
- 修复 Mini App 内打开 Telegram Stars 发票。
- 支付提供商新增仅管理员模式。
- 成功消息去掉直接连接链接，改用按钮和教程。

<a id="тарифы-trial-и-hwid"></a>

### 套餐、试用与 HWID

- Mini App 新增试用激活页。
- 改进后台试用与套餐设置。
- 旧套餐设置与 JSON 目录分开，并标记警告。
- HWID 加购绑定当前订阅有效期，支持按比例计价及续期。
- 修复高级分组访问保留及多余状态同步。

<a id="админка"></a>

### 管理后台

- 新增付款详情页。
- 改进支付提供商、webhook 地址和设置分组。
- 改进套餐、试用及旧参数设置。
- 删除机器人账号时可同时删除 Remnawave 用户。
- 更新后台样式、应用布局、自定义主题和预览。

<a id="panel-sync-и-профили"></a>

### 面板同步与资料

- 移除机器人启动时同步面板的行内操作，手动同步改为入队。
- 新增紧凑面板同步诊断。
- 修复描述字段反复变化导致的多余面板 PATCH。
- 修复面板描述旧邮箱清理及已关联面板邮箱恢复。
- 自动合并重复面板身份。
- 激活／付款状态变化后刷新应用资料。

<a id="deploy-и-документация"></a>

### 部署与文档

- 更新 Caddy、Nginx、Newt／Pangolin 和无代理部署示例。
- 更新 README 及应用、教程、环境变量、部署、套餐和迁移文档。

<a id="при-обновлении-22"></a>

### 升级注意

- 新增运行时语言覆盖、安装分享令牌及 HWID 有效期／付款字段数据库迁移。
- Wata 旧 `WATA_PAYMENT_LINK_TTL_DAYS` 改为 `WATA_LINK_TTL_MINUTES`，默认 15 分钟。
- 安装教程默认启用，尝试读取面板 Subscription Page 配置；出错时回退普通连接链接。

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.4.2...v3.4.3

## v3.4.2 — 2026-05-22

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.4.2) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.4.2)

<a id="вход-связывание-аккаунтов-и-настройки-админки"></a>

### 登录、账号关联与后台设置

[原始 PR](https://github.com/3252a8/remnawave-minishop/pull/1) · @3252a8
<a id="auth--связка-аккаунтов"></a>

#### 鉴权与账号关联
- 修复 Mini App 和 Telegram OAuth 的登录与绑定。
- 修复邮箱和 Telegram 账号合并，包括邮箱订阅有效而 Telegram 订阅已到期的情况。
- 合并账号时正确同步面板身份：先删除多余用户，再更新保留用户。
- 新增账号合并日志通知。
- 修复 Telegram Mini App 退出，手动退出不再破坏通过 `initData` 重新登录。

<a id="админка-и-настройки"></a>

#### 后台与设置
- 提供商设置展示可复制 webhook 地址。
- 后台资源使用稳定路径和回退，避免延迟加载因旧哈希资源失败。
- 后台侧栏版本显示修复，dev 构建可按分支／SHA 区分。
- 调整手机后台按钮样式。

<a id="платежи--panel-sync--тарифный-worker"></a>

#### 支付、面板同步与套餐 worker
- 修复提供商启用后的付款按钮显示。
- 改进面板身份同步，避免重复多余更新。
- 用户已有有效面板 UUID 时，为订阅恢复缺失面板引用。
- 批量预取确认面板用户不存在时，停用订阅且不发送用户通知。

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.4.1...v3.4.2

## v3.4.1 — 2026-05-21

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.4.1) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.4.1)

- 网页应用新增支持工单创建区域。
- 应用和机器人在付款前展示所购服务信息。
- 邮箱和密码登录。
- 重构支付提供商。
- Wata 支付提供商。
- Heleket 支付提供商。
- 大幅性能优化。
- 修复小问题。

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.4.0...v3.4.1

## v3.4.0 — 2026-05-17

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.4.0) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.4.0)

- 可创建自定义[主题](docs/features/webapp-themes.md)。
- 后台可上传标志与站点图标。
- 服务拆分独立容器，提高稳定性并为后续扩展奠定基础。
- 修复试用激活。
- 修复 YooKassa。
- 修复未配置设备加购价格时仍显示加购按钮。
- 修复旧套餐导致订阅购买元素重复。
- 其他小修复与改进。

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.3.0...v3.4.0

## v3.3.0 — 2026-05-13

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.3.0) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.3.0)

- 网页应用管理后台。
- 可创建多个套餐，支持按月／流量及不同分组。
- 流量和设备加购。
- 套餐内可建立高级分组，独立统计并加购流量。
- 应用桌面布局。
- 可关闭管理员操作日志。
- 修复发放邀请有效期时用户分组变化。
- 修复问题及其他细节改进。

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.2.4...v3.3.0

## v3.2.4 — 2026-05-06

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.2.4) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.2.4)

- 修复用户无法访问 Telegram 时的应用访问；Telegram OAuth 按钮显示状态，Telegram 不可用时仍显示头像。 ([8783129c](https://github.com/3252a8/remnawave-minishop/commit/8783129c16b57f31ef237fc07bda903ed80a83ea))

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.2.3...v3.2.4

## v3.2.3 — 2026-05-02

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.2.3) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.2.3)

- 修复 Android 应用语言选择按钮。 ([50857d52](https://github.com/3252a8/remnawave-minishop/commit/50857d52835ee99003b21b1a8a7b8f893e4b7d23))

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.2.2...v3.2.3

## v3.2.2 — 2026-05-01

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.2.2) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.2.2)

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.2.1...v3.2.2

- 修复应用订阅页面入口按钮消失。 ([e1223f8c](https://github.com/3252a8/remnawave-minishop/commit/e1223f8c57a0eb816c9e9d9f277af4dc0c969b87))

## v3.2.1 — 2026-05-01

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.2.1) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.2.1)

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.2.0...v3.2.1

- 改用新 Telegram OAuth 机制。 ([4de730bf](https://github.com/3252a8/remnawave-minishop/commit/4de730bf5a88d5a355ed614ea362fe1223680a4f))
- 改进 Telegram 机器人菜单。 ([81f51687](https://github.com/3252a8/remnawave-minishop/commit/81f516872671472ea8811accd81c2cf0c5e0c390))
- 修复应用语言选择按钮。 ([d15b1be3](https://github.com/3252a8/remnawave-minishop/commit/d15b1be3b9468e4dbaedcd10dc30888970749929))
- 调整邮件设计，移除标志下方背景。 ([4d0241a0](https://github.com/3252a8/remnawave-minishop/commit/4d0241a0ea8790e7584e6d7261471350c80306f8))

**迁移到新 Telegram OAuth 需要配置机器人和 `.env`。**

## v3.2.0 — 2026-04-30

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.2.0) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.2.0)

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.1.0...v3.2.0

- 应用改用 Svelte，并改进界面。
- 应用支持按 GB 套餐。
- 应用支持 HWID 管理。
- 应用支持试用。
- 为验证码等邮件增加样式。
- 记录邮箱注册、账号合并等日志。
- 其他改进与修复。

## v3.1.0 — 2026-04-27

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.1.0) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.1.0)

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.0.0...v3.1.0

- 实现网页应用／Mini App：统一订阅页面包含连接链接、剩余时间、流量和付款。
- 新增 Telegram Mini Apps `initData`、Telegram Login Widget 及一次性邮箱验证码登录。
- 改进网页付款，新增多个 Platega 按钮。
- 机器人默认仅保留应用和支持按钮，其余操作移到独立命令。
- 加强 Mini App 鉴权、CSRF、CSP 和 webhook 签名验证。
- 准备从 `remnawave-tg-shop` 迁移到新名称 `remnawave-minishop`。

**升级注意：** 容器、卷和 GHCR 镜像已更名，已有部署需要迁移。
