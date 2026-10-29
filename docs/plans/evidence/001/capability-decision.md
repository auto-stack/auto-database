# DATABASE-001 T-01 能力决策：只读 SQLite 浏览的接口合同（capability-decision）

日期：2026-10-29 · 执行：DATABASE-001 r2 work（goal 会话）· 检出：`D:/autostack/auto-database`（独立开发 clone，main）
结论先行：**当前 auto-lang SDK（a2r-std rusqlite bundled + VM FFI）足以实现真实只读 SQLite 浏览器**，
无需在 app 手写 Rust 或改生成代码。只读由三层保障：①应用层单语句+关键字守卫（快速、可读错误），
②`PRAGMA query_only=ON` 引擎级强制（实证拦截全部写路径，含 attached 库），③验收哈希 oracle。
任意 SELECT 的真实列名与 NULL 区分用「TEMP VIEW 描述 + 派生表包装」纯 SQL 协议取得（实证通过）。
本文件为本计划依赖的能力合同与工具链缺口登记，供 T-02..05 与复审引用。

## 1. 工具链（实际版本，本机实测）

| 组件 | 版本/来源 | 状态 |
|---|---|---|
| auto CLI | `auto 0.1.0+v0.0.20-117-g873fa23`（`D:/autostack/auto-man/target/debug/auto.exe`） | 可用 |
| 后端服务 | `auto service --server rust --back-port 17839`（本仓 pac.at `api:"rust"`, `back_port:17839`；release 后端 `auto-database-back.exe`） | 实测可用 |
| a2r-std | auto-lang 工作区当前源（rusqlite bundled；`sqlite/fs/json/env` 模块） | 可用 |
| 首次构建 | 全新 rust-workspace 冷编译约 10–20 分钟（auto-lang-core/auto-ui/iced/wgpu 全量）；后端 crate 增量约 12–16s | 已记录 |

基线核对：计划冻结基线 `85fb35db`；执行开始时 HEAD `55c4ece`（仅计划文档修订），工作树 clean、无他人 WIP。

## 2. SDK 接口面（源码核实 + 应用内探针实证）

`a2r-std/src/sqlite.rs` 与 VM FFI 仅有：`open / exec / query / last_insert_rowid / last_error`。
`open` 失败**静默回退内存库**；`query` 把一切单元格转 `str`（NULL→""，BLOB→"<N bytes>"）。
无只读打开标志、无列名/类型元数据、无显式 close（a2r RAII drop）。

探针：`src/back/probe.at`（`AUTO_DB_PROBE=1` 门禁 + `AUTO_DB_PROBE_DIR` 隔离目录，经
`/api/probe/*`）；夹具 `tests/basic/fixtures/make_fixtures.py`（basic_a/basic_b/garbage，
含中文表名列名、NULL、Unicode、1200 行、哨兵行）。原始输出：
`docs/plans/attachments/001/t01-probe-outputs.txt`（sha256 `bde999ee…c42e`，local-only）。

