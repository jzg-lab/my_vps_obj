# 备份

<a id="бэкапы"></a>

Minishop 在 worker 容器中自动创建 ZIP 备份，将归档保存在服务器并发送到 Telegram。可从管理后台下载归档，上传至其他服务器，恢复数据库、已安装插件和主题。控制进程会在恢复期间自动停止 backend 和 worker，完成后重新启动。

> 本页记录上游备份能力及其安全要求，不表示本项目已经完成生产迁移或真实 Node 验收。本项目开发和验收使用[隔离开发环境](../development/project-local.md)，不得以现有生产节点作为测试资源。

## 归档包含什么

<a id="что-попадает-в-архив"></a>

归档创建于 `BACKUP_DIR`，默认是 `shop-data` 数据卷中的 `data/backups`。

典型文件名：

```text
minishop-20260527-12-00.zip
```

归档内容：

- `database/<POSTGRES_DB>.dump`：供 `pg_restore` 使用的 custom 格式 `pg_dump`。
- `database/tariffs.json`：`TARIFFS_CONFIG_PATH` 指向的套餐目录，文件存在时包含。
- `compose/`：`docker-compose.yml`、`.env` 及相邻配置所在目录的快照。
- `config/themes/`：已安装的用户主题。
- `config/plugin-store/`：已安装签名插件的所选版本、状态及受信任发布者密钥。
- `manifest.json`：创建日期、`minishop_version`、`database_metadata.migration_ids`（完整已应用迁移列表）、PostgreSQL 版本、不含凭据和查询参数的面板地址、数据库信息、Compose 快照及警告。

转储和迁移列表使用同一个导出的 PostgreSQL 快照，确保迁移历史对应归档中的数据。ZIP 格式版本与应用版本是两个不同字段。兼容不含新元数据的旧 ZIP，其迁移历史从恢复后的转储读取。

Compose 目录未挂载或不可访问时，worker 不会让整个备份失败：仍创建数据库转储归档，并在 `manifest.json` 中记录警告。

## 大归档与分片发送

<a id="большие-архивы-и-отправка-частями"></a>

不超过 45 000 000 字节的 ZIP 作为单个文档发送。更大的归档自动拆为每片不超过
45 000 000 字节的二进制文件，同时发送 `<archive>.zip.parts.json`，记录分片顺序、
大小及分片和完整 ZIP 的 SHA-256。Telegram 每组最多发送 10 个文件，包括清单。
剩余只有一个文件时单独发送，保留目标聊天及话题／线程。
Telegram 因请求大小拒绝整组时，逐个重发；较小 ZIP 因大小被拒绝时，worker 尝试更小分片。

完整 ZIP 保留在 `BACKUP_DIR`，可从管理后台下载。分片仅用于投递，成功或失败后
均从临时目录删除。即使投递失败，也执行完整 ZIP 的本地保留数量限制。
网络错误和 `retry_after` 仅重试当前未投递组，最多三次；耗尽重试后，通知显示已确认文件数。
Telegram 接受请求后网络断开可能导致整组重复投递，请核对名称和 SHA-256。

通过网页恢复时，打开**系统 → 备份 → 上传**，同时选择**同一归档的清单和全部分片**。
选择顺序无关：服务器按清单重建 ZIP，验证分片及完整 ZIP 的大小和 SHA-256，
再执行常规备份完整性检查。完成的归档出现在列表中，选择后按标准流程恢复数据库或 Compose。
使用分片无需安装 CLI 或手动拼接。

不能混合不同备份的分片、附加多余 ZIP，或选择不完整的文件集合。
管理后台先检查文件列表和大小，服务器额外验证 SHA-256。
损坏的集合不会发布归档，失败或上传中断时也会清除临时文件。
原始 ZIP 总大小上限为 2 GiB；单 ZIP 的上传方式不变。
从管理后台下载任何备份，始终返回**一个完整 ZIP**。

手动创建时若 Telegram 投递失败，后台仍保留“创建成功”的结果并显示警告，
完整 ZIP 可供下载和恢复。

如需用命令行拼接，先将全部分片和清单下载到同一目录：

```bash
python scripts/join-backup.py /path/to/minishop-YYYYMMDD-HH-MM.zip.parts.json
```

工具验证每个文件及原始归档的 SHA-256，再原子地在清单旁创建 ZIP。
不会覆盖已有文件；其他输出路径使用 `--output`。
缺少或损坏分片时，不会留下完成的 ZIP。拼接后可上传管理后台，
或交给标准 `scripts/restore-backup.sh`。单个 `.partNNNN` 不是独立 ZIP，不能直接恢复。

