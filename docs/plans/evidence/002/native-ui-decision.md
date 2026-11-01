# 002 原生真实操作链决策稿（T-00）

plan: DATABASE-002 r1 · 日期: 2026-11-02 · 状态: T-00 交付
原始证据: D:/autostack/plan-artifacts/plan-002/t00/（probe*.log、run*.log、stress 输出、snap-*.txt）

## 1. 冻结身份（本轮实测）

| 项 | 值 |
|---|---|
| 本仓 HEAD / base | 74b6d03（计划 base_commit 42be41d 之后仅文档提交） |
| 计划 §4 六文件 SHA256 | 与 §4 逐字一致（实施前核验，源码未被改动） |
| auto CLI | `D:/autostack/auto-man/target/debug/auto.exe` · `0.1.0+plan-890-verified-r7-t19-5-g55c98c7` · sha256 390e664ead5fc755… |
| tool host | `D:/autostack/auto-ui/target/debug/auto-ui-tool.exe`（构建 2026-11-01 09:16；auto-ui main HEAD 30c9027 2026-11-02，owner plan-026 进行中） |
| MCP 工具面 | autoui_snapshot/state/type/action/find/keyboard/wait/screenshot 等 20 项（较 001 时代增强） |
| 驱动 | tests/basic/vm_drive.py、ui_drive.mjs、verify_basic.py、make_fixtures.py（本轮未改；§4 hash 相符） |
| 环境 | python 3.14.2 + requests 2.34.2 · node v25.2.1 · sqlite3 3.50.4 |
| 夹具 | make_fixtures.py 产物：basic_a=7cad5cdd…、basic_b=05b4d0dd…（scratch 隔离目录） |

## 2. Init 无 hook 确认

- 源码：`src/front/db_store.at` `.Init -> { }` 空体；无 vmE2E 字段（§4 hash 相符）。
- 运行态：autoui_snapshot / autoui_state 全量 dump 均无 vmE2E（t00/probe.log）。
- 结论：当前检出即未改 Init 形态；本轮全部证据在其上采集。

## 3. 实证：真实输入链（无 Init hook、无 API 代做、无 store 消息直派）

**已打通（真实用户事件，含 handler 回执）**：
1. `autoui_type` 路径输入 → `handler: .App.WPathInput`，store `path_input` 收到全文（t00/probe2.log）。
2. `autoui_find(kind=button, label=打开)` 定位 Button vnode → `autoui_action press` → `handler: .App.WOpenDb`（t00/probe3.log）。
3. 后端打开链 120ms 完成（db_open+objects+首表加载，run3.log VM-PARKED）；独立 API open 200/tables=4 对照一致。
4. 失败分支渲染正常：garbage.db → 横幅 `打开失败（not_a_database）file is not a database`，会话存活（t00/probe4.log）。
5. **driver 接缝（T-02 依据）**：vm_drive.py 的 click_by_text 按快照文本就近取 id 会命中按钮内部 **Text** 节点 → `Action 'press' not valid for component type 'Text'`（t00/probe2.log）；正确姿势为 `autoui_find(kind=button)` 取 Button vnode。旧 vm_drive 全线有此缺陷；新版 CLI 上未见"注入偶发丢失"（type/press 均有回执）。

**阻塞缺陷（核心发现）——VM iced 投影结构翻转竞态**：
- 现象：connected 翻转（打开成功或关闭）触发的重渲染使 VM 会话崩溃：
  `panicked at iced_widget-0.14.2/src/container.rs:291:42 — called Option::unwrap() on a None value`（exit 101），MCP 随之失联；后端不受影响。
- 压测（真实 UI 打开→关闭循环，每变体 2 launch × 8 cycle，t00/run-stress.log）：
  - 原版：0/8、0/8（打开成功后**关闭**翻转崩）；
  - `bg-card/30→bg-card` 变体：0/8、0/8（**打开**翻转崩）；
  - `AUTOUI_MSG_BACKFILL_DIRTY=1` 逃生门：0/8、0/8。
  - **7/7 launch 崩溃**；早期单次探针"通过"为时序侥幸。
