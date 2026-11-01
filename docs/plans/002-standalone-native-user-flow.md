---
plan_id: DATABASE-002
status: drafting
feature_name: "原生真实操作与独立运行验收"
author: [Codex]
created_at: 2026-11-01
updated_at: 2026-11-01
plan_revision: 1
current_step: 1
total_steps: 8
base_branch: main
base_commit: 42be41d3827c021b4d72a7b894f3ac3aa8074cbd
depends_on: ["DATABASE-001"]
supersedes_spec_components: ["docs/specs/database/basic-capabilities.md"]
new_spec_components: ["docs/specs/database/standalone-native-acceptance.md"]
touched_goals: []
---

# DATABASE-002：原生真实操作与独立运行验收

## 0. 变更摘要

接续001真实只读SQLite，补未修改Init的原生用户操作链及独立启动门；复用现有vm_drive，不拿注入自驱结果冒充实际输入/点击已验。只读边界保持，不新增SQL写入或数据库管理功能。

## 1. 目标

独立Vue＋Rust/原生VM＋Rust，从真实界面输入SQLite路径、打开、树选择、分页/搜索、结构、SQL成功/拒绝、切库/关闭并再次操作；原数据库全程不被改写，失败不建假空库，原生门可重复。

非目标：行编辑/DDL写入、远程/加密数据库、ER图、多库运维、OS集成/Linux。

## 2. 架构方案

本仓为主导仓，开发/检查/最终复审顺序使用 `D:/autostack/auto-database` 独立clone的 `main`，一app一写入者，复审时暂停实现写入；不在AutoOS子模块开发，不建junction/symlink。框架若确有缺项，先核实现有公共能力和当前实际owner，再在owner仓另立最小前置并遵守其worktree规约，本计划不授权越仓改实现。

应用业务保持纯.at；复用既有仓储、UI、测试，不手写业务Rust、不改生成Rust/Vue来交付。源知识为docs/specs；本轮只列Spec提案，不写canonical、旧specs.json或手工索引。未知技术方案由T-00有界调查，不能靠占位/必需skip关闭验收。

独立运行门使用新建且本次拥有的临时数据/端口/构建输出；不删除既有app/框架target、不停止他人实例。CLI和真实编译/渲染tool都记版本/hash及发现路径；进程清理按本次spawn归属，不凭端口或命令行相似就杀进程。冷准备允许耗时，但须有阶段、就绪判定、有界超时和非零失败；预算及资源边界在T-00先冻结。

复用db.at的守卫＋query_only和每请求连接、现有db_store/树组件和两端驱动；UI操作必须来自当前可见元素的输入/按钮/选择，不临时改Init、不直接派store消息代替UI、不通过API预开库。只读API/独立sqlite3用于结果oracle，不用于代做用户操作。

## 3. 技术栈

现有.at、生成Rust、SQLite、Vue Playwright、AutoUI MCP；复用verify_basic.py、ui_drive.mjs、vm_drive.py、make_fixtures.py。vm_e2e_hook.py保留为历史诊断，不能作为本计划必需UI门的成功路径。

## 4. 需求分析与背景调查

用户2026-11-01要求接续其余原B类应用的下一步计划，沿上一轮“计划/README/roadmap、提交push，不开始实现、不更新OS子模块”的范围执行。Reader已转另一个会话按Readest新目标跟踪；Blog现有上游阻塞由原计划继续，Chat/Charts不在本轮改面。应用单独运行不等OS装配或其他app；Linux仍WAIT_DISTRO_M1（Nix＋COSMIC基础）。

001归档有API37/37、Vue21项和独立复审记录；Spec§4如实声明VM以临时Init注入、自驱并经MCP读态证明链路。现有vm_drive.py虽描述真实UI，仍需在当前版本原样运行/核验输入和树绑定，不能把文件存在当验收通过。

db_store.Init当前为空，实际操作链为PathInput/OpenDb、DbSelect/OpenTable、RunSql等；旧hook会重写Init并直接调用链路。本计划保持原应用源码形态运行。NULL文本与字面NULL显示仍沿001边界，oracle用独立null标志，不顺便改数据类型/写控件。