重新投递时，从管理后台下载完整 ZIP，可通过 `bot.services.backup_parts.split_backup`
再次拆分；同一 ZIP 的分片具有相同名称和 SHA-256。不要拼接不同归档的分片。
重新创建备份会生成新 ZIP，必须使用新 ZIP 的全部分片及对应清单。

Compose 快照默认排除 `plugin-store`、`themes`，以及 Compose 目录内已配置的主题和插件存储路径。
已安装插件的所选版本和受信任发布者密钥单独保存在 `config/plugin-store`；
已安装主题和回退版本保存在 `config/themes`。新归档不包含已删除主题／插件、
临时导入和孤立软件包；已禁用但未删除的插件仍保留。
其余 `data` 不排除，消息图片、标志及其他用户文件配置仍进入备份。
旧 ZIP 不会自动缩小；如需保留软件包历史用于运维回退，请使用独立存储。

## 配置

<a id="настройка"></a>

主要参数位于管理后台的**系统 → 设置 → 备份**。

已配置且适合接收备份的 `LOG_CHAT_ID` 时，最小 `.env` 为：

```env
BACKUP_ENABLED=True
```

需要发到独立聊天或话题／线程时，仅添加所需变量：

```env
BACKUP_CHAT_ID=-1001234567890
BACKUP_THREAD_ID=123
```

其他备份变量通常无需写入 `.env`：`BACKUP_INTERVAL_SECONDS=3600` 在 12:00、13:00 等整点执行；`BACKUP_LOCAL_RETENTION=100` 保留最近 100 个 ZIP；`BACKUP_COMPOSE_ENABLED=True`、`COMPOSE_BACKUP_SOURCE=.` 和 `COMPOSE_RESTORE_MODE=rw` 已符合标准 Compose 场景。

`BACKUP_CHAT_ID` 指定接收归档的 Telegram 聊天，留空使用 `LOG_CHAT_ID`。话题／线程可指定 `BACKUP_THREAD_ID`，留空使用 `LOG_THREAD_ID`。

每个归档包含 `manifest.json`，记录各文件的 SHA-256 和大小，用于检查损坏及内容是否与清单一致。

归档不绑定当前实例、`BOT_TOKEN` 或服务器。只要目标支持归档格式且完整性检查通过，即可上传到其他服务器恢复。

## 挂载 Compose 目录

<a id="mount-compose-папки"></a>

标准 Compose 文件有两个挂载：

- `worker`：`${COMPOSE_BACKUP_SOURCE:-.}:/app/compose-source:ro`，只读，用于创建快照。
- `backend`：`${COMPOSE_BACKUP_SOURCE:-.}:/app/compose-source:${COMPOSE_RESTORE_MODE:-rw}`，读取归档列表，并可从管理后台恢复 Compose 目录。

`COMPOSE_BACKUP_SOURCE=.` 表示当前 `docker-compose.yml` 所在目录。Compose 位于其他位置时，应填写宿主机绝对路径。

后台手动创建备份在 `backend` 容器中执行，定时自动备份在 `worker` 容器中执行。两个容器都必须可见 `/app/compose-source`。手动备份有 Compose 目录而自动备份没有时，在更新 Compose 后重建 worker：

```bash
docker compose up -d --force-recreate worker
docker compose exec worker ls -la /app/compose-source
```

`migrate`、`backend` 和 `worker` 还必须在 `/app/data` 看到同一数据源。
管理后台读取当前 Compose 文件；三个服务的源数据卷或绑定挂载不同，或有服务缺少挂载时，
显示 `data_mount_mismatch` 配置错误。修复前不要修改套餐、翻译及其他文件设置，
因为不同进程可能读取不同版本的数据。

禁止从容器恢复 Compose 文件时，设置：

```env
COMPOSE_RESTORE_MODE=ro
```

此时仍可恢复数据库，但恢复 Compose 目录会返回明确的不可写错误。

## 从管理后台恢复

<a id="восстановление-из-админки"></a>

打开**系统 → 备份**，可执行：

- 手动创建新备份，无需等待下一次计划任务。
- 选择 `data/backups` 中已有归档。
- 下载所选归档，以迁移到其他服务器。
- 手动上传 ZIP。
- 选择恢复“数据库”或“Compose 目录”，两种操作分开执行。
- 输入所选归档的准确文件名，确认后启动恢复。

手动创建与定时任务使用同一机制：执行 `pg_dump`、加入 Compose 快照、保存 ZIP 到 `BACKUP_DIR`、发送到 Telegram，并执行本地保留策略。手动运行期间使用共用 Redis 锁，避免与计划备份或恢复重叠。

