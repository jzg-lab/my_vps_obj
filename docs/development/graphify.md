# Graphify 代码库关系图

<a id="карта-кодовой-базы-graphify"></a>

本文保留上游 Graphify 工具的使用说明；示例中的支付和单订阅实体不代表当前 MVP 已启用这些功能。
本项目的业务范围见[独立服务说明](independent-services.md)。生成关系图与建立 `.codegraph/` 索引是不同操作，本文不代表已要求执行任一种索引。

[Graphify](https://github.com/Graphify-Labs/graphify) 从仓库构建持久化知识图谱：
通过 AST 解析代码，将文档和媒体作为语义节点加入，并将关系标记为实际发现或推断所得。
本项目的结果保存在 `graphify-out/`。

`graphify-out/` 的主要文件有意纳入版本管理，便于快速了解后端、前端、文档、契约和生成物之间的联系，
无需重新通读整个仓库。目录在 `.gitattributes` 中标为 `linguist-generated=true`，
因此 GitHub Linguist 不应将它计入代码库语言统计。
`graphify-out/graph.json` 还被排除在普通文本差异之外，避免机器生成的 JSON 淹没代码审查。

## 目录内容

<a id="что-внутри"></a>

- `graphify-out/graph.html`：交互式关系图。
- `graphify-out/GRAPH_REPORT.md`：文本报告，包含大型节点、节点群、子系统之间的连接及诊断警告。
- `graphify-out/graph.json`：用于查询、路径分析和重新分析的机器可读图谱。
- `graphify-out/manifest.json` 与 `cost.json`：构建元数据。
- `graphify-out/cache/`：本地提取缓存，避免每次重新开始；它保留在 `.gitignore` 中，不提交到仓库。

不要手工编辑这些文件。关系图过期时，从仓库根目录重新生成，
将变化的 `graphify-out/` 文件与引起变化的源代码一并提交，但不包括 `graphify-out/cache/`。

## 何时更新

<a id="когда-обновлять"></a>

当项目架构变化，或出现有助于审查的新关系时，更新 `graphify-out/`：

- 后端、前端或 worker 的大型重构；
- 新增支付服务商、插件钩子、领域事件或 HTTP 契约；
- 文档迁移、开发环境变化或生成物流水线调整；
- 准备安全或架构审查，需要了解子系统之间的调用路径。

小幅文案、本地化或独立测试修改通常不需要更新关系图。

## 安装

<a id="установка"></a>

使用 `uv`：

```powershell
uv tool install graphifyy
graphify install
```

使用 `pipx`：

```powershell
pipx install graphifyy
graphify install
```

Graphify 可通过 tree-sitter 在本地解析代码。需要对文档与媒体进行更深入的语义处理时，可设置 Gemini 密钥：

```powershell
$env:GEMINI_API_KEY = "..."
```

## 重新生成

<a id="перегенерация"></a>

从仓库根目录运行：

```powershell
graphify .
```

运行后检查结果：

```powershell
Start-Process .\graphify-out\graph.html
Get-Content .\graphify-out\GRAPH_REPORT.md -Encoding UTF8 -TotalCount 80
```

如果报告包含诊断警告，先结合上下文判断。
大型仓库中的部分警告可能来自生成或聚合的关系；应关注反复出现的可疑节点、意外循环，
以及本应相互独立的子系统之间出现的依赖。

## 常用查询

<a id="полезные-запросы"></a>

下面保留上游命令示例。前两条自然语言查询分别询问“认证如何实现”和“支付服务商与 Webhook 有什么联系”；查询文本也可改为自己的问题。

```powershell
graphify query "как устроена авторизация?"
graphify query "что связывает платежных провайдеров с вебхуками?"
graphify explain "PaymentProviderSpec"
graphify path "TelegramAuth" "UserSubscription"
```

`query` 适合了解整体，`explain` 用于查看具体节点，`path` 用于检查系统两部分通过哪些文件和实体相连。
Graphify 的回答帮助定位，但不能代替阅读源码和契约测试；标记为 `INFERRED` 的关系应作为待验证的推测。

## 如何审查关系图变化

<a id="как-ревьюить-изменения-графа"></a>

1. 先查看普通代码差异。
2. 打开 `graphify-out/GRAPH_REPORT.md`，检查是否出现意外承担过多职责的节点、不相关区域之间的新连接，或警告数量骤增。
3. 使用 `graphify-out/graph.html` 直观检查较大的架构变化。
4. 不要要求手工修改 `graphify-out/`；应修改源码或文档，再重新运行 Graphify。
