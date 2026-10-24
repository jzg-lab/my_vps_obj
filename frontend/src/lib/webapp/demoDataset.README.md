# 演示数据集

`demoDataset.js` 是用于文档演示和本地预览运行时的静态生成快照，不得手改；必须从提前匿名化的数据快照整体重新生成。

这是保留的上游演示数据，不是本项目当前账号、服务、节点或生产库存。独立服务的演示场景由相应 `mockApi` 模块组织，不能把演示数量当成实际验收证据。

当前快照来源记录在 `DEMO_DATASET.generatedFrom`：`tmp/postgres.dump`，创建于 2026 年 5 月 28 日，入库前已经删除个人数据。数据库导出文件本身不提交。

<a id="как-обновлять"></a>

## 更新步骤

仓库未提供原始快照导出器。开始更新前须取得可复现的导出工具及匿名化源数据，不能猜测命令或直接改生成结果。`scripts/generate_dev_mock_seed.mjs` 消费此快照生成通用开发 seed，不是 `demoDataset.js` 的导出器；`scripts/export_settings_manifest.py` 则负责独立的设置清单。

1. 在仓库之外准备新的匿名化快照。
2. 使用生成 `DEMO_DATASET` 结构的同一导出器，从快照重建 `frontend/src/lib/webapp/demoDataset.js`。
3. 检查 `generatedFrom` 的来源、日期和计数已更新。
4. 运行 `npm --prefix frontend run test` 和 `make check`。

如需改动单个值，先修改导出器或源快照，再重新生成整个文件。