| # | 探针 | 实测结果 | 设计决定 |
|---|---|---|---|
| P1 | open 不存在路径 | **静默创建空库文件**，无错误 | open 前必须 `fs.exists` 预检；不存在→明确报错不建文件（V-01） |
| P2 | open 非数据库文件 | open 惰性成功；首查 `sqlite_master` 报 `file is not a database` | 损坏检测=exists 预检 + sqlite_master 试读 + 错误快照（V-02） |
| P3 | query_only 引擎强制 | INSERT/UPDATE/DELETE/CREATE/DROP/VACUUM 全部 `attempt to write a readonly database`；写 CTE 直接语法拒绝（bundled 版不支持数据变更 CTE）；哨兵值不变 | 引擎级只读合同成立（AC-03 核心层②） |
| P4 | 经 query() 翻转 query_only | **翻转成功且随后 INSERT 落库**（count 1→2）——写可经 query() 通道穿透 | 关键字守卫必须存在且拦截 `pragma`（层①必要性实证）；用户 SQL 只走 query() 不走 exec |
| P5 | query_only 下 ATTACH | ATTACH 本身放行并对 attached 库**建文件**；对 aux 库写入被引擎拦截；主库可读 | 守卫拦截 `attach` 关键字（防意外文件副作用）；引擎层兜底已足够 |
| P6 | schema 内省 | sqlite_master 全对象（含中文表）；`PRAGMA table_info/index_list/index_info` 真实列名/类型/NOTNULL/默认值/PK；DDL 原文；全部在 query_only 连接上完成 | T-03 schema 页与表浏览用纯 SQL 实现，无需 SDK 扩展 |
| P7 | describe+wrap 协议 | TEMP VIEW `SELECT * FROM (<user sql>)` + `table_info` 得**真实列名**（表达式列、CTE 内层、中文全通）；派生表包装 `[col], [col] IS NULL` 得**NULL 标志**（实证逐行正确）；重复列名引擎自动改 `id:1`；非 SELECT 视图体语法拒绝 | 控制台列名+NULL 合同可达成（AC-01/02），重复列名记为已知边界（显示引擎给出的去重名） |
| P8 | 多语句 | query() 仅执行第一条，尾随语句被忽略（尾随 DELETE 未执行） | 引擎侧天然单语句；守卫仍拒绝多语句以给出明确错误（V-03） |
| P9 | 大结果 | 1200 行单查询全量返回；LIMIT/OFFSET 分页正确 | 浏览分页 10/25/50；控制台结果超 1000 行显式截断并标注（非承诺上限） |

## 3. 工具链缺口登记（具名 owner + 规避，均不阻塞本计划）

| # | 缺口 | 证据 | 规避（本仓实现） | owner / 关闭条件 |
|---|---|---|---|---|
| G-1 | `sqlite.last_error()` 为**进程级全局且成功不清空**——错误文本可能是陈旧值（P4/P7 连续操作实证） | t01-probe-outputs（readonly_flip 错误文本与 count 矛盾；describe 后残留语法错误） | 每个错误敏感操作前跑「金丝雀失败查询」快照基线文本，操作后对比：文本变化⇒本次失败且取新文本；结构信号（fs.exists、恒 1 行查询返回空）优先 | auto-lang（sqlite per-connection error 通道）；落地后可移除金丝雀 |
| G-2 | 无只读打开标志、open 静默回退内存库 | P1/P4 | exists 预检 + query_only=ON + 守卫 + 哈希 oracle（三层，见 §4） | auto-lang（`open_readonly` 类接口）；落地前本合同不依赖 |
| G-3 | query 单元格全转 str、无列元数据 | P7 | describe+wrap 协议（§4-D）；数值仍以字符串呈现（SQLite 动态类型下与 oracle 比对按文本+类型标注） | auto-lang（typed query/columns API）；非阻塞 |
| G-4 | a2r 发射器字符串语义三连：`str.sub` 为字节切片且越界/非边界即 panic（stdlib 文档称 clamp，不符）；`len()`/`char_at` 按字符；`str.find` 需第三参 start（签名漂移）；`str.reverse`/`fs.size`/`fs.filename` 无发射映射 | guard_sql 首版多次 E0308/panic（svc-err 日志） | 守卫改 char_at 码点整型+哈希比对；全文件禁用 sub；文件名自算；detail 直读全局错误 | auto-lang（sub 语义对齐/补映射）；已规避，不阻塞 |
| G-5 | 生成的 HTTP 客户端/VM FFI 解码含 **≥2 个数组字段** 的响应结构失败（vue 侧静默错型 `Vec<String>`；VM 侧成功路径崩溃） | TableData/SchemaResult 原三/双数组形态 VM 崩、vue 错型 | 契约 v2：所有响应至多一个数组字段（columns/indexes 拆独立端点；cells 值,标志交错；query 列名头+ncols） | auto-api-gen（多数组响应解码）；契约 v2 已落地 |
| G-6 | 前端 widget 的 Init 不会自动触发 store 的 Init——必须显式转发（`.Init -> { store.Init() }`），否则 store 侧初始化逻辑静默不执行 | VM E2E 钩子初版 vmE2E 恒空；补转发后立即生效 | app.at 已补转发（真实 bug 修复） | auto-ui 文档/生成器约定澄清；已规避 |
| G-7 | VM 前端 store 无法读取进程环境（`use auto.env`/`env.get` 恒空）；VM MCP `autoui_snapshot` 第二次调用只返回头行；`autoui_type/autoui_action` 在高负载下偶发丢事件 | Init 钩子 env 版 vmE2E 恒空；ps 探针空快照；注入重试才稳 | VM 验证走 `tests/basic/tools/vm_e2e_hook.py`（Init 内确定性执行全链，状态经 MCP 读取）；快照复用首次结果 | auto-lang/auto-ui（VM env 通道、快照稳定性）；已规避 |

