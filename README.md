# auto-database

数据库管理工具，使用 AutoLang / AutoUI 开发的独立应用。

更新：2026-11-01。001已交付归档/r2、7/7，API37/37与Vue21项；原生链使用临时Init自驱注入再读态，覆盖边界保留。 本轮未重跑产品验收。

## 运行

安装对应版本的 `auto` CLI 后，从本仓根执行：

```sh
auto run
auto run -r vm
```

前端端口：`17838`；Rust后端：`17839`。

## 来源与组合

来源提交、路径与文件 hash 见 `SOURCE-IMPORT.json`。首次导入提交保留在 `source-sync` 分支；完整 v0.5 恢复后从该基线导入差异，再与产品开发线合并。

AutoOS 通过 [`apps/auto-database`](https://github.com/auto-stack/auto-os/tree/main/apps/auto-database) submodule 固定本仓版本；教学 Demo 保留在来源仓。

已有测试随源导入；端口与平台相关测试需要按本仓配置准备运行环境。安装/启动与双端完整功能验收是不同检查项。

## 基本能力补齐计划（2026-10-29）

[DATABASE-001：真实只读 SQLite 浏览与查询](docs/plans/archived/001-real-sqlite-browser.md) 为本app的基础能力执行合同，已交付归档/r2；原生Init注入证据边界由002接续。
总状态与前置见 [AutoOS B类总跟踪表](https://github.com/auto-stack/auto-os/blob/main/docs/plans/b-apps-basic-capabilities.md)。基础能力通过后再考虑Linux；A类统一等待 auto-os-distro 完成 Nix＋COSMIC 基础，后续增强另会话。

开发使用独立 clone `D:/autostack/auto-database` 的 main；AutoOS 内对应子模块仅固定已交付提交，流程见 [App开发与子模块](https://github.com/auto-stack/auto-os/blob/main/docs/design/strategy/app-submodule-workflow.md)。


## 当前后续计划（2026-11-02）

[DATABASE-002：原生真实操作与独立运行验收](docs/plans/002-standalone-native-user-flow.md) 为 **executing/r1、实施中（T-00..T-04 完成，T-05 收尾）**。实测结论（证据：[evidence/002 决策稿](docs/plans/evidence/002/native-ui-decision.md)）：

- **API/拒写门 37/37 保持全绿**；独立准备/启动门（错tool/端口占用/邻居失败旁观者）全绿；D-05 敏感性控制（错库断言非零、Init 注入 hash 护栏、确定性控制）全绿。
- **Vue 轨修复并全绿（21/21，含 UI 全链 55/55）**：新 CLI 生成器 R001 拒绝两表 `:key="ri"` 重名，控制台表循环变量改 `qi`（一行，语义不变）。
- **原生轨阻塞在框架缺陷**：未改 Init 的真实输入/打开/关闭驱动链已打通至状态翻转（type→WPathInput、find(button)→press→WOpenDb 均有 handler 回执），但 auto-ui-runtime iced 投影在 connected 翻转重渲染时 `container.rs:291` 竞态崩溃（压测 7/7 launch 崩）→ **挂 auto-ui owner 前置**，原生必需门（AC-02/03/04 原生部分）保持未完成，待用户决策（等修复/缩减验收/授权跨仓修复）。
- 进程纪律已换归属制：只按本次 spawn 树记录清理，不凭端口/命令行相似杀进程；失败/占用端口不伤旁观实例。

先T-00核验实际源码/CLI/编译或渲染tool、已有SDK、冷准备与失败边界；实证缺项才转实际owner最小前置。既有测试入口继续复用，历史绿总数不能替代新必需UI操作。只用隔离数据/本次进程；不清共享target或终止用户实例。无实证业务缺口时不为完成计划强改业务源码。

[路线图](docs/roadmap-v0.6.md) · [现实现规范](docs/specs/database/basic-capabilities.md)。开发与顺序复审在D:/autostack/auto-database独立clone main，一app一写入者；不在OS组合子模块开发，不建junction/symlink。各app独立验收后由统一OS计划装配，Linux仍WAIT_DISTRO_M1。

002必需UI门不得临时改Init或用API/直接store消息代做输入；vm_e2e_hook只保留历史诊断用途（D-05 注入检测以其为受控反例）。只读边界保持，不新增数据库写入。
