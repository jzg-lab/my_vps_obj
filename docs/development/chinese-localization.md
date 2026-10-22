# 简体中文与客户端体验（C 包）

本包工作区从 `ace4746328534fdd90d02eb98d85053bf7e4852d` 创建，分支 `codex/phase1-chinese-ux`。不修改业务额度、权限、生命周期或数据库结构。

## 语言路径

- 网站和后端统一使用 `zh-hans`，语言名称为“简体中文”。`zh`、`zh-CN`、`zh-SG`、`zh-Hans` 及 `zh-Hans-*` 输入规范化到该代码；`zh-TW`、`zh-Hant` 不自动视为简体。
- `JsonI18n` 自动读取 `locales/zh-hans.json`，保留 `en`、`ru`。不复制英文文本充当中文，也不改变既有回退顺序。管理员的运行时覆盖仍优先。
- 首次页面通过 URL `lang`、语言 cookie、浏览器语言、默认配置依次匹配。登录后继续使用账号偏好；现有 `/api/account/language` 保存选择并使用户缓存失效，语言 cookie 让刷新前的启动页保持一致。无需新 API。
- 后台继续按需加载 `admin` scope；用户页面使用 `webapp` scope。根页面 `lang` 随当前语言同步，让辅助技术正确朗读。
- 管理员可在现有“默认语言”设置填写 `zh-hans`；本包不替运营者修改部署默认值。套餐名称、品牌、IP、邮箱、凭据和管理员自定义内容保持原样。
- 内嵌教程兼容 Remnawave v1 配置的 `zh` 字段。已有 `localizedInstallValue` 按基础语言读取，无需修改第三方面板或更换 i18n。
- 服务日期继续使用 `Asia/Shanghai`，语言切换不改变业务边界；界面明确标注北京时间。

## 覆盖与持续补齐

已加入用户登录、账号安全、客服、服务目录/详情，以及后台套餐、资源、账号生命周期、开通历史、通用控件、一期设置字段的中文。旧支付和营销业务未因此启用。前端演示构建读取中文资源，测试不能只在翻译函数里模拟中文。

`tests/contracts/test_chinese_locale.py` 检查服务/状态前缀、开放页面中的直接翻译调用和一期设置 manifest；新 A/B 服务键缺中文会失败。全部中文键还要存在英俄基础键，保留占位符计数及富文本标签。动态组合键需在该测试的前缀或对应页面测试中覆盖，不能只写组件 fallback。

新增页面交付步骤：开发者先增加 en/ru 键 → C 补中文 → 扩展上述范围及场景 → 跑 locale contract、类型检查及受影响桌面/手机流程。测试范围不代表整个上游 6,383 键均已翻译。

## v0.13 协作依赖

主窗口在本包执行期间确认了新基准：月度按持久化固定累计检查点分配流量，远端核对成功后再展示；模板额度更新会影响同模板所有已开通服务的当前与未来额度，保留用量及价格/到期/资源快照；计数异常只能按准确核对结果恢复。

本分支尚未包含 A/B 的业务实现。不要单独发布共同起点的“模板变更仅影响以后开通”提示。收到 A 的基础键后，必须同步替换中文批量影响提示与周期说明并重验；不能据本包的界面测试宣称新规则已经实现。B 的连接交付入口和真实导入步骤同样需集成后验证。

## 已运行证据（2026-10-23）

- 第一批后端全套：5,585 项通过、45 项条件跳过、630 个子测试通过；未设置真实 PostgreSQL/面板/Node 联调变量。
- 第一批前端静态检查通过：runes、ESLint、Svelte/TypeScript、格式。语言相关 15 项单元测试通过。
- 独立演示构建及中文 Playwright 4 项通过：1440px、390px，切换/刷新、服务日期、服务详情、套餐下拉/表单、资源登记、账号删除确认、历史与设置搜索。截图保存在当前工作区的 `frontend/test-results/`；包含明确的演示业务名称和示例 IP。
- 第一次浏览器失败为测试选中了语言与主题两个同类按钮，以及未填完整必填字段导致业务校验未触发；修正选择器和测试输入后通过。没有为过测修改业务组件。
- 待完成：更多后台页面中文核对、客户端推荐/教程配置、最终全矩阵、A/B 新键及真实导入验收。以上是检查点，不是整个 C 包验收完成。

复现（在隔离工作区，Python/Node 依赖已可用时）：

```sh
python -m pytest -q tests/contracts/test_chinese_locale.py tests/unit/test_chinese_language.py tests/unit/test_webapp_account_language.py
npm --prefix frontend run check
npm --prefix frontend test -- src/lib/webapp/i18n.test.ts src/lib/webapp/installGuideRuntime.test.ts
npm --prefix frontend run test:e2e -- chinese-services.spec.ts
```

浏览器运行器自动选择空闲本地端口；演示不连接数据库或面板。生成产物留在独立工作区。真实节点、订阅导入、长连接停用和客户端协议兼容性均未验证，不使用现用 3x-ui 资源替代。