| 来源文件 | SHA256 |
|---|---|
| `docs/specs/database/basic-capabilities.md` | `510ddab502f80869fac10db1a363a77f14bde3efb2c98858927a2e2e483c88e1` |
| `src/back/db.at` | `e2eabac19e5c876488bbee1a7d07c8845cc08dd96b45e89e4cdb3445a80bced0` |
| `src/front/db_store.at` | `a1fcad3a4575b2d9899892f1da67ad5714e488bacf45c5f15aa45e29fb01709b` |
| `tests/basic/verify_basic.py` | `ed0559b06fb877a7f8af899ea5653eebc95d596c71a6b66bcdf9d03bdc1e55d1` |
| `tests/basic/vm_drive.py` | `2f017ac9d6948ebfa13bacdbf20b79013471b6df8641d1c5176b2736f97032d1` |
| `tests/basic/tools/vm_e2e_hook.py` | `d4a14975f8ebb66c2d34142de5ff7a4fb2ccfbcf5571c74befcdbd344483a72a` |

## 5. 详细设计

T-00新增 `docs/plans/evidence/002/native-ui-decision.md`：固定源码/CLI/tool/驱动，先确认Init无hook；用最小真实路径输入/打开/树选择确定MCP活视图和事件绑定。区分driver失配、陈旧tool和app/框架缺陷，先复用已交付能力，必要时向实际owner提最小前置。

继续用 `python tests/basic/verify_basic.py --profile vue|vm` / `--api-only`。T-01/T-02补正式独立准备、随机端口、隔离夹具和自有进程；T-03升级vm_drive真实用户链，若现代码已正确则不为本计划重写查询引擎。只读原则沿现有单条SELECT/CTE、拒绝写与引擎错误；中文标识符/路径按当前支持范围作真实操作样本。

测试夹具是关闭状态的本次SQLite文件（避免外部写者使hash oracle误判）；查询/错误/切库前后核对main文件hash与哨兵行，检查请求间隙可重命名/替换而无泄漏锁。无效路径不出现新文件；库A/B具不同标识和记录，切回A必须是真A，不能看相同默认表名假绿。

失败的UI动作要有可见错误/原输入保留；服务/窗口重开后重新输入路径能再次查询，不额外承诺自动记住上次库。探针不能破坏本机用户数据库，测试模式缺省关闭/隔离证明不足即失败。

### 规范增量

| delta_id | add/modify/retire | docs/specs/... target | before/after rule | rationale | acceptance IDs |
|---|---|---|---|---|---|
| SD-01 | modify | docs/specs/database/basic-capabilities.md | VM注入自驱边界→未改Init的真实输入/树/SQL证据；只读不变 | 补真实用户操作验收 | AC-02/03/04 |
| SD-02 | add | docs/specs/database/standalone-native-acceptance.md | 独立准备/工具身份/可见操作和永久门 | 原生可重复运行 | AC-01/04 |

## 6. 测试设计

D用例均owner_stage=work，由T-03/T-04使既有入口真正覆盖；原API/只读oracle保留。

| Case ID | AC | 输入/真实入口 | oracle/预期 | 边界 |
|---|---|---|---|---|
| D-01 | AC-01 | 文档准备、Vue/原生分别独立启动，错tool/占用端口 | 可操作的真实窗口/页和自有Rust后端；错误非零，旁观实例不受影响 | 不依赖OS |
| D-02 | AC-02 | 未改Init，UI输入中文路径打开A→树/分页/搜索/结构→SQL | 当前元素真实事件生效；所见列/值与独立sqlite3一致，不用API或消息预操作 | 同时保留Vue控制 |
| D-03 | AC-03 | UI写语句/多语句/坏SQL/不存在路径/坏文件 | 拒绝/引擎错误明确；main hash/哨兵行不变、缺失路径不新建，不回落demo | 沿001只读子集 |
| D-04 | AC-02/03 | A→B→A→关闭；异常后请求间隙重命名，重开app再查询 | 内容身份随库变化、关闭无旧结果/锁泄漏；恢复后下一次合法查询成功 | 闭合夹具、无外部写者 |
| D-05 | AC-04 | 拦截真实UI输入/错库断言等受控反例 | 驱动不能靠Init/state直写绿；受影响断言与总门非零，正常控制通过 | 前后源码hash证明未注入 |

最终review独立上下文实际复跑原生必需链并检查源码前后hash、UI动作/独立库证据；环境缺失不能复用旧Init结果充当新门。必要外部缺口保留在work，不免验。

## 7. 验收标准

- AC-01（owner_stage=work）：正式独立准备/启动与失败/自有资源清理可重复，D-01通过。
- AC-02（owner_stage=work）：未改Init的真实原生输入/树/SQL/切库与重开下一次操作，D-02/D-04通过。
- AC-03（owner_stage=work）：只读/错误/路径与句柄保全成立，D-03/D-04通过。
- AC-04（owner_stage=work）：永久门真实覆盖、D-05敏感性和旧API/Vue回归成立，无必需skip/零场景；SD/README符合实际。
- AC-05（owner_stage=review）：冻结源码/工具，独立上下文复审AC-01..04、SD-01/02并实际跑原生门。
- AC-06（owner_stage=merge）：仅app规范/新计划归档计数/提交push收尾，不更新OSpin或重开001。

