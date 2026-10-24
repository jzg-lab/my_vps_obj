# 身份级断连：r3 隔离验证材料

对应 UC2-R3-PACKAGE、F04、UC-04/05、UA-10/12。本目录保存固定上游的最小
forward VLESS 实验补丁及复现入口，**不替换默认镜像，不构成生产接入或完整协议验收**。

## 冻结来源

本目录的 `manifest.json` 汇总源归档、补丁、许可、依赖锁、工具版本、生成文件与产物
摘要。它是仓库整理后的清单，不冒充原始交接清单。原始 r3 交接为
`/tmp/my-vpn-uc2-identity-scope/artifacts/manifest.json`，SHA-256：
`b5a495e8c4688598e9008599fd012c6a68e3fe93ba7a86986bbbab9a4e88b22d`。
该交接标记为 `isolated-poc-r3-scope-offline`，未构建 bundle；仓库产物摘要另来自主窗口的
`/tmp/my-vpn-uc2-r3-independent-build/artifacts/main-build.json`，SHA-256：
`2e61f693065a39a2a1502adb158bebbdd337fdaa246ab825d1788609a23d0a4f`。
后者标记为 `isolated-poc-r3`：Node 从固定上游归档加累计补丁独立构建，复用已独立重建
且锁摘要相同的 r2 依赖；Xray 直接沿用已独立重建的 r2 产物。这两份来源不能混为同一次构建。

| 项目 | 固定来源 | 源 tar SHA-256 |
| --- | --- | --- |
| Xray v26.7.28 | `5ca6f4b7d4dc20a881d4330e498892697627ec0c` | `45de3ead5186fea442b04c662c554a1ffd1d7bd9093a83410f2edabe74fb766e` |
| Remnawave Node 3.4.2 | `ea7a835485af81ec464ebbf7acaaa7d6dd486a05` | `c8008efb55cc3c569ab9398302649e812711c75d3e4db73a7ad4e03203b25616` |

上游下载地址见清单中的 `sources.*.url`；源码及依赖不入库。两份
[Node 补丁](patches/node-identity-cancel.patch)、[Xray 补丁](patches/xray-identity-cancel.patch)
分别保持冻结 r3 累计补丁和未变的 r2 Xray 补丁完整字节。Node 补丁仅对固定上游干净
源码应用一次，不能叠加到 r2 或再应用增量补丁。补丁 SHA-256 分别为：

```text
bf1af2716ef8d800385af780d11c016245ddb670659fe5901077d9416a1548b7  node-identity-cancel.patch
90076c5b3e6d6609b1ef1742e62e57ac4e63ff4e7fceee5c287b9226fb998abf  xray-identity-cancel.patch
```

[Node 原 LICENCE](licenses/node-LICENCE) 与 [Xray 原 LICENSE](licenses/xray-LICENSE)
均逐字保存自固定源码归档，分别对应上游声明的 AGPL-3.0-only 与 MPL-2.0。
原文标题、日期和版权声明不做替换。本目录不包含预编译二进制、`node_modules` 或源码树。

## 工具与产物

原交接构建工具为 macOS ARM64 上 Go `go1.27.2`、Node `v26.10.0`、npm `11.19.1`、
protoc `33.0`、protoc-gen-go `v1.36.11`。复现脚本严格检查这些版本，不自动升级工具。
protoc 的固定下载地址和 ZIP 摘要见 `toolchain`；Go 与 Node 依赖使用原锁文件，摘要也
在清单中。`go install` 使用明确版本的生成器模块；Node 安装使用
`npm ci --include=dev --ignore-scripts`，确保生产模式构建所需的类型、检查和打包工具仍被安装。

| 覆盖产物 | 容器中的目标 | r3 配对 SHA-256 |
| --- | --- | --- |
| `main.js` | `/opt/app/dist/main.js` | `4896c9fa350cf50fe27dda4fcf4cde883a642ef1712bcab7b48b58ea56e61f0d` |
| `xray-linux-arm64` | `/usr/local/bin/xray` | `25074e2dfad139dfab8d6f4abc89fc16c8c4b2240d78d5a117075076bc897c31` |

Xray 目标为静态 Linux ARM64，保留原命令的 `-trimpath -buildvcs=false`、空 build ID 和
`uc2-identity-cancel` 标记。Node 仅在 `NODE_ENV=production` 下构建，禁止使用会启动应用的
上游开发构建。脚本不运行生成的 Node bundle，也不启动 Docker、数据库或面板 API。

补丁中的 `identity_cancel.pb.go` 是原 protoc 生成产物，不能手改。`build` 会从补丁中的
`.proto` 重新生成到独立目录，与冻结生成文件逐字比较并核对
`18624031253b6cfbbffeade01664dcc026d51740a8aa53c5d7ef11f0d7ad1658`，之后才测试、构建。
离线 `check` 只核验冻结产物与补丁，不声称已执行再生成。

