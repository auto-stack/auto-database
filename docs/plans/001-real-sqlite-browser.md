---
plan_id: DATABASE-001
status: drafting
feature_name: real-sqlite-browser
author: [Codex]
created_at: 2026-10-29
updated_at: 2026-10-29
plan_revision: 1
current_step: 0
total_steps: 7
supersedes_spec_components: []
new_spec_components: [docs/specs/database/basic-capabilities.md]
touched_goals: []
---

# DATABASE-001：真实只读 SQLite 浏览与查询

## 0. 变更摘要

把预置表和字符串模拟 SQL 替换为真实 SQLite 文件的只读浏览器。

本轮只起草执行合同：没有实施功能、运行功能验收或将本app升为A类。auto-database 的基本能力补齐不依赖 auto-os-distro；Linux 支持另等 Nix＋COSMIC 基础完成，增强设计另会话。

## 1. 目标

用户选择一个已有 SQLite 文件，看到真实表/结构和数据，执行一条只读查询，得到真实列/行/NULL或明确错误。

非目标：行编辑、事务写入、数据迁移、远程数据库、账号/凭据管理、可视化建模、Linux 适配。本次定义为只读基本版本，现有模拟 Commit/Rollback/Edit 不可继续装作可用。

## 2. 架构方案

应用逻辑继续纯 `.at`，前端/后端沿 AutoUI 现有结构；本仓为主导仓。应用工作检出固定 `D:/autostack/auto-os/apps/auto-database`，工作分支 `main`；执行/复审共用此检出，一个写入者。**不新建app外部worktree或clone，不建任何junction/symlink**。框架缺口在实际owner仓另立前置并按其worktree纪律执行，不在app手写Rust、修改生成Rust或绕过公开SDK。

连接到明确存在的用户文件并以引擎只读能力限制；不存在/损坏/不可读必须报错，不能创建空库或回退内存后成功。表和列从真实 schema 获取，动态列/NULL 不套预设 customers 模型。只允许经引擎验证的单条只读查询，禁止 ATTACH/写PRAGMA/扩展加载/多语句等绕过；不以 starts_with(SELECT) 充当只读保证。

跨仓总表：[B类基本能力总跟踪表](../../../../docs/plans/b-apps-basic-capabilities.md)。源Spec以所属仓 `docs/specs/` 为准；当前没有该app的canonical模块规范，旧根 `SPEC.md`（如有）只是历史Demo观察/再生描述，不能据此宣布真实功能已完成。新规范路径将在实际复审/merge后落地，本轮不写入已实现Spec。

## 3. 技术栈

Auto / AutoUI、当前匹配的AutoLang/AutoUI/AutoMan工具组合、各app已有widget/store/API；具体存储与平台接缝由T-01用实际源码和探针确认。Vue / VM 两端均需真实任务验收，不因某一后端不通就删掉原任务；如必须显式指定 server=vm 等启动profile，应先验证并记录到执行入口/README，不能静默换成mock。

## 4. 需求分析与背景调查

授权：用户于2026-10-29要求建立总跟踪表、复用Notes/Reader/Blog现有计划，并为其余B类应用准备基本能力补齐计划。此处授权的是**计划准备和必要的文档/组合版本登记**，不宣称已授权/完成本计划具体功能实现，不推定全量竞品复刻或Linux开发已启动。

冻结的观察基线：`85fb35dbe675e354614629a4cbb40d6560ce86c0`（在本app `main` fetch origin后ff核对）；执行前重新核对HEAD/pin/WIP并记录变化。主产品统计为27个去重产品，B类9个；AutoJade旧名Jade Garden不重复计数。

app.at RunSql 根据关键字在固定列表间切换，Commit/Rollback 只改计数和文案。语言仓已有 a2r-std/src/sqlite.rs 与 VM FFI；读到 a2r sqlite.open 失败会落内存库，且当前观察未证明提供只读连接，因此不是可直接承诺的产品 API。

已读来源（源码/文档观察，不是本轮实测）：

- `src/front/app.at`：SHA256 `b08c79c9f6ed794a19b51303435518d20cc84c1e4cf8c3266e0bbc29d113e365`。
- `SPEC.md`：SHA256 `c1fd450e9f7611e2f1d6941b121e69608b142885bbaf1f5b7c13371539e95992`。
- `pac.at`：SHA256 `af9d025a3a1d2f28cd8f010417d412ccb4e5b12fa7314044bc45e57eaa44620b`。
- `tests/desktop_mcp.py`：SHA256 `eff2406648ec7a7344f20b020ad032aa1c2dc0cf1b6567811318c674a06e0ff6`。

