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


## 当前后续计划

[DATABASE-002：原生真实操作与独立运行验收](docs/plans/archived/002-standalone-native-user-flow.md) **已交付归档/r1（2026-11-03）**：未改 .Init 的真实 MCP 输入链（autoui_type/find/press 带 handler 回执、树选择经 on_select 携项 id）原生门 `--profile vm` 59/59、`--profile vue` 55/55（T-06 终审双端实跑，绑定当次 CLI/tool 身份）；独立启动/进程归属/只读 oracle/D-05 反注入合同见 [standalone-native-acceptance 规范](docs/specs/database/standalone-native-acceptance.md)。已知环境边界：共享工具链 release 生成消费者构建对机器负载边际敏感（计划 §10 F-2），复跑门择安静窗口。

下一个 app 级计划未立；后续为 AutoOS 统一装配（另立统一OS计划，接收各 app 已单独验证的提交）与 Linux 支持（WAIT_DISTRO_M1）。

[路线图](docs/roadmap-v0.6.md) · [现实现规范](docs/specs/database/basic-capabilities.md)。开发与顺序复审在D:/autostack/auto-database独立clone main，一app一写入者；不在OS组合子模块开发，不建junction/symlink。各app独立验收后由统一OS计划装配，Linux仍WAIT_DISTRO_M1。

002必需UI门不得临时改Init或用API/直接store消息代做输入；vm_e2e_hook只保留历史诊断用途（D-05 注入检测以其为受控反例）。只读边界保持，不新增数据库写入。
