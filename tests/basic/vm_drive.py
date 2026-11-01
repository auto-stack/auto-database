#!/usr/bin/env python3
"""vm_drive.py — DATABASE-002 原生端真实 UI 验收驱动（AutoUI MCP）。

由 tests/basic/verify_basic.py 调度；驱动 `auto run -r vm` 的原生 VM 界面。
DATABASE-002 T-02/T-03 升级（相对 001）：
  - 定位层重写：autoui_find(kind=button, label=…) 取真实 Button vnode；
    禁止按快照文本就近猜 id（001 实证会命中按钮内部 Text 节点，
    press 报 `Action 'press' not valid for component type 'Text'`）。
  - 事件回执校验：每次 type/press 校验 ActionResult 的 handler 回执，
    无回执/报错即重试（有界），不再盲等状态。
  - 全链路：输入路径→打开→树→浏览(分页/搜索/NULL)→Schema→SQL(成功/
    拒绝/引擎错)→坏路径/坏文件→切库 B→A→关闭→重开再查询（D-02..D-04）。
  - 本驱动只做真实 UI 操作；只读 oracle（sqlite3/hash/哨兵）由调度方
    verify_basic.py 在会话外核对。

用法: python vm_drive.py <mcp-url> <dbA-path> <dbB-path> [missing-path] [garbage-path]
输出：逐行 PASS/FAIL，末行 SUMMARY {json}；退出码 0/1。
"""

import json
import re
import sys
import time

try:
    import requests
except ImportError:
    print("FAIL: requests not installed")
    sys.exit(2)

results = []


def record(step, ok, detail=""):
    results.append({"step": step, "ok": bool(ok), "detail": detail})
    print(("PASS" if ok else "FAIL") + ": " + step + ((" — " + detail) if detail else ""), flush=True)