选择数据库后，后台创建恢复任务并显示状态。控制进程停止 backend 和 worker，
验证归档和插件签名，将数据恢复到独立数据库，切换数据库后自动重启进程。
期间 API 可能暂时返回错误，页面会继续查询状态。切换前发生错误时，原数据库和插件文件保留，
应用重新启动。若切换结果不确定，进程保持停止，直到人工检查日志。
此流程要求 backend 和 worker 共用 `BACKUP_DIR`，并使用 Core 镜像的标准 `plugin_launcher.py`。
外部数据库客户端需另外停止。

新服务器 `PANEL_API_URL` 与归档记录不同时，后台显示两个地址，并要求选择如何处理用户绑定。
可保留旧绑定供手动核查，或确认在当前面板上重新验证。后者只清除旧面板地址标记，
数据库中的用户 ID 保留；下次连接前，MiniShop 会将账号身份与面板数据核对。
旧归档可能没有原面板地址。只有目标面板确实包含所需账号时，才确认重新验证。

手动 HWID 限制、额外设备和其他订阅设置存于数据库，包含在 `pg_dump` 中。
外部 Remnawave 面板状态不在 ZIP 内；迁移面板本身时，需单独迁移其数据，
再核对绑定和限额。

数据库与 Compose 文件分开恢复，因为源服务器配置可能包含不同域名、密钥、端口和数据卷路径。
恢复 Compose 目录不会让已运行容器自动应用新设置；检查文件后需更新容器。
旧归档没有 `config/plugin-store/` 时，应在恢复数据库前为目标服务器安装所需插件，
或在升级后的源服务器重新创建归档。

Compose 文件会覆盖当前目录。替换前，backend 在其他归档旁创建当前 Compose 目录的恢复前快照：

```text
minishop-pre-restore-YYYYMMDD-HH-MM.zip
```

恢复 Compose 目录后，重启所需服务，让 `docker-compose.yml`、`.env`、Caddyfile/Angie/Nginx 配置等文件的修改实际生效：

```bash
docker compose up -d --build backend worker
docker compose ps
```

代理配置发生变化时，重启对应服务（`caddy`、`angie`、`nginx`、`newt`）。

## 恢复前的归档检查

<a id="проверка-архива-перед-восстановлением"></a>

backend 在恢复前验证：

