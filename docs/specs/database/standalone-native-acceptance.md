# database 独立运行与原生验收规范（standalone-native-acceptance）

状态：随 DATABASE-002 实现落地（执行合同：docs/plans/archived/002-standalone-native-user-flow.md；
能力依据：docs/plans/evidence/002/native-ui-decision.md 与该计划 §9 复审记录）。
范围：本 app 脱离 OS 装配的独立准备/启动、原生端真实操作验收门与反注入证据合同。
不含行编辑/DDL 写入、远程/加密数据库、多库运维、OS 集成与 Linux 适配
（统一等待 auto-os-distro 的 Nix+COSMIC 基础）。

## 1. 独立准备与启动门（D-01）

- 正式门 `python tests/basic/verify_basic.py --profile vue|vm`（或 `--api-only`）。
  每次运行新建并独占本次的临时目录/随机端口/构建输出；冷准备允许耗时（服务就绪
  有预算），阶段化等待、就绪判定、有界超时、失败非零。
- 错误 tool → 非零退出；目标端口被占 → 本方干净失败且不伤占用者；邻居实例失败
  → 旁观实例不受影响且可继续应答。不依赖 OS 装配或其他 app。

## 2. 进程归属纪律

- 清理只按本次 spawn 树记录的 PID 进行；禁止按端口占用或命令行相似性杀进程。
- 不删除既有 app/框架 target，不停止他人实例；不建 junction/symlink。
- 测试夹具为关闭状态的本次 SQLite 隔离文件（含中文路径目录），避免外部写者使
  hash oracle 误判。

## 3. 调度方只读 oracle（D-03/D-04）

- 主库文件 sha256 与哨兵行：打开→操作→切库→关闭全程前后一致；以独立 sqlite3
  与只读 API 作对照 oracle，不用其代做用户操作。
- 请求间隙文件可重命名/替换（无泄漏锁）；无效路径/坏文件不新建文件、不产生
  ATTACH aux 副文件、不回落演示数据。
- 切库 A→B→A 以内容身份核对（两库不同标识与记录），不看相同默认表名假绿；
  失败的 UI 动作有可见错误且原输入保留；关闭后无旧结果残留，同会话重开需重新
  输入路径并再次查询成功（不承诺自动记住上次库）。

## 4. 反注入敏感性控制（D-05）

- 错库断言反例：受控注入错误断言时总门必须非零——驱动不得靠 Init/state 直写绿。
- Init 注入 hash 护栏：对 src/front/db_store.at 施加 hook 前后 hash 必变且还原后
  复原，证明门在未改 Init 形态上运行（基线 a1fcad3a…）。
- 正常控制：关闭态分支与独立 API oracle 对照一致；无必需 skip/零场景。

## 5. 成功分支门

- 原生端成功分支已补齐：`--profile vm` 59 项全绿（真实输入/树/分页/搜索/NULL/
  Schema/SQL 成功·拒绝·引擎错/坏路径/坏文件/切库/关闭/重开 + D-01..D-05 全电池），
  `--profile vue` 55 项不回归；两端门可重复运行，绑定当次实跑记录的 CLI/tool
  版本与 hash。