其他观察（非阻塞）：a2r 发射器对 `str` 参数只对**局部变量**插引用，函数调用结果直传 `str` 形参
会 E0308（probe.at 首版编译实证）——约定：先绑局部变量再传；`fs.delete` 有同 todo 仓 G-3 的
E0382 形态风险，本仓避免在语句位直接调用。

## 4. 据此冻结的 DATABASE-001 只读协议（v1，T-02/T-03 实现合同）

- **打开（open）**：`fs.exists` 预检（缺失→`file_not_found`，绝不 open）→ open → 金丝雀错误快照 →
  试读 `sqlite_master` 计数（错误→`not_a_database`/原样错误文本）→ `exec("PRAGMA query_only=ON")`
  → 返回文件身份（路径、大小、表/视图/索引计数）。后端**无跨请求连接状态**：每个请求
  open→用→RAII 关闭（AC-04 句柄生命周期天然可观测：请求间隙文件锁必释放）。
- **只读三层**：①守卫（去注释/字符串感知的单语句判定；首 token ∈ {SELECT, WITH}；全小写扫描
  拒绝 `pragma|attach|detach|vacuum|load_extension|insert|update|delete|drop|create|alter|reindex`
  出现在语句任意处）→②query_only=ON 连接（引擎拒绝一切写）→③验收哈希 oracle（V-03）。
- **表浏览（table_data）**：列模型来自 `table_info`；数据 SQL 由本仓生成：
  `SELECT [c], [c] IS NULL … FROM [t] ORDER BY [sort] LIMIT n OFFSET m`，计数 `SELECT COUNT(*) …`
  （search 用 `LIKE … ESCAPE '\'`，参数经单引号翻倍转义；标识符经 `[]` 引用，`]]` 处理）。
- **控制台查询（query）**：守卫 → desc 连接（无 query_only，仅 `CREATE TEMP VIEW`/`table_info`/
  `DROP`，绝不执行用户 SQL 主体；非 SELECT 被视图体语法拒绝）取列名 → data 连接（query_only）
  跑 `SELECT [c1],[c1] IS NULL,… FROM (<user sql>) LIMIT 1001`（>1000 行→truncated=true）→
  引擎错误原样呈现（AC-02「显示引擎错误」）。
- **切换/关闭**：前端 store 持当前路径并显式清空；后端无状态，切换=下一请求按新路径打开；
  无隐式连接残留。
- **资源预算**：浏览页 10/25/50；控制台截断阈值 1000 行（显式 truncated 标注）；单查询无
  超时承诺（本地文件、只读、引擎快速失败），取消=前端停止等待（不中断已提交语句）。

## 5. 实现后实测补充（2026-10-29，T-02..T-05）

- API 电池 37/37（`python tests/basic/verify_basic.py --api-only`，独立 sqlite3 oracle 比对：
  表/列/NULL/中文/CTE/聚合/搜索/排序逐值一致；V-02 失败路径无副作用；V-03 全部写拒绝+
  sha256 不变；V-04 分页/截断/切库/句柄释放）。
- Vue 端 Playwright 21/21（`--profile vue`，真实浏览器全用户链路，零页面错误）。
- VM 端：MCP 事件注入在本机高负载下不可靠，改用 Init 钩子确定性执行
  （`tests/basic/tools/vm_e2e_hook.py`），实测链路
  `open:basic_a.db/4 q:success/3 rows rej:error b:basic_b.db/3 back:basic_a.db` 全通过，
  状态经 autoui_state 读取（vmE2E 字段，常规运行恒空不影响 UI）。
  注入式完整 UI 电池（vm_drive.py 21 项）保留为环境安静时的复验入口。

—— 本文件为执行合同证据，随实现提交（*.md 证据摘要允许入库）。