源码探针入口：[a2r SQLite](../../../../../auto-lang/crates/a2r-std/src/sqlite.rs)、[VM FFI SQLite](../../../../../auto-lang/crates/auto-lang-core/src/vm/ffi/stdlib/sqlite.rs)。它们提供调查事实，不表示只读/错误合同已满足。

## 5. 详细设计

### 执行入口和依赖

首个就绪任务仅T-01：在上述应用检出核对版本、清单、当前工具链、真实API与测试入口，用隔离数据跑能力探针。输出允许后续实现依赖的接口与不支持项；缺口需具名指向owner/前置计划及关闭条件。不得假造未存在API、跳过基础正确性，或以“将来Linux会解决”替代当前端的基本能力。

T-02..04按下列任务依赖顺序推进；T-05将本节拟议测试做成真实可复现入口，T-06/07保持未来阶段未勾选。合并后只有基础合同的全部必需工作/复审通过且父仓pin指向交付版本，才更新总表分类。发布包/所有Linux发行版不在本计划的成功声明里。

### 规范增量

| delta_id | action | docs/specs target | before/after rule | rationale | AC |
|---|---|---|---|---|---|
| SD-01 | add | `docs/specs/database/basic-capabilities.md`（新） | Demo/未定义 → 本计划首版用户任务、数据模型和准确支持范围 | 以真实基本能力作为产品准入 | AC-01/02 |
| SD-02 | add | 同上，失败/恢复及交互节 | 未定义 → 保存/输出/失败、重启和两端行为的可验合同 | 防止假成功、旧数据丢失和单端冒充 | AC-03/04 |

根README/历史SPEC在实现落地时反链canonical目标，保留历史来源、不覆盖未经审查的旧约定；本计划不在draft阶段修改canonical知识或ledger。

## 6. 测试设计

本轮没有执行下列功能测试。先以真实应用入口和真实文件/服务为准，既有脚本若只验证演示数据，需要补有辨别力的真实数据正反例；禁止仅把UI文案变绿或用相同生产函数生成期望值。

| case_id | AC/task与责任 | 输入/设置 | 实际入口 | 必须观察的结果 |
|---|---|---|---|---|
| V-01 | T-01..05 / AC-01..04；由T-05制作永久回放 | 两份含不同表和中文/NULL的真实SQLite | 打开文件→schema→SELECT | 独立Python sqlite3只读连接核对列和值；不存在路径不得生成文件。 |
| V-02 | T-01..05 / AC-01..04；由T-05制作永久回放 | 无效路径/坏SQLite | 实际连接入口 | 明确失败，无隐式空内存库成功；原文件保持。 |
| V-03 | T-01..05 / AC-01..04；由T-05制作永久回放 | UPDATE/DELETE/ATTACH/多语句、只读CTE正控 | 公开查询入口 | 负例拒绝且主库及目标哨兵哈希不变，合法查询仍成功。 |
| V-04 | T-01..05 / AC-01..04；由T-05制作永久回放 | 1200行结果、切库与重复开关 | UI→provider→关闭 | 正确分页/显式截断而非假总数，句柄回收可观测；1200为样本非承诺上限。 |

测试隔离：所有文件/数据库/服务均使用临时用户数据目录及明确测试端口，不接触真实用户数据；占用端口/不可写/损坏时明确失败。多个实例/取消/退出与恢复按本计划声明范围验证。资源预算若需限制，T-01明确单位/语义/拒绝或截断结果并在dependent实现前冻结；没有提出上限不等于无限规模承诺，不以隐藏硬上限代替验收。

可复现入口（**均由T-05新增/接通**）：`python tests/basic/verify_basic.py --profile vue`、`python tests/basic/verify_basic.py --profile vm`。入口应实际调用应用后端与两端UI，记录源码/工具/依赖版本、fixture hash及运行结果；不得仅调内存helper替代。按可用工具复用现有Playwright或VM MCP/autoui-verifier驱动。T-01记录真实启动命令、数据env、端口与适用CLI参数；两端都要证实实际支持的用户任务。

角色：本轮仅起草，没有派执行/复审agent。实现与最终复审按四技能分阶段；无明确独立上下文时如实声明并从工件重建，不能自称独立或擅自创建新会话/agent。只改app不触auto-lang crates时禁止跑其cargo t/docs_gen；框架前置按owner自己的门档验证。