## 离线核验与复现

先由操作者准备清单指定的三个归档，文件名为 `xray.tar.gz`、`node.tar.gz`、`protoc.zip`。
脚本自身不下载这些文件。以下 `check` 只读取本地文件、核对摘要、解压到自动删除的临时
目录、验证并应用精确补丁及核验生成文件摘要，不安装依赖、不编译、不访问网络：

```sh
.venv/bin/python deploy/node-identity-cancel/reproduce.py check \
  --sources /absolute/local/source-archives \
  --artifacts /absolute/local/r3-artifacts
```

`--artifacts` 可省略；提供时必须同时存在两份摘要完全相符的产物。r2 Node、缺失文件、
部分复制或任一不匹配均报错，不能升级标签或仅检查文件名后继续。r3 Node 配上述未变
Xray 才是指定配对；Xray 沿用 r2 本身不属于错误混装。

**仅在主窗口分配构建时段后**，使用不存在且位于仓库外的目录运行：

```sh
.venv/bin/python deploy/node-identity-cancel/reproduce.py build \
  --sources /absolute/local/source-archives \
  --work /absolute/new/reproduction-directory
```

`build` 会安装固定 Go 生成器及锁定的 npm/Go 依赖，可能访问依赖仓库；顺序运行原 r2
四包 race 测试、20 轮重点测试、Xray 构建及 Node 检查与构建。Node 检查明确执行：

- `node --test --test-reporter=tap test/identity-cancel.test.cjs test/identity-scope.test.cjs`
  （冻结套件共 42 项）；
- `npm run typecheck -- --incremental false`；
- Oxfmt/Oxlint 检查八个文件：`src/common/utils/identity-scope.ts`、
  `src/modules/handler/handler.service.ts`、`src/modules/handler/identity-cancel.ts`、
  `src/modules/internal/internal.service.ts`、`src/modules/xray-core/xray.service.ts`、
  `test/identity-fixture.cjs`、`test/identity-cancel.test.cjs`、`test/identity-scope.test.cjs`。

