---
plan_id: PLAN-003
status: reviewed
feature_name: Vue 对象树展开辅助函数导入修复
author: [Codex]
created_at: 2026-11-06
updated_at: 2026-11-06
plan_revision: 1
current_step: 2
total_steps: 3
supersedes_spec_components: []
new_spec_components: []
touched_goals: []
---

# PLAN-003：Vue 对象树展开辅助函数导入修复

## 0. 变更摘要

OS054候选正式Vue构建报TS2304：DbToggle调用toggle_id却没有在DbStore模块导入。补齐已有纯函数导入，恢复现有对象树能力。

## 1. 目标

DbStore独立Vue模块可解析toggle_id，树展开/收起继续调用已有实现。不改SQLite后端、数据格式、查询权限或界面功能。

## 2. 架构方案

单行修改src/front/db_store.at的components.tree_util导入列表。实施和顺序复审使用D:/autostack/auto-database独立clone main，服从AutoOS AGENTS §2.1（替代通用worktree规则）。OS组合树不编辑app源码。

## 3. 技术栈

AutoUI store、既有Vue生成与vue-tsc/Vite构建。

## 4. 需求分析与背景调查

授权来自用户本轮“解决这些问题，并最终完成计划054”；本修复是其中真实组合验收暴露的最小应用前置。主合同：[auto-os PLAN-054](D:/autostack/auto-os/docs/plans/054-basic-apps-unified-assembly.md)。无新预算或额外模型授权。

源码基线b3499d5，src与OS054锁定280ddac一致。主检出main无tracked WIP；既有untracked .auto/保留不纳入交付。docs/specs/database/basic-capabilities.md §1 T2已要求对象树，§3要求只读；本补丁不改变这些契约。观察：db_store.at:16只导入filter_tree/collect_ids，:214调用toggle_id；root app.at和filetree.at已各自正确导入该函数。

## 5. 详细设计

给DbStore自身补toggle_id导入，避免依赖另一组件模块的词法作用域。不新增辅助函数副本。

### 规范增量

| delta_id | add/modify/retire | target | before/after rule | rationale | acceptance IDs |
|---|---|---|---|---|---|
| SD-01 | none | docs/specs/database/basic-capabilities.md | 既有只读对象树合同不变 | 修复已有能力的模块依赖遗漏，无新规则 | AC-01/02 |

## 6. 测试设计

V-01：保留OS054 scratch原始构建日志vue-build-auto-database-r131.log（TS2304，exit1）；把新源码复制到隔离scratch后用同一候选SDK正式auto build -r vue，要求exit0且vue-tsc不再报toggle_id。该真实编译检查直接区分漏导入，不新增镜像实现单测。
V-02：OS054桌面真实数据库浏览验收包含树展开/收起、文件SHA/哨兵值不变；在054 T-04绑定交付版本，未跑不得签通过。实现/内部检查由当前执行上下文负责；最终复审按auto-plan-review顺序冻结同一独立clone，不自动创建新会话。

## 7. 验收标准

- AC-01（work）：新DbStore独立Vue生成/类型检查/构建通过；原漏导入反例保持可追溯。
- AC-02（work）：源码只补现有依赖，后端与Spec树不变；OS054真实树任务通过且SQLite文件不变。
- AC-03（review）：冻结提交复审AC-01/02及SD-01无影响说明，不以内部自检代替最终复审。
- AC-04（merge）：源码/文档推送main，OS054只在干净对应子模块fetch/detach新提交并更新gitlink；归档回执真实，保留其他WIP。

## 8. 执行步骤

- [x] T-01（work，AC-01）：补单行导入，复制源码到OS054 scratch并正式Vue构建，记录前红后绿。e02551c；正式auto build -r vue exit0，Vite2.46s，原TS2304消失；clone与scratch db_store.at字节SHA一致。
- [x] T-02（work，依赖T-01，AC-02）：OS054完整八app Vue桌面3410中真实输入打开中文SQLite，树箭头收起/展开后选订单，查询客户姓名/余额，CREATE TABLE具名not_readonly拒绝；切库显示54/U054-switch-only，关闭文件和窗口后重开原库筛选张三成功。两库SHA不变、试写表不存在，请求间隙均可重命名。实现冻结e02551c，进入execution_done，T-03未执行。
- [ ] T-03（review/merge，依赖T-02，AC-03/04）：冻结同clone顺序复审、push、组合pin更新与归档；不提前勾选。

