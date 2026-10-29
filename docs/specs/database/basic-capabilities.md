# database 基本能力规范（basic-capabilities）

状态：随 DATABASE-001 实现落地（r2 执行合同：docs/plans/001-real-sqlite-browser.md；
能力依据：docs/plans/evidence/001/capability-decision.md）。
范围：真实只读 SQLite 文件浏览与查询。不含行编辑、事务写入、数据迁移、远程数据库、
账号管理、可视化建模、Linux 适配（A 类统一等待 auto-os-distro 的 Nix+COSMIC 基础）。

## 1. 用户任务（本版支持的全部）

- T1 打开：用户输入一个本机 SQLite 文件路径，应用展示其真实身份（文件名、表/视图/索引计数）。
- T2 浏览：从对象树（表/视图/索引，含中文标识符）选择对象，查看真实列（PRAGMA table_info
  的列名/类型/NOTNULL/默认值/PK）与真实行（分页 10/25/50、列排序白名单、全列 LIKE 搜索）。
- T3 结构：查看所选表/视图的列定义、索引清单与 DDL 原文（sqlite_master.sql）。
- T4 查询：执行单条只读 SQL（SELECT / 只读 CTE），得到引擎真实列名、行与 NULL 标注
  （NULL 单元格显示为 "NULL"）；超过 1000 行显式截断并标注（样本值，非承诺上限）。
- T5 切换/关闭：关闭当前文件或直接打开另一文件；结果集随文件身份确实更换。

## 2. 数据与错误合同

- 连接为**每请求打开→RAII 关闭**：后端无跨请求连接状态；请求间隙文件锁必释放
  （验收以"请求间隙可重命名文件"为观测）。
- 打开失败可区分且无副作用：`empty_path` / `file_not_found`（绝不调用 sqlite.open——
  引擎对缺失路径会静默建文件）/ `not_a_database` / `readonly_setup_failed`。
- 查询失败可区分：守卫拒绝 `rejected`（empty_statement | multi_statement | not_readonly |
  forbidden_keyword:*）与引擎错误 `query_failed`（错误原文呈现，如 "no such table: x"）。
- 绝不假成功：任何失败都不返回 ok=true，也无演示数据兜底；空结果与失败以 ok/err_code 区分。

## 3. 只读不变式（三层，缺一不可）

1. 语句守卫：去引号/注释感知的单条语句；首 token ∈ {SELECT, WITH}；全文拒绝
   pragma/attach/detach/load_extension（query_only 翻转与挂载旁路）。
2. 引擎强制：每个连接先 `PRAGMA query_only=ON`——一切写路径（INSERT/UPDATE/DELETE/
   DDL/VACUUM/对 attached 库写/数据变更 CTE）由 SQLite 以只读错误拒绝。
3. 验收 oracle：V-03 以文件 sha256 前后不变 + 哨兵行值不变为最终裁判，不采信 UI 标签。

## 4. 生命周期与双端

- 大结果：浏览分页有界（页大小 ≤200）；控制台 >1000 行截断并标注 truncated。
- 句柄：查询失败/切库/关闭不泄漏文件锁（每请求 RAII）。
- 双端：vue（Playwright 驱动，verify_basic.py --profile vue 全链路 21 项）与
  vm（VM 解释器内以 Init 自驱钩子确定性执行同一链路——tests/basic/tools/
  vm_e2e_hook.py 临时改写 .Init，状态经 AutoUI MCP autoui_state 读取；注入式
  21 项电池为环境安静时的复验入口）完成 打开→浏览→错误→切库。

- NULL 单元格统一显示为文本 "NULL"（与字面 "NULL" 值视觉不可分；API 层以独立
  nulls 标志区分，oracle 比对不受影响）。
- 重复输出列名由引擎去重（如 `id:1`），界面按引擎给定名展示。
- 非本地路径、加密库、非文件 SQLite URI、超过内存预算的结果集均不在本版合同内。
- 发射器已知限制（G-4，见 capability-decision §3）：字符串 sub 为字节切片等——
  实现已规避，后续 SDK 修复不改变本合同对外语义。