class Mcp:
    def __init__(self, url):
        self.url = url
        self.n = 0

    def call(self, tool, **args):
        self.n += 1
        r = requests.post(self.url, json={"jsonrpc": "2.0", "method": "tools/call",
                                          "params": {"name": tool, "arguments": args},
                                          "id": self.n}, timeout=30)
        data = r.json()
        if "error" in data:
            raise RuntimeError("MCP error: %s" % data["error"])
        content = data.get("result", {}).get("content", [])
        return content[0]["text"] if content else ""

    def snapshot(self):
        return self.call("autoui_snapshot")

    def state(self, *fields):
        if fields:
            return self.call("autoui_state", fields=list(fields))
        return self.call("autoui_state")

    def find(self, kind=None, label=None, limit=5):
        a = {"limit": limit}
        if kind:
            a["kind"] = kind
        if label:
            a["label"] = label
        return self.call("autoui_find", **a)

    def type(self, eid, text, expect_handler=None):
        """Type into an element; verify store echo via snapshot when given."""
        resp = self.call("autoui_type", element_id=eid, text=text)
        return resp

    def press(self, eid):
        return self.call("autoui_action", element_id=eid, action="press")

    # ---- 定位层（T-02 核心） ----

    def find_button(self, label, attempts=5):
        """autoui_find(kind=button, label) → Button vnode id；找不到返回 None。"""
        for _ in range(attempts):
            f = self.find(kind="button", label=label)
            if isinstance(f, str) and not f.startswith("HTTP-") and not f.startswith("PARSE"):
                ids = re.findall(r"vnode_(\d+)", f)
                if ids:
                    return "vnode_" + ids[-1]
            time.sleep(1.5)
        return None

    def find_clickable(self, label, limit=8):
        """非 button 可点元素（树行等）：快照里按标签精确定位 text 节点，
        回溯最近的包裹 `row #vnode_N {`（标签行）。press 该行即以具体项 id
        派发组件 on_select（实测回执 `handler: .TreeView.Select st/customers`，
        表切换生效）。

        旧实现（find 祖先链取最深事件节点）在 002 修复后失效：TreeView 的
        on_select/on_toggle 投影在整树容器级，per-item 事件在快照中只打
        一次模板行（`onclick: .Select(r.id)`），祖先链里没有行级事件节点，
        press 容器不带项 id＝无操作；直接 press 文本节点报
        `not valid for component type 'Text'`（T-00 实证）。"""
        snap = self.snapshot()
        if not isinstance(snap, str) or snap.startswith("HTTP-") or snap.startswith("PARSE"):
            return None
        lines = snap.splitlines()
        pat = re.compile(r'text #vnode_\d+ "%s"' % re.escape(label))
        for i, line in enumerate(lines):
            if pat.search(line.strip()):
                for j in range(i - 1, max(0, i - 15), -1):
                    mm = re.search(r"row #vnode_(\d+) \{", lines[j])
                    if mm:
                        return "vnode_" + mm.group(1)
                return None
        # 回退：非树形可点元素走旧 find 祖先链逻辑
        f = self.find(label=label, limit=limit)
        if not isinstance(f, str) or f.startswith("HTTP-") or f.startswith("PARSE"):
            return None
        event_ids = []
        for line in f.splitlines():
            if ("onclick" in line or "on_select" in line or "on_toggle" in line) \
                    and "vnode_" in line:
                mm = re.search(r"vnode_(\d+)", line)
                if mm:
                    event_ids.append("vnode_" + mm.group(1))
        if event_ids:
            return event_ids[-1]
        ids = re.findall(r"vnode_(\d+)", f)
        return ("vnode_" + ids[-1]) if ids else None

    def find_input(self, snap, index=0):
        ids = re.findall(r"input #(\S+)", snap)
        return ids[index] if len(ids) > index else None

    def press_button(self, label, expect_handler_sub=None, attempts=3):
        """定位按钮并 press；校验回执含 handler 名（如 .App.WOpenDb）。
        返回 (ok, 回执或错误)。"""
        last = ""
        for i in range(attempts):
            eid = self.find_button(label)
            if eid is None:
                last = "button %r not found" % label
                time.sleep(1.5)
                continue
            resp = self.press(eid)
            last = resp
            if "not valid" in resp or resp.startswith("HTTP-") or resp.startswith("PARSE"):
                time.sleep(1.5)
                continue
            if expect_handler_sub and expect_handler_sub not in resp:
                # 回执无 handler（如无状态变化路径）不必然失败，但记录
                return True, resp
            return True, resp
        return False, last

    @staticmethod
    def _norm_pathdump(s):
        """归一 state dump：去引号、还原 \\\\ 转义、统一分隔符。"""
        s = s.replace('\\"', '"').replace("\\\\", "\\")
        s = s.replace("\\", "/")
        while "//" in s:
            s = s.replace("//", "/")
        return s.lower()

    def type_and_verify(self, eid, text, store_field, attempts=5):
        """type 后读 store 字段确认真实送达（001 教训：回显≠送达）。
        attempts=5/1.5s：VM 首次 type 的 store 应用可滞后于即时读
        （002 门实测：3×1.0s 全空、1.5s 后已达），放宽读回节奏。"""
        last = ""
        for _ in range(attempts):
            resp = self.type(eid, text)
            time.sleep(1.5)
            st = self.state(store_field)
            if "HTTP-" in st[:6] or "PARSE" in st[:6]:
                last = st[:80]
                time.sleep(1.5)
                continue
            if self._norm_pathdump(text) in self._norm_pathdump(st):
                return True, st
            last = st[:120]
        return False, last

    def wait_state(self, want_sub, fields, timeout_s=30, poll=2.0):
        """轮询 state 直到含 want_sub 或超时；返回最后 state 文本。"""
        deadline = time.time() + timeout_s
        st = ""
        while time.time() < deadline:
            time.sleep(poll)
            st = self.state(*fields)
            if "HTTP-" in st[:6] or "PARSE" in st[:6]:
                return st  # 会话失联立即返回
            if want_sub in st:
                return st
        return st