## 9. 复审记录

- drafting：确认独立clone main、源码漏导入、反例真实；next=work/T-01。所有验收尚未执行。
- work/T-01：e02551c只有store导入依赖的实现差异。固定SDK auto-ui644d8366/auto-lang23f3a031a；同一OS054 scratch项目原TS2304/exit1→修复后正式auto build -r vue exit0，vue-tsc与Vite均通过。日志D:/autostack/plan-artifacts/plan-003/auto-database/vue-build-fix.log SHA256 cd73cc4c201b80d3c91cb36e4e8fe0599d114cc0414b5c4d96816ededc786d50。T-02桌面树/只读oracle待验；未push、未改OS gitlink、未签最终review。保留原untracked .auto/。

- stage: review | review_scope: final | reviewer_identity/limitations: Codex，同一实现上下文重建结论；无独立agent/context，不声称独立性（review技能允许该限制） | plan_id: PLAN-003 | plan_revision: 1 | outcome: pass | worktree_path: D:/autostack/auto-database（用户app clone策略） | branch: main | reviewed_commit: 4abf9b15bea0bbd0fb04b3d79ace84612ba0fbd7 | base_commit: b3499d5 | dependency_revisions: UI644d83666f6a178a57445e4a0d982714088296d5 / Lang23f3a031a / Man03bb65e | next: merge
  AC-01 pass：实际diff唯一实现行为是DbStore导入现有toggle_id；检查tree_util函数声明/DbToggle调用及生成useDbStore，不添函数副本。原同scratch TS2304失败与修复正式Vue构建成功日志覆盖该遗漏，源码与消费副本逐字节一致，code/dependency/config未漂移，复用已执行编译而不重跑无关套件。
  AC-02 pass：复核真实DOM/截图中的树收起/展开/选订单99.9、SQL返回张三100.5/李四250.75、CREATE TABLE被not_readonly拒绝、切库54/U054-switch-only、文件关闭、关窗重开后的张三过滤。独立oracle的两库SHA与原始输入相同，should_never_exist不存在且可重命名；后端/Spec git diff为空。保留已有untracked .auto/ui-cache.json（2202 bytes，非交付源），未清他人缓存。
  AC-03/SD-01 pass：当前docs/specs/database/basic-capabilities.md SHA9efac155edb2d220a28f947e2090e939a678e5882f0b8864966eeeceecb473bc，既有T2对象树与只读规则未变；SD-01=none，补模块依赖不增加能力/规则，supersedes/new均为空。git diff --check通过，HEAD与审前相同、无dirty tracked实现。
  pending_closeout_gates：AC-04/T-03的push、OS组合pin升级和归档尚未执行；app独立clone按用户规则保留，不删除。054整体最终独立上下文复审不由本条替代。findings：无需修复的实现发现。接入与数据证据来自明确标记的development overlay，正式OS pin仍待交付。
## 10. 待澄清事项

无新增产品决策。最终复审与OS054桌面证据未完成，不提前宣称交付。

- work handoff / 2026-11-06：AC-01/02 complete，r1 / implementation e02551c，SDK644d8366+23f3a031a。消费源为OS054 scratch的明确development overlay，不冒称OS gitlink已升级；后端Rust真实17839，运行PID49104，宿主session13890仍活。V-02独立oracle t04/db-independent-oracle-r134.json SHA02ceea520eb7847275fce6846de843bdf2b6dd4266852dbaf97c8af0f4e34e7a；两fixture SHA分别1a5c61b60353b21511b7638fd60c56da8530195bae1109884aa63f8f229dfe65、91cc71c91d7ba24b55f8f6d72bd882749c8eff55cd59c8d0c1d3e663bcfc675d，前后相等。重开后真实筛选截图t04/screenshots/vue-db-reopened-r134.jpg SHA9cd697c543d8c9d2787e954b3a779d61c34062cdcfa1bfbd80f3df909af35bf3；DOM记录db-reopened-dom-r134.txt和拒写DOM/截图在054 t04。next=review final，同一独立clone main；实现写入暂停。未push/未改组合pin/未归档。