它不复用旧工作目录。只有 PB 再生成一致、测试全通过、锁未变化且两份产物均匹配冻结
SHA-256，才写 `artifacts/verified-build.json`。失败目录和日志保留供排查，但没有成功标记；
不要把部分产物当成新版，也不要为放行修改冻结 hash。离线检查不能替代正式脚本的干净
构建和 live 验收；已执行的构建、隔离实测及证据边界统一见
[实施计划第 14 节](../../docs/implementation-plan.md#本轮本地最终验收)。

## 一次性 Node 接入

原夹具的 `IMAGE` 固定摘要保持不变：
`remnawave/node:3.4.2@sha256:1f97485b4bc7e4944f1ae95cc57d176376813b0022e9567b705f384f1a2e909d`。

主窗口使用既有隔离环境与独占 live 时段，额外设置唯一可选变量：

```sh
QA_SERVICE_OPERATIONS_ADAPTER_DIR=/absolute/local/r3-artifacts
```

仍须显式 `QA_SERVICE_OPERATIONS_LIVE_NODE=1` 并满足原环境校验；本说明不加载或复制私密
env。没有 live opt-in 时不读取该可选变量；未指定适配器时不读取清单、产物或访问 Docker。
这里的无 I/O 保证指适配器入口，普通 opt-in live 场景仍按原夹具执行。

唯一 hook 位于原 `LiveNode.container` 完成创建之后、返回供调用者启动之前，只处理
`node`。它严格要求仓库 `isolated-poc-r3` 清单及上述产物配对；r2 清单、r2 Node 或任一
不匹配产物在 Docker 操作前即拒绝。它先校验并暂存两份产物，再检查本机 Docker、固定 ARM64 base image、新建未启动
状态、精确 run 标签和恢复清单。任何覆盖 `/opt/app/dist/main.js`、`/usr/local/bin/xray`
或其执行别名 `/usr/local/bin/rw-core` 的 mount 均拒绝。

随后复制两份文件并逐个从停止的容器复制回本机，核对**容器内实际字节**和 Xray 执行位；
复核容器仍是同一未启动实例后才返回。任何失败都会抛错，使调用者无法启动这个部分安装
的容器；不热替换，不自动回退到旧内核或 IP 断流。客户端和受控源均不打补丁。

报告和恢复 manifest 的 `execution_adapter` 记录 revision、工具和源版本、原 base image、
覆盖产物摘要、容器文件摘要、安装状态及 `base_image_is_patched=false`。原镜像摘要只能
证明基础镜像，不能冒充已打补丁镜像摘要。失败仍保留报告和原 manifest；清理和恢复仍用
原 `tests.support.service_operations_live_node` 的精确资源流程，不新增批量删除逻辑。

真实验证仍选择原用例，不改判据：

```text
tests/integration/test_service_operations_same_source.py::test_real_node_same_source_service_isolation
tests/integration/test_service_operations_live_node.py::test_real_node_service_operations_and_retained_configurations
```

回退为按原 manifest 删除精确一次性容器及本轮资源；之后从固定原镜像新建不带适配器的
容器。默认镜像、环境文件及共享运行配置没有被更改。

## r3 库存与互斥边界

- 使用现有 SDK 原生 `handler.rawClient.listInbounds({isOnlyTags:false})` 读取内核库存。
  原配置必须包含非空、唯一带 tag 的 forward VLESS 用户 inbound，不能冒用生成的管理 tag。
- 只有精确的 `REMNAWAVE_API_INBOUND` 可排除，且须核验实际 dokodemo proxy 类型、
  `ReceiverConfig`、配置确定的 abstract Unix socket 与无 TCP 端口；`REMNAWAVE_API`
  之类名字本身不获豁免。其余实际 handler 必须是 VLESS，所有预期用户 tag 必须存在，
  额外实际 VLESS handler 也纳入操作范围。
- 空、缺失、重复、无 tag、未知协议、畸形库存或库存 RPC 失败均在身份写入前失败。
  运行期库存失败使就绪失效，须显式启动/重新确认；范围仅在启动或 no-op 验证成功且
  实际库存校验通过后发布。不会因本地用户 hash 已缺失而跳过取消。库存只在内存检查，
  不记录原始库存、凭据或未经清理的解码错误。
- 单条/批量 add/remove 四个入口与 start/restart/stop/shutdown 共用 Node 操作信号量，
  覆盖等待中的 RPC 和本地索引写入；私有锁内辅助方法不重复取锁。慢 RPC/进程操作会
  延迟其他变更，没有新增超时策略。普通同步保留不主动断流的旧 RemoveUser 行为，
  撤销与轮换仍使用 r2 精准取消。
- **这不是远端配置 fence。** 没有单调业务版本、tombstone、内核 generation token、
  持久撤销账本或跨进程锁。晚到的旧完整配置及后续 add/resume 仍可重新引入已撤销身份；
  锁不判断请求是否陈旧/被授权。直接 gRPC、进程替换及不经过受控入口的外部操作不被
  该锁串行化。启动/重新确认失败也不证明旧或新数据面已停止，只代表范围不可信，
  受控身份写入失败关闭。

## 验证范围与限制

- 原交接提供 42 项 Node 离线测试及类型/格式/lint 证据；后续仓库脚本重建及 r3 同源隔离、
  生命周期实测的结果以[实施计划第 14 节](../../docs/implementation-plan.md#本轮本地最终验收)
  为准，不复制阶段性状态。r2 历史结果不能作为 r3 验收证据，固定本机 forward VLESS
  结论也不代表默认 Node 或其他协议通过；默认镜像仍未替换，同源误断风险仍须明确保留。
- 只支持 **forward VLESS POC**；reverse 请求和带非零 XUDP GlobalID 的受跟踪 mux 帧
  会被拒绝，未实现 XUDP 游离/迁移会话。其他协议没有新的精准取消方法；混合协议的
  部分失败不能视为整份服务已撤销。TCP/UDP framing、普通 mux 的离线测试不等于真实
  UDP、WebSocket、TLS/REALITY/Vision/splice、全部第三方客户端或长期负载验收。
- Node 的“只断连接、不删除凭据”接口明确不支持并返回 HTTP 500；显式管理员 IP 维护
  接口及其原插件未改。不能宣传为所有断连入口都已精准化。
- 库存协调限于上述受控 Node 路径，并非对任意并发外部配置写入的原子快照。本 hook
  只证明产物安装，不证明配置或身份已装载。主窗口仍需核查真实内核的目标 VLESS inbound、
  两份用户及 Node 就绪；未知 inventory 不算成功。
- 新 Node 配未打补丁 Xray 会明确失败；旧 Node 配新 Xray 仍可能触发原 IP 清理，因此必须
  两份都在首次启动前完成校验。跨 inbound 部分移除不原子，已完成部分不自动回滚。
- 沿用 r2 的取消成功语义：目标 admission 移除、上下文取消、每个 Close 返回成功或已关闭；它不等待
  所有 goroutine、远端 EOF、内核缓冲区排空或所有 outbound 释放，不保证绝对零超额。
  Close 时持锁可能延迟同 inbound 的其他准入操作。目标真实 EOF、旧配置拒绝以及同源
  另一身份**原长流持续**仍必须通过真实回归，重连可用不能代替。
