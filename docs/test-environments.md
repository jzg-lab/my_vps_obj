# 可复用测试环境

本文说明测试工具与依赖缓存的生命周期，质量门禁范围由[贡献指南](../CONTRIBUTING.md)决定。
首次接手看[接手指南](handoff.md)；日常开发栈用[项目本地环境](development/project-local.md)，
上游夹具和多版本测试用 [dev-stand](development/dev-stand.md)，不要混用数据库或 seed。

`npm run check:local` 准备可复用依赖并运行完整检查，`npm run qa:local` 调用保留的隔离面板与升级测试工具链。
后者包含上游支付、试用和单订阅场景，不因工具存在就适用于全部独立服务流程。
完整 Windows 门禁需要 Node 24、uv、Python 3.12 和 Linux Docker。带跳过项的单元测试通过，
不等于真实环境验收通过；项目结果只见[实施计划 §14：本轮本地最终验收](implementation-plan.md#本轮本地最终验收)。

## 存储与生命周期

Python 工具与 npm 依赖保存在检出目录外的用户缓存中，缓存键包含依赖清单、平台、架构和 Node 主版本。清理检出目录后，通过目录联接／符号链接重新接入前端依赖。仅成功安装后标为就绪。不得缓存可变测试数据库、`.env`、凭据、源码快照或运行中的服务。

`qa-deps` 镜像只包含依赖与工具，不含产品源码或前端构建。`npm test` 使用容器运行器时每次新建源码快照，执行后删除；原生运行方式见贡献指南。容器测试在 Linux 存储内运行，默认限制 4 CPU／4 GiB。可通过 `MINISHOP_TEST_CPUS`、`MINISHOP_TEST_MEMORY` 和 `MINISHOP_TEST_CACHE_DIR` 调整本机预算。内存不足属于门禁失败，应明确增加容量或串行构建，不能跳过测试。

容器命令默认两小时截止（`MINISHOP_TEST_TIMEOUT`，GNU timeout 语法），之后给 30 秒强制终止宽限。即使主机 shell 被结束，也不会留下无限运行测试。完整环境默认每个应用服务 2 CPU／1 GiB，数据库 768 MiB，Redis 256 MiB；应用服务可用 `MINISHOP_STAND_SERVICE_CPUS`／`MINISHOP_STAND_SERVICE_MEMORY` 调整。每次运行必须使用独立数据库和网络。

本地初始化跨检出目录串行；完整门禁持有每个检出目录的租约，防止两次本地检查并发重建生成文件。强制结束主机进程可能留下小型租约文件。下次运行会指出路径与已结束的所有者：先确认没有门禁仍在运行，再只删除该租约；不得抢占存活进程的租约。

未启动的 `minishop-core-test-runtime-*` 容器只保留镜像，无运行进程，仅占磁盘。带 `minishop.local.keep=true` 的当前保留容器及其仍引用的命名卷不能当作废弃资源。确认没有检查使用目标缓存后，在已核对的本机测试引擎执行项目提供的限定清理：

```sh
npm run test:env:gc
```

不得为此执行全局 `system prune`、`volume prune` 或无项目范围的镜像／容器清理，避免影响其他任务。Docker 标签无法阻止显式强制删除或恢复出厂设置。有意删除缓存后可依 lock 从仓库恢复；额外清理须依据目标清单另行安排，不能把共享引擎中的全部未使用资源视为本项目缓存。保留当前原生缓存，只有没有检查使用时才移除旧键。Git 清理不得超出检出目录，尤其不得递归进入链接的依赖目录。

## 发布与更新

以下保留上游测试运行时的发布参考。`3252a8` 账号、命名空间和上游 GitLab 发布不属于本项目默认操作；接手不需要登录该账号或发布公共镜像。本项目验证使用现有固定 lock，变更依赖或发布方式时另行核对仓库配置。

dev 的依赖输入变化时，GitLab 发布 `docker.io/3252a8/remnawave-minishop-test-runtime`。指纹覆盖 Docker 配方、Python 清单、供应商修复脚本和平台。发布产出含仓库摘要的 lock，须审查并提交；使用时按摘要，不跟随可变 latest 标签。依赖变化会自动使旧 lock 失效。

`npm run test:env:refresh` 在本地更新固定基础镜像包及依赖范围；`node scripts/test_runtime.mjs publish` 显式发布并写入 lock。使用 Docker Hub 用户 `3252a8` 登录。每月及安全公告后审查，必要时更新固定基础摘要；不得原地改写已接受摘要。不同架构须使用匹配 lock，或在本地构建精确配方。离线机器需要已保留的当前镜像和依赖缓存；首次初始化需要联网。

更新准备候选环境，普通运行继续使用已接受 lock。发布前执行 `MINISHOP_TEST_RUNTIME_CANDIDATE=1 npm run qa:local` 验证候选；发布器和 CI 冒烟使用同一候选。发布标签同时包含镜像身份和配方键，包更新不会移动旧的已接受标签。pytest 源快照经 Docker 标准输入传输，CI 无需把自身文件系统挂载进独立 Docker daemon；完整本地 Compose 环境仍要求与引擎共享本地文件系统。

CI 保留全部警告、分支覆盖率、前端断言和完整面板版本矩阵。Playwright 在 CI 使用两个分片、每片一个 worker，本地两个 worker；每次完整运行启动新演示服务。可以容忍缓存导出失败，但构建和测试失败必须终止门禁。
