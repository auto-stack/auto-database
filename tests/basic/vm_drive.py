#!/usr/bin/env python3
"""vm_drive.py — DATABASE-001 T-05 VM 端真实 UI 验收驱动（AutoUI MCP）。

由 tests/basic/verify_basic.py 调度；驱动 `auto run -r vm` 的原生 VM 界面：
autoui_snapshot / autoui_state / autoui_type / autoui_action。
链路与 Vue 端一致：打开→树→浏览(分页/搜索/NULL)→Schema→SQL(成功/拒绝/引擎错)→切库。

用法: python vm_drive.py <mcp-url> <dbA-path> <dbB-path>
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
                                          "id": self.n}, timeout=20)
        data = r.json()
        if "error" in data:
            raise RuntimeError("MCP error: %s" % data["error"])
        content = data.get("result", {}).get("content", [])
        return content[0]["text"] if content else ""

    def snapshot(self):
        return self.call("autoui_snapshot")

    def state(self, *fields):
        return self.call("autoui_state", fields=list(fields))

    def type(self, element_id, text):
        return self.call("autoui_type", element_id=element_id, text=text)

    def press(self, element_id):
        return self.call("autoui_action", element_id=element_id, action="press")

    def find_id(self, snap, pattern):
        m = re.search(pattern, snap)
        return m.group(1) if m else None

    def click_by_text(self, snap, text):
        """点击快照中含指定文本的元素（id 与文本同行时优先；否则回溯最近 id）。"""
        pat = re.compile(r"#(\S+)")
        cur = None
        for line in snap.splitlines():
            m = pat.search(line)
            if m:
                cur = m.group(1)
            if (('"%s"' % text) in line or text in line) and cur:
                return cur
        return None


def main():
    mcp_url = sys.argv[1]
    db_a = sys.argv[2]
    db_b = sys.argv[3]
    m = Mcp(mcp_url)

    # 首个快照可能为空（MCP 渲染时序）：等到 Database Studio 出现为止
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

    # 1. 输入路径并打开 A
    path_id = m.find_id(snap, r'input #(\S+)')
    if not path_id:
        # 输入框是第一个 input 元素
        m2 = re.search(r"input #(\S+)", snap)
        path_id = m2.group(1) if m2 else None
    record("path-input-found", path_id is not None, str(path_id))
    if path_id:
        # VM 事件注入在负载下偶发丢失：type+press 重试直至 connected=true（30s）
        opened = False
        for attempt in range(3):
            m.type(path_id, db_a)
            time.sleep(0.8)
            snap = m.snapshot()
            open_id = m.click_by_text(snap, "打开")
            if attempt == 0:
                record("open-btn-found", open_id is not None, str(open_id))
            if not open_id:
                continue
            m.press(open_id)
            for _ in range(10):
                time.sleep(2)
                st = m.state("connected", "file_name", "table_count", "view_count", "index_count")
                if "connected: true" in st:
                    opened = True
                    break
            if opened:
                break
        record("open-a-state", opened and 'basic_a.db' in st and 'table_count: 4' in st, st[:200])

        snap = m.snapshot()
        record("open-a-readonly", "READ-ONLY" in snap, "badge visible")
        record("open-a-tree", "客户资料" in snap and "customers" in snap, "real tree")

        # 2. 真实数据 + NULL（显式点 customers；自动选中首张非内部表）
        cust_id = m.click_by_text(snap, "customers")
        if cust_id:
            m.press(cust_id)
            time.sleep(2)
        st = m.state("colNames", "showingText")
        record("data-headers", "company_name" in st, st[:150])
        snap = m.snapshot()
        record("data-first-row", "Alfreds Futterkiste" in snap, "real row")
        search_id = m.click_by_text(snap, "Filter records")  # 定位邻近输入
        # 直接用第二个 input（第一个是路径，第二个是树过滤，第三个是搜索）
        inputs = re.findall(r"input #(\S+)", snap)
        if len(inputs) >= 3:
            m.type(inputs[2], "Taquer")
            time.sleep(1.2)
            snap = m.snapshot()
            record("null-cell-marker", "NULL" in snap, "NULL rendered")
            m.type(inputs[2], "")
            time.sleep(1.0)

        # 3. 分页：audit_logs
        snap = m.snapshot()
        node_id = m.click_by_text(snap, "audit_logs")
        if node_id:
            m.press(node_id)
            time.sleep(1.5)
        st = m.state("total", "showingText")
        record("audit-1200", "1200" in st, st[:150])
        snap = m.snapshot()
        last_id = m.click_by_text(snap, "››")
        if last_id:
            m.press(last_id)
            time.sleep(1.2)
        st = m.state("page", "totalPages")
        record("audit-last-page", "page: 120" in st, st[:150])

        # 4. Schema：中文表 DDL
        snap = m.snapshot()
        node_id = m.click_by_text(snap, "客户资料")
        if node_id:
            m.press(node_id)
            time.sleep(1.2)
        snap = m.snapshot()
        tab_id = m.click_by_text(snap, "Schema")
        if tab_id:
            m.press(tab_id)
            time.sleep(1.0)
        snap = m.snapshot()
        record("schema-ddl", "CREATE TABLE 客户资料" in snap, "real DDL")

        # 5. SQL 控制台：成功/拒绝/引擎错误
        snap = m.snapshot()
        tab_id = m.click_by_text(snap, "SQL")
        if tab_id:
            m.press(tab_id)
            time.sleep(0.8)
        snap = m.snapshot()
        sql_id = None
        for cand in re.findall(r"input #(\S+)", snap):
            sql_id = cand  # 最后一个 input 是 SQL 输入
        agg_id = m.click_by_text(snap, "GROUP BY")
        if agg_id:
            m.press(agg_id)
            time.sleep(0.4)
        run_id = m.click_by_text(snap, "Run SQL")
        if run_id:
            m.press(run_id)
            time.sleep(1.5)
        st = m.state("sqlStatus", "sqlMeta")
        record("sql-agg-ok", 'sqlStatus: "success"' in st, st[:150])

        rej_id = m.click_by_text(m.snapshot(), "写语句")
        if rej_id:
            m.press(rej_id)
            time.sleep(0.4)
        snap = m.snapshot()
        run_id = m.click_by_text(snap, "Run SQL")
        if run_id:
            m.press(run_id)
            time.sleep(1.2)
        st = m.state("sqlStatus", "sqlErr")
        record("sql-reject-banner", 'sqlStatus: "error"' in st and "not_readonly" in st, st[:200])

        if sql_id:
            m.type(sql_id, "SELECT * FROM no_such_table")
            time.sleep(0.4)
        snap = m.snapshot()
        run_id = m.click_by_text(snap, "Run SQL")
        if run_id:
            m.press(run_id)
            time.sleep(1.2)
        st = m.state("sqlErr")
        record("sql-engine-error", "no such table" in st, st[:150])

        # 6. 切库 B → A
        snap = m.snapshot()
        inputs = re.findall(r"input #(\S+)", snap)
        path_id2 = inputs[0] if inputs else None
        if path_id2:
            m.type(path_id2, db_b)
            time.sleep(0.4)
        snap = m.snapshot()
        open_id = m.click_by_text(snap, "打开")
        if open_id:
            m.press(open_id)
            time.sleep(2)
        st = m.state("file_name", "table_count")
        record("switch-b", 'basic_b.db' in st and 'table_count: 3' in st, st[:150])
        snap = m.snapshot()
        record("switch-b-data", "SKU-A1" in snap, "db B data")
        if path_id2:
            m.type(path_id2, db_a)
            time.sleep(0.4)
        snap = m.snapshot()
        open_id = m.click_by_text(snap, "打开")
        if open_id:
            m.press(open_id)
            time.sleep(2)
        snap = m.snapshot()
        cust_id2 = m.click_by_text(snap, "customers")
        if cust_id2:
            m.press(cust_id2)
            time.sleep(2)
        snap = m.snapshot()
        record("switch-back-a", "Alfreds Futterkiste" in snap, "db A restored")

    ok_all = all(r["ok"] for r in results)
    print("SUMMARY " + json.dumps({"results": results}))
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
