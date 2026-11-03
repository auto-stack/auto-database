# auto-database：独立可用性路线图

更新：2026-11-03。以Spec与真实交付为准，计划目标不表示已实现。

| 顺序 | 计划/成果 | 当前状态与边界 |
|---|---|---|
| 基础 | [001首轮能力](plans/archived/001-real-sqlite-browser.md) | 001已交付归档/r2、7/7，API37/37与Vue21项；原生链使用临时Init自驱注入再读态，覆盖边界保留。 |
| 当前优先 | [DATABASE-002：原生真实操作与独立运行验收](plans/002-standalone-native-user-flow.md) | executing/r1 收尾（T-00..T-06 完成）：§10 决议 c 跨仓最小修复（auto-ui master 76b0340 + 驱动适配 2d7a988）后原生门全绿——API37/37、独立启动门、D-05控制全绿，vm 59/59（work×2+T-06复审×1）、vue 55/55；T-06 F-1 文档项修复后进入 merge 归档；落地复跑门择安静窗口（F-2）。证据：plans/evidence/002/native-ui-decision.md |
| 之后 | AutoOS统一装配 | 另立统一OS计划，接收各app单独验证/推送的精确提交；本轮不改pin |
| 之后 | Linux支持 | WAIT_DISTRO_M1，等Nix＋COSMIC发行版基础；不阻塞本app本机任务 |

补未改Init的真实路径输入、树选择、SQL/错误/切库/关闭和下一次操作，独立sqlite3/hash/句柄oracle保持只读。

行编辑/DDL写入、远程/加密库、ER图另排，保持只读SQLite。

工作位D:/autostack/auto-database独立clone main，实施与独立上下文复审顺序共用，一app一写入者。复用既有验证入口；真实UI/磁盘oracle对应本次源码和CLI/tool，无必需skip/零场景。失败控制要能检测实际错误，只回收本次进程/隔离数据，不清共享缓存。

[README](../README.md) · [现实现规范](specs/database/basic-capabilities.md)