- 文件必须是有效 ZIP。
- `manifest.json` 必须属于 `remnawave-minishop`，且格式版本受支持。
- 各文件 SHA-256 和大小必须与清单一致。
- 服务器端所选文件必须位于 `BACKUP_DIR` 内，拒绝 `../backup.zip` 等路径。
- ZIP 内路径不能为绝对路径，不能包含 `..`、`\`、空路径段或重复项。
- 拒绝文件数、大小或压缩比异常的归档，包括 ZIP 炸弹。
- 恢复数据库需要 `database/*.dump` 或 `database/*.backup`。
- 恢复 Compose 需要 `compose/` 内文件。
- 目标目录存在且可写时，才开始恢复 Compose。
- 备份和恢复共用一个 Redis 锁，防止同时执行。
- 必须准确重新输入所选归档名称。
- 数据库只恢复到独立空库，当前库在切换前后都保留。

这些检查防止误传无关文件、ZIP 路径穿越及损坏归档。为支持跨服务器迁移，验证不绑定实例密钥。它不验证来源可信度；不要恢复来源不受你控制的归档。

## 迁移到其他服务器

<a id="перенос-на-другой-сервер"></a>

实例间迁移数据库：

1. 在旧服务器创建备份，从后台或 Telegram 下载 ZIP。
2. 在新服务器的**系统 → 备份**上传归档。
3. 选择数据库，输入准确归档名并启动恢复。后台显示进度，完成后进程自动重启。
4. 检查插件、主题和健康检查。旧数据库及插件文件保留用于回退。
5. 需要 `.env` 和代理配置时，单独恢复 Compose，核对目标服务器设置并更新容器。

迁移 Compose 目录时，核对域名、令牌、`WEBHOOK_BASE_URL`、`SUBSCRIPTION_MINI_APP_URL`、
绑定端口及数据卷／挂载路径，新服务器可能不同。不要在恢复数据库时自动套用旧 Compose，
它可能用旧镜像启动已经升级结构的数据库。

## 备用方式：通过维护命令恢复数据库

<a id="резервный-вариант-восстановление-бд-командой-обслуживания"></a>

使用**目标版本**的镜像及同一发行版的脚本。归档必须位于共用数据卷的 `BACKUP_DIR`。
在 Docker Compose 宿主机的安装目录运行，需要 Bash 和 `flock`。
没有 Git 检出目录的安装，应将目标发行版的 `scripts/restore-backup.sh` 按相同路径保存到安装目录。

```bash
bash scripts/restore-backup.sh minishop-YYYYMMDD-HH-MM.zip
# 自定义 Compose 配置：
bash scripts/restore-backup.sh minishop-YYYYMMDD-HH-MM.zip --env-file .env -f docker-compose.yml
```

执行顺序：

1. 停止应用前检查 ZIP 和校验和。
2. 停止 `backend`、`worker` 和 `migrate`，确认当前数据库没有其他连接。
3. 禁止当前数据库的新连接，并从 `template0` 创建独立空库。
4. 使用 `pg_restore --list` 检查转储，再以 `--single-transaction --exit-on-error --no-owner --no-privileges` 恢复，不使用 `--clean`，也不覆盖当前数据库结构。
5. 有清单迁移历史时与其核对。拒绝未知迁移，包括未安装插件的迁移；不支持降级。只应用缺少的 Core 和已安装插件迁移。
6. 检查模型表、列、PostgreSQL 索引和约束，校正 serial 序列。先恢复数据，再创建新表和应用迁移。
7. 准备归档中的套餐目录；归档缺少时保留当前目录。在同一事务内原子重命名两个数据库，旧库保留为 `minishop_previous_<id>` 并禁止连接，新库取得原连接名称。
8. 仅在成功后使用配置的镜像启动 backend/worker，并等待健康检查。

需要数据库所有者权限和 `CREATEDB`（标准 Compose 用户具备）、访问服务数据库 `postgres`
的权限，以及容纳两个完整数据库的磁盘空间。外部客户端及独立应用副本也必须停止。
PgBouncer 和非标准角色／权限需单独检查配置。恢复成功不代表已验证所有第三方插件的数据语义。

出错时服务保持停止。切换前原库不变，失败候选库保留用于诊断。
命令写入 `BACKUP_DIR/restore-<id>.json`，记录数据库名、操作状态和文件路径；旧套餐目录保留在旁边。
进程异常结束时，应将日志与 `pg_database` 核对，因为日志写入与 PostgreSQL 操作不在同一事务。
数据库及其对应套餐目录都检查完成前，不要启动应用。

成功切换后如需回退，停止 backend/worker/migrate，保存新库并将其改名为空闲名称，
将日志中的 `previous_database` 改回原名。两个重命名必须从服务数据库 `postgres`
在同一事务内完成，且不能有活跃连接；为回退后的库允许连接
（`ALTER DATABASE ... ALLOW_CONNECTIONS true`）。恢复 `previous_tariffs`
（原本没有套餐目录时则删除），选择与原库对应的镜像，再启动服务。
只有核验结果后才手动删除旧库和失败候选库，脚本不会删除它们。

## 变量

<a id="переменные"></a>

完整参考见[环境变量](../configuration/env-vars.md#кеши-rate-limits-и-worker)。主要键如下：

| 变量 | 用途 |
| --- | --- |
| `BACKUP_ENABLED` | 启用定期备份。 |
| `BACKUP_CHAT_ID` / `BACKUP_THREAD_ID` | Telegram 归档投递目标。 |
| `BACKUP_INTERVAL_SECONDS` | 执行间隔，默认 `3600`。 |
| `BACKUP_LOCAL_RETENTION` | 服务器保留的最近归档数量。 |
| `BACKUP_DIR` | ZIP 归档目录。 |
| `BACKUP_COMPOSE_ENABLED` | 添加 Compose 快照。 |
| `COMPOSE_BACKUP_SOURCE` | 挂载到容器的 Compose 目录宿主机路径。 |
| `COMPOSE_RESTORE_MODE` | `rw` 允许后台恢复 Compose，`ro` 禁止写入。 |
| `BACKUP_PG_DUMP_PATH` / `BACKUP_PG_RESTORE_PATH` | 容器内 `pg_dump` 和 `pg_restore` 的路径。 |

## 用户主题

<a id="пользовательские-темы"></a>

备份将 `WEBAPP_THEMES_DIR` 保存到 `config/themes/`，包含已安装主题目录、
当前软件包及回退版本、所有者设置和手动主题。
排除已删除主题、孤立软件包、临时导入和内部快照。
已删除主题文件可能暂时留在服务器供已打开页面使用，但不会加入新备份。
恢复数据库时，验证软件包后恢复主题；没有此部分的旧归档不会修改主题。
详情见[主题存储](webapp-themes.md#хранение-и-резервные-копии)。