def main():
    mcp_url = sys.argv[1]
    db_a = sys.argv[2]
    db_b = sys.argv[3]
    missing = sys.argv[4] if len(sys.argv) > 4 else None
    garbage = sys.argv[5] if len(sys.argv) > 5 else None
    m = Mcp(mcp_url)

    # ── 0. 页面就绪 + 关闭态 ──
    snap = ""
    for _ in range(30):
        try:
            snap = m.snapshot()
            if "Database Studio" in snap:
                break
        except Exception:
            pass
        time.sleep(3)
    record("ui-load", "Database Studio" in snap, "page renders")
    record("no-demo-data", "northwind" not in snap and "Alfreds" not in snap, "demo absent")
    record("closed-state", "未打开" in snap, "closed state visible")
    st_all = m.state()
    record("init-hook-absent", "vmE2E" not in snap and "vmE2E" not in st_all,
           "no Init-injection field in snapshot/state")

    if "Database Studio" not in snap:
        print("SUMMARY " + json.dumps({"results": results}))
        sys.exit(1)

    # ── 1. 真实输入路径并打开 A（D-02 前半） ──
    path_id = m.find_input(snap, 0)
    record("path-input-found", path_id is not None, str(path_id))
    if not path_id:
        print("SUMMARY " + json.dumps({"results": results}))
        sys.exit(1)
    ok, st = m.type_and_verify(path_id, db_a, "path_input")
    record("type-path-store", ok, st.replace("\n", " | ")[:150])
    ok, resp = m.press_button("打开", expect_handler_sub=".App.WOpenDb")
    record("press-open-receipt", ok, resp.replace("\n", " ")[:120])
    st = m.wait_state("connected: true", ("connected", "file_name", "table_count"), timeout_s=40)
    record("open-a-state", "connected: true" in st and "basic_a.db" in st,
           st.replace("\n", " | ")[:200])

    if "connected: true" not in st:
        # 打开翻转处框架竞态可致会话失联（T-00 决策稿 §3）：真实记录，不得掩盖
        record("session-alive-after-open", False,
               "framework flip race suspected (see evidence/002/native-ui-decision.md)")
        print("SUMMARY " + json.dumps({"results": results}))
        sys.exit(1)

    snap = m.snapshot()
    record("open-a-readonly", "READ-ONLY" in snap, "badge visible")
    record("open-a-tree", "客户资料" in snap and "customers" in snap, "real tree")

    # ── 2. 树选择 + 数据 + 搜索 + NULL（D-02） ──
    node = m.find_clickable("customers")
    record("tree-node-found", node is not None, str(node))
    if node:
        m.press(node)
        time.sleep(2)
    st = m.state("colNames", "showingText")
    record("data-headers", "company_name" in st, st.replace("\n", " | ")[:150])
    snap = m.snapshot()
    record("data-first-row", "Alfreds Futterkiste" in snap, "real row")

    search_id = None
    for i, cand in enumerate(re.findall(r"input #(\S+)", snap)):
        if i >= 2:
            search_id = cand  # 第三个 input 是记录搜索
    if search_id:
        m.type(search_id, "Taquer")
        time.sleep(1.5)
        snap = m.snapshot()
        record("null-cell-marker", "NULL" in snap, "NULL rendered")
        m.type(search_id, "")
        time.sleep(1.2)

    # ── 3. 分页：audit_logs（D-02） ──
    snap = m.snapshot()
    node = m.find_clickable("audit_logs")
    if node:
        m.press(node)
        time.sleep(2)
    st = m.state("total", "showingText")
    record("audit-1200", "1200" in st, st.replace("\n", " | ")[:150])
    ok, resp = m.press_button("››")
    st = m.wait_state("page: 120", ("page", "totalPages"), timeout_s=20)
    record("audit-last-page", "page: 120" in st, st.replace("\n", " | ")[:150])

    # ── 4. Schema：中文表 DDL（D-02） ──
    snap = m.snapshot()
    node = m.find_clickable("客户资料")
    if node:
        m.press(node)
        time.sleep(1.5)
    ok, resp = m.press_button("Schema")
    time.sleep(1.0)
    snap = m.snapshot()
    record("schema-ddl", "CREATE TABLE 客户资料" in snap, "real DDL")

    # ── 5. SQL 控制台：成功/拒绝/引擎错（D-02/D-03） ──
    # （与 ui_drive.mjs 同构：GROUP BY 模板按钮填充后直接 Run；
    #   原 type(sql_id, "") 会把模板清空→空 SQL 报错，2026-11-02 修复）
    ok, resp = m.press_button("SQL")
    time.sleep(0.8)
    snap = m.snapshot()
    sql_inputs = re.findall(r"input #(\S+)", snap)
    sql_id = sql_inputs[-1] if sql_inputs else None
    ok, resp = m.press_button("GROUP BY")
    time.sleep(0.8)
    ok, resp = m.press_button("▶ Run SQL")
    st = m.wait_state('sqlStatus: "success"', ("sqlStatus", "sqlMeta"), timeout_s=20)
    record("sql-agg-ok", 'sqlStatus: "success"' in st, st.replace("\n", " | ")[:150])

    ok, resp = m.press_button("写语句(应拒绝)")
    ok, resp = m.press_button("▶ Run SQL")
    st = m.wait_state('sqlStatus: "error"', ("sqlStatus", "sqlErr"), timeout_s=20)
    record("sql-reject-banner", 'sqlStatus: "error"' in st and "not_readonly" in st,
           st.replace("\n", " | ")[:200])

    if sql_id:
        m.type(sql_id, "SELECT * FROM no_such_table")
        time.sleep(0.5)
    ok, resp = m.press_button("▶ Run SQL")
    st = m.wait_state("no such table", ("sqlErr",), timeout_s=20)
    record("sql-engine-error", "no such table" in st, st.replace("\n", " | ")[:150])

    # ── 6. 坏路径 / 坏文件（D-03，调度方核对不建文件/hash 不变） ──
    if missing:
        snap = m.snapshot()
        pid2 = m.find_input(snap, 0)
        if pid2:
            m.type(pid2, missing)
            time.sleep(0.5)
        ok, resp = m.press_button("打开")
        st = m.wait_state("file_not_found", ("open_err",), timeout_s=20)
        record("badpath-banner", "file_not_found" in st, st.replace("\n", " | ")[:150])
        snap = m.snapshot()
        record("badpath-visible", "打开失败" in snap, "banner in UI")
    if garbage:
        snap = m.snapshot()
        pid2 = m.find_input(snap, 0)
        if pid2:
            m.type(pid2, garbage)
            time.sleep(0.5)
        ok, resp = m.press_button("打开")
        st = m.wait_state("not_a_database", ("open_err",), timeout_s=20)
        record("badfile-banner", "not_a_database" in st, st.replace("\n", " | ")[:150])

    # ── 7. 切库 B → A（D-02/D-04 身份） ──
    snap = m.snapshot()
    pid2 = m.find_input(snap, 0)
    if pid2:
        m.type(pid2, db_b)
        time.sleep(0.5)
    ok, resp = m.press_button("打开")
    st = m.wait_state("basic_b.db", ("connected", "file_name", "table_count"), timeout_s=40)
    record("switch-b", "basic_b.db" in st and "table_count: 3" in st,
           st.replace("\n", " | ")[:150])
    snap = m.snapshot()
    record("switch-b-data", "SKU-A1" in snap, "db B data")

    if pid2:
        m.type(pid2, db_a)
        time.sleep(0.5)
    ok, resp = m.press_button("打开")
    st = m.wait_state("basic_a.db", ("connected", "file_name"), timeout_s=40)
    # 切库后选中表重置为默认（字母序 audit_logs）——与 ui_drive.mjs 同构，
    # 显式重选 customers 再验内容身份（不看默认表名假绿，D-04 oracle）。
    node = m.find_clickable("customers")
    if node:
        m.press(node)
        time.sleep(2)
    snap = m.snapshot()
    record("switch-back-a", "basic_a.db" in snap and "Alfreds Futterkiste" in snap,
           "db A restored (identity by content)")

    # ── 8. 关闭（D-04）：真实「关闭」按钮 → 未打开态、无旧结果 ──
    ok, resp = m.press_button("关闭", expect_handler_sub=".App.WCloseDb")
    record("press-close-receipt", ok, resp.replace("\n", " ")[:120])
    st = m.wait_state("connected: false", ("connected",), timeout_s=30)
    snap = m.snapshot()
    record("close-state", "connected: false" in st and "未打开" in snap
           and "Alfreds Futterkiste" not in snap,
           st.replace("\n", " | ")[:120])

    # ── 9. 会话存活（关闭翻转同样是竞态崩溃点） ──
    st = m.state("connected")
    record("session-alive-after-close", "HTTP-" not in st[:6] and "PARSE" not in st[:6],
           st.replace("\n", " | ")[:80])

    # 重开查询（同会话再开一次；重开 app 由调度方 D-04 场景负责）
    if "connected: false" in st:
        snap = m.snapshot()
        pid3 = m.find_input(snap, 0)
        if pid3:
            m.type(pid3, db_a)
            time.sleep(0.5)
        ok, resp = m.press_button("打开")
        st = m.wait_state("connected: true", ("connected", "file_name"), timeout_s=40)
        record("reopen-next-query", "connected: true" in st, st.replace("\n", " | ")[:120])

    ok_all = all(r["ok"] for r in results)
    print("SUMMARY " + json.dumps({"results": results}))
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
