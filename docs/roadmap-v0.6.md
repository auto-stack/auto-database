# auto-database：独立可用性路线图

更新：2026-11-02。以Spec与真实交付为准，计划目标不表示已实现。

| 顺序 | 计划/成果 | 当前状态与边界 |
|---|---|---|
| 基础 | [001首轮能力](plans/archived/001-real-sqlite-browser.md) | 001已交付归档/r2、7/7，API37/37与Vue21项；原生链使用临时Init自驱注入再读态，覆盖边界保留。 |
| 当前优先 | [DATABASE-002：原生真实操作与独立运行验收](plans/002-standalone-native-user-flow.md) | executing/r1 实施中：API37/37、独立启动门、D-05控制、Vue轨（R001键适配后21/21）全绿；原生真实输入链已通至状态翻转，被 auto-ui-runtime iced 投影竞态（container.rs:291，压测7/7崩）阻塞→auto-ui owner前置，原生必需门未完成待用户决策。证据：plans/evidence/002/native-ui-decision.md |
| 之后 | AutoOS统一装配 | 另立统一OS计划，接收各app单独验证/推送的精确提交；本轮不改pin |
| 之后 | Linux支持 | WAIT_DISTRO_M1，等Nix＋COSMIC发行版基础；不阻塞本app本机任务 |

补未改Init的真实路径输入、树选择、SQL/错误/切库/关闭和下一次操作，独立sqlite3/hash/句柄oracle保持只读。

行编辑/DDL写入、远程/加密库、ER图另排，保持只读SQLite。

工作位D:/autostack/auto-database独立clone main，实施与独立上下文复审顺序共用，一app一写入者。复用既有验证入口；真实UI/磁盘oracle对应本次源码和CLI/tool，无必需skip/零场景。失败控制要能检测实际错误，只回收本次进程/隔离数据，不清共享缓存。

[README](../README.md) · [现实现规范](specs/database/basic-capabilities.md)
