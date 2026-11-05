---
plan_id: PLAN-003
status: executing
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
- [ ] T-02（work，依赖T-01，AC-02）：配合OS054桌面任务核对树操作与只读oracle，提交execution_done。
- [ ] T-03（review/merge，依赖T-02，AC-03/04）：冻结同clone顺序复审、push、组合pin更新与归档；不提前勾选。

## 9. 复审记录

- drafting：确认独立clone main、源码漏导入、反例真实；next=work/T-01。所有验收尚未执行。
- work/T-01：e02551c只有store导入依赖的实现差异。固定SDK auto-ui644d8366/auto-lang23f3a031a；同一OS054 scratch项目原TS2304/exit1→修复后正式auto build -r vue exit0，vue-tsc与Vite均通过。日志D:/autostack/plan-artifacts/plan-003/auto-database/vue-build-fix.log SHA256 cd73cc4c201b80d3c91cb36e4e8fe0599d114cc0414b5c4d96816ededc786d50。T-02桌面树/只读oracle待验；未push、未改OS gitlink、未签最终review。保留原untracked .auto/。

## 10. 待澄清事项

无新增产品决策。最终复审与OS054桌面证据未完成，不提前宣称交付。