- 复现率随时序浮动（崩溃点在 open/close 翻转间移动），属竞态而非确定性逻辑错误。
- 已排除：窗口最小化（VM host **无 OS 窗口**，离屏渲染正常，screenshot 成功）；MCP 注入失灵（type/press 有 handler 回执）；app 业务源码缺陷（store/handler/错误横幅行为全部正确）；Init hook（无）；alpha 色样式（F7 变体同崩）；框架置脏逃生门（escape 压测同崩）。
- 机制定位：auto-ui-runtime VM/iced 投影层在条件子树翻转 + 动态子节点更新时的 diff/operate 竞态（Container::operate 取不到 layout 子节点）。
- 对照 001：同一 app 源码在旧 CLI（v0.0.20-118，Init 注入链）全链路通过 → 疑似 plan-890 代投影回归（推断；旧二进制已不可复测）。
- 次生现象（T-01 收口项）：间歇性 `run_ui failed: tool host closed the control stream before answering id=1`，多见于源码变更后首次启动/再生期，重试可通过。

## 4. 责任判定

| 层 | 判定 | 依据 |
|---|---|---|
| 驱动（vm_drive 定位层） | 本计划修复（T-02/T-03） | Text 误按实证；find(kind) 修正后 type/press 全通 |
| app 业务源码（VM 轨） | 无缺陷，不改 | §4 hash 未变；store/handler 行为全部正确 |
| auto-ui-runtime（VM iced 投影） | **框架缺陷 → owner 前置** | container.rs:291 竞态；7/7 压测崩溃；001 同源码旧 CLI 通过 |
| Vue 生成器（R001 新规则） | 新 CLI 拒绝未改源码 → app 侧一行适配（本计划内） | `for qi, row in .store.qVals` 控制台表键名去重后 Vue 电池 21/21（t00/vue-diag-run.log）；R001=同组件两TableRow实例共键即错，Vue 兄弟域本可合法 |

## 4b. Vue 轨实测（2026-11-02 补）

- 现象：--profile vue 电池 open-a 失败；vue_diag 捕获生成期 `[R001 ERROR] App: Duplicate :key="ri" on <TableRow> (2 instances share this key)`——数据浏览表与 SQL 控制台表同用循环变量 ri，新生成器判 ERROR 拒绝编译（001 时代生成器接受）。
- 修复：控制台表循环变量 ri→qi（app.at 一行；浏览表不变）。语义不变（key 仅行标识）。
- 结果：ui_drive.mjs 全链 21/21 PASS、零 page error（打开/计数/中文树/NULL/分页/页大小/Schema/SQL 成功/拒绝/引擎错/切库B/切回A/无页面错误）。
- 附注：vite 对 urllib 直连 / 的探测拒绝（10061）但 Playwright 正常——以浏览器实际可达为准。

## 5. 支持与预算（实测边界，T-01 采纳）

- 冷准备 106s（首次生成+编译）；暖启动 4-40s。VM 前端解释执行无编译。
- 端口/数据/进程隔离已验证：-B/-F 随机端口、scratch 夹具、spawn 树记录（auto/cargo/auto-ui-tool/back 6-7 pid）→ 按记录 pid taskkill /T；不凭端口/命令行相似杀进程（实测机器上有非本会话 `auto.exe service --server vm` 等，保持不动）。
- 预算冻结：ui 就绪 ≤1500s 冷 / 600s 暖（沿 verify_basic 现值）+ 失败非零；单 UI 电池 ≤600s；全套 D-01..05+API ≤40min；tool-host 启动瞬断按现有重试模式收口。

## 6. 决策与影响

1. T-02/T-03 按 §3.5 修正升级 vm_drive（find(kind) 定位 + handler 回执校验 + 翻转后重试），驱动层无未知接缝。
2. **原生打开/关闭成功分支被框架竞态阻塞**：AC-02/03/04 的原生门无法在本工具链稳定通过。按计划 §2（不越仓改实现）与 §10（受影响任务保持未完成、明确报告）：原生必需链挂起，挂 **auto-ui owner 前置**——最小复现：`auto run -r vm` + MCP type 路径 + press 打开/关闭（证据 t00/*）。
3. 不受影响工作继续：T-01 独立准备/进程身份/错误判定（失败分支与 API 轨全可用）、Vue 轨对照、API/拒写门、D-05 敏感性控制、hash/哨兵/句柄 oracle。
4. 待用户决策（T-05 handoff 提出）：(a) 等 auto-ui 修复后回归原生门（计划保持 executing）；(b) 明示缩减 AC-02 原生验收；(c) 授权跨仓最小修复。默认按 (a) 挂起。