## 8. 执行步骤

- [x] T-00（owner_stage=work；依赖001；AC-01/02）：确认无hook的真实输入/树链及工具身份，输出责任/支持/预算决策稿。〔✅ 已完成 2026-11-02：docs/plans/evidence/002/native-ui-decision.md；§4 六hash相符；Init无hook（源码+运行态）；真实 type→WPathInput / find(button)→press→WOpenDb 全通（handler回执）；garbage错误分支渲染正常；发现 auto-ui-runtime iced投影 container.rs:291 结构翻转竞态（压测7/7 launch崩，open或close翻转），原生成功分支阻塞→owner前置；vm_drive click_by_text 误按Text节点实证→T-02修正；进程归属清理/冷106s暖4-40s/预算冻结；原始证据 plan-artifacts/plan-002/t00/〕
- [ ] T-01（owner_stage=work；依赖T-00；AC-01）：收口独立准备/启动、隔离夹具/端口/进程身份和错误判定。
- [ ] T-02（owner_stage=work；依赖T-00及确需实际前置；AC-02）：修driver/应用实证接缝；不改Init或走API预操作，只用真实可见UI事件。
- [ ] T-03（owner_stage=work；依赖T-01/02；AC-02/03）：扩展既有vm_drive/调度器，跑D-02..04和Vue对应控制、独立只读/句柄oracle。
- [ ] T-04（owner_stage=work；依赖T-03；AC-04）：跑D-01..05与原API/拒写门、真实故意失败控制，输出SD候选和无源码注入证据。
- [ ] T-05（owner_stage=work；依赖T-04；AC-01..04）：核对漂移/覆盖、README/roadmap，提交execution_done。
- [ ] T-06（owner_stage=review；依赖T-05；AC-05）：同clone独立上下文最终复审并实际执行原生门。
- [ ] T-07（owner_stage=merge；依赖T-06 pass；AC-06）：仅本app规范/归档/提交push收尾。

## 9. 复审记录

- stage: new | plan_id: DATABASE-002 | plan_revision: 1 | outcome: pass（有界T-00准备就绪；本轮没有实现或产品验收） | next: work/T-00（等待后续实施指令）。
- 已归档001、现实现Spec和产品源码保持不变；规划结构/链接通过不等于功能通过。review以同一clone的独立上下文核验，不自动创建agent/chat或指定模型。
- stage: goal | plan_id: DATABASE-002 | plan_revision: r1 | round: 1 | from: drafting | to: work | status: drafting | outcome: pass | worktree: D:/autostack/auto-database（计划§2用户既定：独立clone即main，一app一写入者） | commit: 74b6d03 | next: work（授权链：/goal 完成计划002 → work/review/有界修复/merge 全程继承）。
- stage: work | plan_id: DATABASE-002 | plan_revision: r1 | outcome: needs_fix（T-00完成；原生成功分支被框架竞态阻塞，受影响任务挂起owner前置） | worktree_path: D:/autostack/auto-database | branch: main | base_commit: 42be41d | code_commit: 74b6d03（本轮未改产品源码） | dependency_revisions: auto CLI 0.1.0+plan-890-verified-r7-t19-5-g55c98c7（sha256 390e664e…）、auto-ui-tool 2026-11-01构建（auto-ui main 30c9027）、auto-lang 工作区源 | task_ids: T-00 | evidence: docs/plans/evidence/002/native-ui-decision.md（§4六hash相符；Init无hook；真实type/press handler回执全通；garbage错误分支正常；iced container.rs:291翻转竞态压测7/7崩→AC-02/03/04原生门挂auto-ui前置；driver Text误按实证） | blockers: 原生打开/关闭成功分支=auto-ui-runtime框架缺陷（计划§10：受影响任务保持未完成，T-05 handoff提出用户决策 a等修复/b缩减验收/c授权跨仓修复） | next_responsible_role: work（T-01/T-02不受影响部分继续）

## 10. 待澄清事项

当前没有需要用户重复确认的产品方向。技术不确定性由T-00记录真实证据、owner与依赖任务；若需要改变目标、削减必需验收或扩大跨仓写入范围，先明确报告，受影响任务保持未完成。归档/merge只完成本app的Spec/计划/提交push与自有临时产物收尾，不更新AutoOS gitlink、manifest或.gitmodules；后续OS统一计划接收已单独验证的固定SHA。