## 7. 验收标准

| ID | owner_stage | observable / verification |
|---|---|---|
| AC-01 | work | 真实连接：打开自建SQLite，表/列/记录与独立sqlite3 oracle一致；切换两个不同库后结果确实更换；不存在/坏库不成功且不新建文件。 |
| AC-02 | work | 真实SQL：单条 SELECT/合法只读 CTE/聚合/NULL/Unicode 返回真实结果；非法SQL/未知表显示引擎错误，不依关键字选择样例。 |
| AC-03 | work | 只读不变式：写语句、WITH写入、PRAGMA/ATTACH/多语句和扩展加载尝试不能改主库/关联库；数据库及相关内容哈希保持，不能只看UI只读标签。 |
| AC-04 | work | 生命周期与双端：大结果有明确分页/截断和可响应界面；关闭/切换/查询失败释放句柄。Vue/VM 完成打开→查询→错误→切库。 |
| AC-05 | review | 冻结已提交实现与依赖，逐个重验AC-01..04和独立反例；核对SD-01/02与范围、实际证据，输出明确review结论；未闭项不可忽略。 |
| AC-06 | merge | 通过对应最终门后交付main并推送，父仓gitlink和组合验证可追溯；canonical/ledger/归档收尾完成，app显式detached；总表有证据地标A，A类Linux仍等待发行版前置。 |

## 8. 执行步骤

- [ ] T-01（owner_stage=work；依赖 无；AC-01..04）：基线与全路径探针：有界核查现有 Auto SQLite 的打开失败、只读连接、单语句/只读判定、动态结果/NULL、资源关闭和取消/分页；固定版本和前置归属。已读源码 D:/autostack/auto-lang/crates/a2r-std/src/sqlite.rs、crates/auto-lang-core/src/vm/ffi/stdlib/sqlite.rs 只是调查入口，禁止 app 手写 Rust 或仅检查 open 句柄非空。若接口缺失，登记 SDK 前置并阻塞依赖任务。若需后端，17839 为候选。 输出新文件 `docs/plans/evidence/001/capability-decision.md`，记录可用API、版本/资源边界、缺项owner和最小闭环。
- [ ] T-02（owner_stage=work；依赖 T-01；AC-01..04）：真实数据接缝：新增 src/back/sqlite_service.at / api.at（拟议），接经 T-01 证实的只读 provider；连接关闭/切库释放资源，错误与内存 fixture 明确区分。
- [ ] T-03（owner_stage=work；依赖 T-02；AC-01..04）：Schema与真实查询：实现实际表/schema读取及查询结果模型，行数/列名/NULL来自引擎；确定分页或显式截断预算，超过预算有真实状态。
- [ ] T-04（owner_stage=work；依赖 T-03；AC-01..04）：界面去模拟化：现有对象树/结果表/SQL输入接真数据；去掉模拟事务和写入成功提示，不可用写控件隐藏或明确禁用；显示文件身份和只读状态。
- [ ] T-05（owner_stage=work；依赖 T-02..04；AC-01..04）：完成独立数据/失败回放和两端真实UI验收，新建 `tests/basic/verify_basic.py` 调度入口（可复用既有脚本），同时保存命令/输入hash/真实结果与原始失败；准备 canonical Spec 增量，提交实现，转 execution_done。
- [ ] T-06（owner_stage=review；依赖 T-05；AC-05）：在同一app检出暂停实现，按冻结提交、真实数据和独立反例最终复审；核对Spec增量与双端结果，说明上下文独立性限制；未满足返回修复，不将数据错误降为债务。
- [ ] T-07（owner_stage=merge；依赖 T-06；AC-06）：完成实际提交/推送/父仓gitlink验证，沉淀canonical Spec与derived ledger、归档；刷新总表A/B与证据，app显式detach。Linux仍等待发行版门，不因文档或脚本存在宣布已可用。

## 9. 复审记录

- stage: new | plan_id: DATABASE-001 | plan_revision: 1 | outcome: pass（计划草案就绪；能力探针/实现/验收未执行） | next: work/T-01（另行执行）。
- 本轮核对源码/Spec缺口、历史任务、路径、基线和计划唯一性；未执行实现/功能测试，所有7项任务保持未勾选；通过的是草案结构/相互引用检查，不是产品验收。

## 10. 待澄清事项

无必须先向用户确认的产品身份问题；技术可行性与资源边界由 T-01 冻结，缺口保持具名阻塞。
