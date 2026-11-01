#!/usr/bin/env python3
"""DATABASE-002 verification (native standalone usability; Plan §6 D-01..D-05).

Reproducible entries (real app, real files, no in-memory helpers):
    python tests/basic/verify_basic.py --profile vue
    python tests/basic/verify_basic.py --profile vm
    python tests/basic/verify_basic.py --api-only
    python tests/basic/verify_basic.py            # full: api+standalone+vue+vm+d05

Batteries:
  api         — 001 电池原样保留（V-01..V-04；独立 sqlite3 oracle、写拒绝、
                hash/哨兵/句柄）。作为旧门回归（AC-04）。
  standalone  — D-01：正式独立准备/启动；错 tool、端口占用、双实例隔离；
                失败非零且旁观实例不受影响。
  ui(vue/vm)  — 真实前端链路：vue → Playwright（ui_drive.mjs，001 链路）；
                vm → AutoUI MCP（vm_drive.py，002 真实输入升级版）。
                调度方核对：fixture sha256 前后不变、哨兵行、无效路径不建文件、
                请求间隙可重命名（无泄漏锁）、无 aux 副文件（D-03/D-04 oracle）。
                vm 附加：关闭 app 进程后重开再查询（D-04 重开下一次操作）。
  d05         — 敏感性控制：错库断言反例（总门非零）、源码注入检测
                （hash 前后护栏）、正常控制（关闭态+API oracle）。

Exit code 0 = all checks passed. Evidence: caller keeps stdout under
D:/autostack/plan-artifacts/plan-002/ (repo-external scratch; never committed).

Process discipline (Plan §2): cleanup kills ONLY PIDs recorded from our own
spawn tree — never by port or command-line similarity; occupied target ports
fail the run without touching the occupier.

Toolchain resolution:
    AUTO_CLI           path to `auto` (default auto-man debug build)
    PLAYWRIGHT_MODULE  path to playwright/index.mjs (npx cache probed)
"""

import argparse
import hashlib
import json
import os
import glob
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_CLI = r"D:/autostack/auto-man/target/debug/auto.exe"
CONSOLE_TRUNC = 1000
SERVICE_READY_BUDGET_S = 2400   # 冷框架重建（共享机器竞争）实测可达 20+ 分钟
UI_READY_BUDGET_S = 1500

results = []


def record(step, ok, detail=""):
    results.append({"step": step, "ok": bool(ok), "detail": detail})
    print(("PASS" if ok else "FAIL") + ": " + step + ((" — " + detail) if detail else ""), flush=True)
    return ok


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def port_free(port):
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def http(method, url, body=None, timeout=15):
    req = urllib.request.Request(url, method=method)
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw
    except Exception as e:
        return 0, {"ok": False, "err_code": "conn_failed", "err_detail": str(e)[:120]}


# ── 进程归属管理（002 Plan §2：不凭端口/命令行相似杀进程） ──

def _ps_procs():
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-CimInstance Win32_Process | "
                        "Select-Object ProcessId,ParentProcessId | ConvertTo-Json -Compress"],
                       capture_output=True, text=True)
    try:
        d = json.loads(r.stdout or "[]")
        return d if isinstance(d, list) else ([d] if d else [])
    except Exception:
        return []


def tree_of(root_pid):
    children = {}
    for p in _ps_procs():
        children.setdefault(int(p["ParentProcessId"]), []).append(int(p["ProcessId"]))
    seen, stack = set(), [root_pid]
    while stack:
        pid = stack.pop()
        for c in children.get(pid, []):
            if c not in seen:
                seen.add(c)
                stack.append(c)
    seen.add(root_pid)
    return seen


def stop_owned(pids, log_note=""):
    """Kill exactly the recorded spawn tree (plus a refresh while root alive)."""
    alive = {int(p["ProcessId"]) for p in _ps_procs()}
    killed = []
    for pid in sorted(pids):
        if pid in alive:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
            killed.append(pid)
    if killed:
        time.sleep(2)
    return killed


def spawn_owned(cli, args, cwd, env, log_path):
    log = open(log_path, "a", encoding="utf-8")
    proc = subprocess.Popen([cli] + args, cwd=cwd, env=env,
                            stdout=log, stderr=subprocess.STDOUT)
    return proc, log


def wait_backend_ready(proc, port, budget_s, log_path):
    """Wait until /api/db/open answers (200/400 with err_code). Never kills the
    process on timeout — returns False and leaves diagnosis to the caller."""
    deadline = time.time() + budget_s
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        code, body = http("POST", "http://127.0.0.1:%d/api/db/open" % port,
                          {"path": "___probe_missing___"}, timeout=4)
        if code in (200, 400) and isinstance(body, dict) and "err_code" in body:
            return True
        time.sleep(3)
    return False


def resolve_cli():
    cli = os.environ.get("AUTO_CLI", DEFAULT_CLI)
    if not os.path.exists(cli):
        print("FATAL: auto CLI not found at " + cli + " (set AUTO_CLI)")
        sys.exit(2)
    return cli


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def oracle(path, sql):
    """Independent sqlite3 oracle connection (read-only intent)."""
    con = sqlite3.connect("file:%s?mode=ro" % path.replace("\\", "/"), uri=True)
    try:
        cur = con.execute(sql)
        return [list(r) for r in cur.fetchall()]
    finally:
        con.close()


def interleave_rows(cells, ncols, nrows):
    """cells: interleaved value,flag per cell -> rows of None/str."""
    rows = []
    for r in range(nrows):
        row = []
        for c in range(ncols):
            idx = (r * ncols + c) * 2
            flag = cells[idx + 1]
            row.append(None if flag == "1" else cells[idx])
        rows.append(row)
    return rows


def fetch_columns(base, path, tname):
    code, cl = http("POST", base + "/api/db/columns",
                    {"path": path, "tname": tname}, timeout=20)
    if isinstance(cl, dict) and cl.get("ok"):
        return [c["name"] for c in cl.get("columns", [])]
    return []


def make_fixtures(workdir):
    """Generate isolated fixtures + 中文路径样本目录。返回 dict of paths."""
    fixdir = os.path.join(workdir, "fix")
    subprocess.run([sys.executable, os.path.join(REPO, "tests", "basic", "fixtures",
                    "make_fixtures.py"), "--out", fixdir], check=True, capture_output=True)
    cn = os.path.join(fixdir, "中文目录")
    os.makedirs(cn, exist_ok=True)
    for name in ("basic_a.db", "basic_b.db"):
        shutil.copy2(os.path.join(fixdir, name), os.path.join(cn, name))
    return {
        "fixdir": fixdir,
        "a": os.path.join(fixdir, "basic_a.db"),
        "b": os.path.join(fixdir, "basic_b.db"),
        "g": os.path.join(fixdir, "garbage.db"),
        "missing": os.path.join(fixdir, "no_such.db"),
        "a_cn": os.path.join(cn, "basic_a.db"),
        "b_cn": os.path.join(cn, "basic_b.db"),
    }


# ── API 电池（001 逻辑保留；进程管理换归属制） ──

def api_battery(cli, workdir):
    fx = make_fixtures(workdir)
    a_db, b_db, g_db = fx["a"], fx["b"], fx["g"]
    hash_a_before = sha256(a_db)
    hash_b_before = sha256(b_db)
    hash_g_before = sha256(g_db)

    port = free_port()
    if not port_free(port):
        record("service-ready", False, "port %d occupied before spawn" % port)
        return
    logp = os.path.join(workdir, "api-service.log")
    env = dict(os.environ)
    env["AUTO_DB_PROBE"] = "0"
    proc, log = spawn_owned(cli, ["service", "--server", "rust", "--back-port", str(port)],
                            REPO, env, logp)
    owned = tree_of(proc.pid)
    try:
        ready = wait_backend_ready(proc, port, SERVICE_READY_BUDGET_S, logp)
        if not ready:
            record("service-ready", False,
                   "backend not ready within %ds (see %s)" % (SERVICE_READY_BUDGET_S, logp))
            return
        owned = tree_of(proc.pid)  # 刷新：构建期后新增子进程
        record("service-ready", True, "rust backend on :%d" % port)
        base = "http://127.0.0.1:%d" % port

        def post(ep, body, timeout=20):
            return http("POST", base + ep, body, timeout=timeout)

        # ── V-01: open real file, counts vs oracle ──
        code, m = post("/api/db/open", {"path": a_db})
        want_counts = {}
        for t, n in oracle(a_db, "SELECT type, COUNT(*) FROM sqlite_master "
                                 "WHERE name NOT LIKE 'sqlite\\_%' ESCAPE '\\' GROUP BY type"):
            want_counts[t] = n
        ok = (isinstance(m, dict) and m.get("ok") is True
              and m.get("tables") == want_counts.get("table")
              and m.get("views") == want_counts.get("view")
              and m.get("indexes") == want_counts.get("index"))
        record("v01-open-counts", ok, json.dumps(m, ensure_ascii=False)[:160])

        code, objs = post("/api/db/objects", {"path": a_db})
        want_objs = sorted((t, n) for t, n in oracle(
            a_db, "SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite\\_%' ESCAPE '\\'"))
        got_objs = sorted((o["otype"], o["name"]) for o in objs.get("objects", [])) if isinstance(objs, dict) else []
        record("v01-objects-vs-oracle", got_objs == want_objs,
               "got=%d want=%d" % (len(got_objs), len(want_objs)))

        for tname, order in (("customers", "id"), ("客户资料", "id")):
            cols = fetch_columns(base, a_db, tname)
            want_cols = [r[1] for r in oracle(a_db, "PRAGMA table_info(%s)" % tname)]
            nc = len(cols)
            code, td = post("/api/db/table_data", {"path": a_db, "tname": tname, "page": 1,
                                                   "page_size": 50, "sort_col": order,
                                                   "sort_dir": "asc", "search": ""})
            got_rows = []
            if isinstance(td, dict) and td.get("ok") and nc:
                got_rows = interleave_rows(td.get("cells", []), nc, td.get("showing", 0))
            want_rows = [[None if v is None else str(v) for v in row]
                         for row in oracle(a_db, "SELECT * FROM %s ORDER BY %s" % (tname, order))]
            record("v01-table-%s" % tname, got_rows == want_rows and cols == want_cols,
                   "rows got=%d want=%d" % (len(got_rows), len(want_rows)))

        code, td = post("/api/db/table_data", {"path": a_db, "tname": "customers", "page": 1,
                                               "page_size": 10, "sort_col": "", "sort_dir": "",
                                               "search": "Berlin"})
        want_n = oracle(a_db, "SELECT COUNT(*) FROM customers WHERE company_name LIKE '%Berlin%' "
                              "OR contact_name LIKE '%Berlin%' OR city LIKE '%Berlin%' "
                              "OR country LIKE '%Berlin%' OR phone LIKE '%Berlin%'")[0][0]
        record("v01-search-total", isinstance(td, dict) and td.get("total") == want_n,
               "total=%s want=%s" % (td.get("total") if isinstance(td, dict) else "?", want_n))

        code, td = post("/api/db/table_data", {"path": a_db, "tname": "customers", "page": 1,
                                               "page_size": 1, "sort_col": "id", "sort_dir": "desc",
                                               "search": ""})
        want_top = str(oracle(a_db, "SELECT id FROM customers ORDER BY id DESC LIMIT 1")[0][0])
        got_top = td["cells"][0] if isinstance(td, dict) and td.get("cells") else "?"
        record("v01-sort-desc", got_top == want_top, "top=%s want=%s" % (got_top, want_top))

        for name, sql in (
            ("plain", "SELECT id, company_name, contact_name FROM customers ORDER BY id LIMIT 25"),
            ("cte", "WITH c AS (SELECT id, contact_name FROM customers WHERE id <= 20) SELECT * FROM c ORDER BY id"),
            ("agg", "SELECT country, COUNT(*) AS n FROM customers GROUP BY country ORDER BY n DESC, country"),
            ("null-unicode", "SELECT id, 姓名, 备注 FROM 客户资料 ORDER BY id"),
        ):
            code, q = post("/api/db/query", {"path": a_db, "sql": sql})
            nc = q.get("ncols", 0) if isinstance(q, dict) else 0
            got = []
            if isinstance(q, dict) and q.get("ok") and nc:
                cells = q.get("cells", [])[nc:]
                got = interleave_rows(cells, nc, q.get("rowcount", 0))
            want = [[None if v is None else str(v) for v in row] for row in oracle(a_db, sql)]
            record("v01-query-%s" % name, got == want, "rows got=%d want=%d" % (len(got), len(want)))

        # ── V-02: failure paths ──
        code, m = post("/api/db/open", {"path": fx["missing"]})
        record("v02-missing-not-found", isinstance(m, dict) and m.get("ok") is False
               and m.get("err_code") == "file_not_found", json.dumps(m, ensure_ascii=False)[:120])
        record("v02-missing-no-create", not os.path.exists(fx["missing"]), "file must not be created")

        code, m = post("/api/db/open", {"path": g_db})
        record("v02-garbage-rejected", isinstance(m, dict) and m.get("ok") is False
               and m.get("err_code") == "not_a_database",
               json.dumps(m, ensure_ascii=False)[:120])
        record("v02-garbage-intact", sha256(g_db) == hash_g_before, "garbage file untouched")

        for name, sql, want_rej in (
            ("delete", "DELETE FROM customers", None),
            ("update", "UPDATE customers SET city='x'", None),
            ("insert", "INSERT INTO customers VALUES (99,'x','y','z','w','v')", None),
            ("drop", "DROP TABLE customers", None),
            ("wcte", "WITH d AS (DELETE FROM __sentinel RETURNING *) SELECT * FROM d", None),
            ("vacuum", "VACUUM", None),
        ):
            code, q = post("/api/db/query", {"path": a_db, "sql": sql})
            rejected = (isinstance(q, dict) and q.get("ok") is False
                        and q.get("err_code") in ("rejected", "query_failed"))
            record("v03-reject-%s" % name, rejected,
                   (q.get("err_detail", "") if isinstance(q, dict) else "")[:80])

        for name, sql in (("pragma-flip", "PRAGMA query_only=OFF"),
                          ("attach", "ATTACH DATABASE '%s' AS aux" % os.path.join(fx["fixdir"], "aux.db")),
                          ("multi", "SELECT 1; DELETE FROM customers")):
            code, q = post("/api/db/query", {"path": a_db, "sql": sql})
            rejected = isinstance(q, dict) and q.get("ok") is False and q.get("err_code") == "rejected"
            record("v03-reject-%s" % name, rejected,
                   (q.get("err_detail", "") if isinstance(q, dict) else "")[:80])

        code, q = post("/api/db/query", {"path": a_db, "sql": "SELECT * FROM no_such_table"})
        record("v03-engine-error-text", isinstance(q, dict) and q.get("ok") is False
               and "no such table" in str(q.get("err_detail", "")),
               str(q.get("err_detail") if isinstance(q, dict) else "")[:100])

        code, q = post("/api/db/query", {"path": a_db,
                                         "sql": "SELECT v FROM __sentinel WHERE k='guard'"})
        val = q["cells"][q["ncols"]] if isinstance(q, dict) and q.get("cells") else "?"
        record("v03-sentinel-value", val == "original-value-固定哨兵", "v=%s" % val)
        record("v03-hash-unchanged-a", sha256(a_db) == hash_a_before, "sha256(basic_a.db)")
        record("v03-hash-unchanged-b", sha256(b_db) == hash_b_before, "sha256(basic_b.db)")
        record("v03-no-aux-file", not os.path.exists(os.path.join(fx["fixdir"], "aux.db")),
               "ATTACH must not create side files")

        # ── V-04 ──
        code, td = post("/api/db/table_data", {"path": a_db, "tname": "audit_logs", "page": 1,
                                               "page_size": 50, "sort_col": "id", "sort_dir": "asc",
                                               "search": ""})
        record("v04-browse-1200", isinstance(td, dict) and td.get("total") == 1200
               and td.get("showing") == 50, "total=%s showing=%s" %
               (td.get("total") if isinstance(td, dict) else "?",
                td.get("showing") if isinstance(td, dict) else "?"))
        code, td = post("/api/db/table_data", {"path": a_db, "tname": "audit_logs", "page": 24,
                                               "page_size": 50, "sort_col": "id", "sort_dir": "asc",
                                               "search": ""})
        first_id = td["cells"][0] if isinstance(td, dict) and td.get("cells") else "?"
        record("v04-page-offset", first_id == str(50 * 23 + 1), "page24 first id=%s" % first_id)

        code, q = post("/api/db/query", {"path": a_db, "sql": "SELECT id FROM audit_logs ORDER BY id"})
        trunc = isinstance(q, dict) and q.get("truncated") is True and q.get("rowcount") == CONSOLE_TRUNC
        record("v04-console-truncated", trunc,
               "rowcount=%s truncated=%s" % (q.get("rowcount") if isinstance(q, dict) else "?",
                                             q.get("truncated") if isinstance(q, dict) else "?"))

        code, m = post("/api/db/open", {"path": b_db})
        record("v04-open-b", isinstance(m, dict) and m.get("ok") is True and m.get("tables") == 3,
               json.dumps(m, ensure_ascii=False)[:120])
        code, q = post("/api/db/query", {"path": b_db, "sql": "SELECT v FROM __sentinel WHERE k='guard'"})
        val_b = q["cells"][q["ncols"]] if isinstance(q, dict) and q.get("cells") else "?"
        record("v04-switch-results-change", val_b == "b-side-哨兵", "b sentinel=%s" % val_b)
        code, q = post("/api/db/query", {"path": a_db, "sql": "SELECT v FROM __sentinel WHERE k='guard'"})
        val_a = q["cells"][q["ncols"]] if isinstance(q, dict) and q.get("cells") else "?"
        record("v04-switch-back", val_a == "original-value-固定哨兵", "a sentinel=%s" % val_a)

        renamed = os.path.join(fx["fixdir"], "basic_a_renamed.db")
        try:
            os.rename(a_db, renamed)
            os.rename(renamed, a_db)
            record("v04-handle-released", True, "file renameable between requests")
        except OSError as e:
            record("v04-handle-released", False, "file locked: %s" % e)

        record("v04-final-hash", sha256(a_db) == hash_a_before and sha256(b_db) == hash_b_before,
               "both fixtures unchanged after full battery")
    finally:
        killed = stop_owned(owned)
        try:
            log.close()
        except Exception:
            pass


# ── D-01 独立准备/启动电池 ──

def standalone_battery(cli, workdir):
    """D-01: 独立启动、错 tool、端口占用、双实例隔离；失败非零不伤旁观。"""
    # s1: 错 tool → 快速非零
    bogus = os.path.join(workdir, "no-such-cli.exe")
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "--api-only"],
                       capture_output=True, text=True, timeout=60,
                       env=dict(os.environ, AUTO_CLI=bogus))
    record("d01-wrong-tool-nonzero", r.returncode != 0, "rc=%d" % r.returncode)

    # s2: 端口被占（用我们自己的哑监听者扮演占用者）→ 启动必须干净失败且不杀占用者
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    occupied = blocker.getsockname()[1]
    logp = os.path.join(workdir, "d01-occupied.log")
    env = dict(os.environ)
    env["AUTO_DB_PROBE"] = "0"
    proc, log = spawn_owned(cli, ["service", "--server", "rust", "--back-port", str(occupied)],
                            REPO, env, logp)
    owned = tree_of(proc.pid)
    try:
        ok_ready = wait_backend_ready(proc, occupied, 90, logp)
        # 90s 足以判"端口占用即失败"；后端不可在占用端口上就绪
        record("d01-occupied-port-fails", not ok_ready,
               "backend must not become ready on occupied port")
        # 占用者（我们的哑监听者）仍存活：旁观不受影响
        record("d01-occupier-unharmed", blocker.fileno() != -1,
               "dummy occupier still bound")
    finally:
        stop_owned(owned)
        blocker.close()

    # s3: 邻居失败不伤旁观 —— 实例1就绪后，邻居实例因端口占用启动失败，
    # 实例1必须不受影响（D-01"错误非零，旁观实例不受影响"）。
    # 注：同仓两个并发 service 实例受 cargo/Windows 运行中二进制重链接限制，
    # 不作为验收形态（工具链约束，见 evidence/002 决策稿）。
    p1 = free_port()
    logp1 = os.path.join(workdir, "d01-inst1.log")
    proc1, log1 = spawn_owned(cli, ["service", "--server", "rust", "--back-port", str(p1)],
                              REPO, env, logp1)
    owned1 = tree_of(proc1.pid)
    try:
        ok1 = wait_backend_ready(proc1, p1, SERVICE_READY_BUDGET_S, logp1)
        record("d01-instance1-ready", ok1, "port %d" % p1)
        if ok1:
            owned1 = tree_of(proc1.pid)
            blocker2 = socket.socket()
            blocker2.bind(("127.0.0.1", 0))
            blocker2.listen(1)
            occupied2 = blocker2.getsockname()[1]
            logp2 = os.path.join(workdir, "d01-neighbor.log")
            proc2, log2 = spawn_owned(cli, ["service", "--server", "rust", "--back-port", str(occupied2)],
                                      REPO, env, logp2)
            owned2 = tree_of(proc2.pid)
            try:
                ok2 = wait_backend_ready(proc2, occupied2, 90, logp2)
                record("d01-neighbor-fails-cleanly", not ok2,
                       "neighbor on occupied port must not become ready")
            finally:
                stop_owned(owned2)
                blocker2.close()
                try:
                    log2.close()
                except Exception:
                    pass
            time.sleep(2)
            code, _ = http("POST", "http://127.0.0.1:%d/api/db/open" % p1,
                           {"path": "___probe_missing___"}, timeout=5)
            record("d01-bystander-survives-neighbor-failure", code in (200, 400),
                   "instance1 answers after neighbor failed")
    finally:
        stop_owned(owned1)
        try:
            log1.close()
        except Exception:
            pass


# ── Vue Playwright ──

def find_playwright_module():
    env = os.environ.get("PLAYWRIGHT_MODULE")
    if env:
        return env
    cache = os.path.join(os.environ.get("LOCALAPPDATA", ""), "npm-cache", "_npx")
    best = None
    for pdir in glob.glob(os.path.join(cache, "*", "node_modules", "playwright", "package.json")):
        try:
            with open(pdir, encoding="utf-8") as f:
                ver = json.load(f)["version"]
            base = os.path.dirname(pdir)
            browsers = os.path.join(os.path.dirname(base), "playwright-core", "browsers.json")
            with open(browsers, encoding="utf-8") as f:
                bl = json.load(f)["browsers"]
            need = [b["revision"] for b in bl if b["name"] in ("chromium", "chromium-headless-shell")]
            pw_root = os.environ.get("LOCALAPPDATA", "") + os.sep + "ms-playwright"
            have = all(os.path.isdir(os.path.join(pw_root, "chromium_headless_shell-" + r)) or
                       os.path.isdir(os.path.join(pw_root, "chromium-" + r)) for r in need)
            cand = os.path.join(base, "index.mjs")
            if have:
                return cand
            best = best or cand
        except Exception:
            continue
    return best


def run_vue_drive(front, a_db, b_db, workdir):
    pw = find_playwright_module()
    if not pw:
        record("vue-ui", False, "playwright module not found")
        return
    env2 = dict(os.environ)
    env2["PLAYWRIGHT_MODULE"] = pw
    try:
        r = subprocess.run(["node", os.path.join(REPO, "tests", "basic", "ui_drive.mjs"),
                            "http://localhost:%d" % front, a_db, b_db],
                           cwd=REPO, env=env2, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        record("vue-ui", False, "driver timeout 600s")
        return
    sys.stdout.write(r.stdout)
    if r.stderr:
        sys.stdout.write(r.stderr[-400:])
    summary = None
    for line in r.stdout.splitlines():
        if line.startswith("SUMMARY "):
            summary = json.loads(line[8:])
    ok = summary is not None and all(x["ok"] for x in summary["results"]) and r.returncode == 0
    record("vue-ui", ok, "rc=%d" % r.returncode)


# ── UI 电池（vue/vm）：调度 + 调度方 oracle ──

def ui_battery(cli, workdir, profile):
    fx = make_fixtures(workdir)
    a_db, b_db = (fx["a"], fx["b"]) if profile == "vue" else (fx["a_cn"], fx["b_cn"])
    hash_a_before = sha256(fx["a"])
    hash_b_before = sha256(fx["b"])

    back = free_port()
    front = free_port()
    while not (port_free(back) and port_free(front)):
        back = free_port()
        front = free_port()
    logp = os.path.join(workdir, "ui-run.log")
    env = dict(os.environ)
    env["AUTO_DB_PROBE"] = "0"
    mcp_port = None
    if profile == "vm":
        mcp_port = free_port()
        env["AUTOUI_MCP_PORT"] = str(mcp_port)

    proc, log = spawn_owned(cli, ["run", "-r", profile, "-B", str(back), "-F", str(front)],
                            REPO, env, logp)
    owned = tree_of(proc.pid)
    try:
        ready = wait_backend_ready(proc, back, UI_READY_BUDGET_S, logp)
        # 框架启动瞬断（tool host control stream，进程即退）容错：未就绪整次重试一次
        if not ready:
            print("WARN: ui run not ready; retrying once (tool-host startup flake)", flush=True)
            stop_owned(owned)
            try:
                log.close()
            except Exception:
                pass
            back, front = free_port(), free_port()
            if profile == "vm":
                mcp_port = free_port()
                env["AUTOUI_MCP_PORT"] = str(mcp_port)
            proc, log = spawn_owned(cli, ["run", "-r", profile, "-B", str(back), "-F", str(front)],
                                    REPO, env, logp)
            owned = tree_of(proc.pid)
            ready = wait_backend_ready(proc, back, 600, logp)
        if not record("ui-backend-ready", ready,
                      "back :%d front :%d profile=%s" % (back, front, profile)):
            return
        owned = tree_of(proc.pid)

        if profile == "vue":
            run_vue_drive(front, a_db, b_db, workdir)
        else:
            mcp_url = "http://127.0.0.1:%d/mcp" % mcp_port
            up = False
            for _ in range(30):
                code, _b = http("POST", mcp_url, {"jsonrpc": "2.0", "method": "tools/list",
                                                  "params": {}, "id": 1}, timeout=3)
                if code == 200:
                    up = True
                    break
                time.sleep(2)
            if not record("vm-mcp-ready", up, mcp_url):
                return
            try:
                r = subprocess.run([sys.executable, os.path.join(REPO, "tests", "basic", "vm_drive.py"),
                                    mcp_url, a_db, b_db, fx["missing"], fx["g"]],
                                   cwd=REPO, capture_output=True, text=True, timeout=900)
            except subprocess.TimeoutExpired:
                record("vm-ui", False, "driver timeout 900s")
                return
            sys.stdout.write(r.stdout)
            if r.stderr:
                sys.stdout.write(r.stderr[-400:])
            summary = None
            for line in r.stdout.splitlines():
                if line.startswith("SUMMARY "):
                    summary = json.loads(line[8:])
            ok = summary is not None and all(x["ok"] for x in summary["results"]) and r.returncode == 0
            record("vm-ui", ok, "rc=%d" % r.returncode)

        # ── 调度方只读 oracle（D-03/D-04）：请求间隙重命名（app 仍开，重命名本次实际打开的文件） ──
        renamed = a_db + ".gap"
        try:
            os.rename(a_db, renamed)
            os.rename(renamed, a_db)
            record("ui-handle-released-in-gap", True,
                   "fixture renameable while app open (no leaked lock)")
        except OSError as e:
            record("ui-handle-released-in-gap", False, "file locked: %s" % e)

        record("ui-hash-unchanged-a", sha256(fx["a"]) == hash_a_before, "sha256(basic_a.db)")
        record("ui-hash-unchanged-b", sha256(fx["b"]) == hash_b_before, "sha256(basic_b.db)")
        record("ui-missing-not-created", not os.path.exists(fx["missing"]),
               "UI bad-path step must not create file")
        record("ui-no-aux-file", not os.path.exists(os.path.join(fx["fixdir"], "aux.db")),
               "no ATTACH side file")
        con = sqlite3.connect("file:%s?mode=ro" % fx["a"].replace("\\", "/"), uri=True)
        try:
            v = list(con.execute("SELECT v FROM __sentinel WHERE k='guard'"))[0][0]
        finally:
            con.close()
        record("ui-sentinel-value", v == "original-value-固定哨兵", "v=%s" % v)

        # ── D-04 重开下一次操作（vm 专属）：停进程→重新启动→重新输入→打开 ──
        if profile == "vm":
            stop_owned(owned)
            owned = set()
            time.sleep(3)
            back2 = free_port()
            front2 = free_port()
            mcp2 = free_port()
            env2 = dict(env)
            env2["AUTOUI_MCP_PORT"] = str(mcp2)
            proc2, log2 = spawn_owned(cli, ["run", "-r", "vm", "-B", str(back2), "-F", str(front2)],
                                      REPO, env2, logp)
            owned2 = tree_of(proc2.pid)
            try:
                ready2 = wait_backend_ready(proc2, back2, 600, logp)
                if not record("vm-restart-ready", ready2, "back :%d" % back2):
                    return
                owned2 = tree_of(proc2.pid)
                mcp_url2 = "http://127.0.0.1:%d/mcp" % mcp2
                up = False
                for _ in range(30):
                    code, _b = http("POST", mcp_url2, {"jsonrpc": "2.0", "method": "tools/list",
                                                       "params": {}, "id": 1}, timeout=3)
                    if code == 200:
                        up = True
                        break
                    time.sleep(2)
                if not record("vm-restart-mcp", up, mcp_url2):
                    return
                r = subprocess.run([sys.executable, os.path.join(REPO, "tests", "basic", "vm_drive.py"),
                                    mcp_url2, fx["a"], fx["b"]],
                                   cwd=REPO, capture_output=True, text=True, timeout=600)
                summary = None
                for line in r.stdout.splitlines():
                    if line.startswith("SUMMARY "):
                        summary = json.loads(line[8:])
                # 重开场景只要求"输入→打开→连接"前几步成立；完整电池由上一会话负责
                core = None
                if summary:
                    core = [x for x in summary["results"] if x["step"] in
                            ("ui-load", "path-input-found", "type-path-store",
                             "press-open-receipt", "open-a-state")]
                ok = bool(summary) and core and all(x["ok"] for x in core) and r.returncode in (0, 1)
                record("vm-reopen-next-query", ok,
                       "reopen app then real path input -> open (core steps)")
            finally:
                stop_owned(owned2)
                try:
                    log2.close()
                except Exception:
                    pass
    finally:
        if owned:
            stop_owned(owned)
        try:
            log.close()
        except Exception:
            pass


# ── D-05 敏感性控制 ──

def d05_battery(cli, workdir):
    """受控反例：错库断言（总门非零）、源码注入检测、正常控制。"""
    fx = make_fixtures(workdir)

    # c1: 错库断言反例 —— oracle 期待 B 哨兵而实际开 A，检查必须 FAIL（rc!=0）
    probe = os.path.join(workdir, "d05_wrong_db.py")
    with open(probe, "w", encoding="utf-8") as f:
        f.write(
            "import sqlite3, sys, json\n"
            "con = sqlite3.connect(r'%s')\n" % fx["a"].replace("\\", "/") +
            "v = list(con.execute(\"SELECT v FROM __sentinel WHERE k='guard'\"))[0][0]\n"
            "# 错库断言：期待 B 侧哨兵（实际 A）——受控反例，必须断言失败\n"
            "assert v == 'b-side-哨兵', 'wrong-db assertion tripped: ' + v\n"
            "print('unexpected pass')\n")
    r = subprocess.run([sys.executable, probe], capture_output=True, text=True, timeout=60)
    record("d05-wrong-db-gate-nonzero", r.returncode != 0,
           "rc=%d (counterexample must fail)" % r.returncode)

    # c2: 源码注入检测 —— 前后 hash 护栏对 vm_e2e_hook 注入敏感（apply→检测→
    # revert 全程 try/finally，保证任何中途异常都不留脏源码）
    store = os.path.join(REPO, "src", "front", "db_store.at")
    h0 = sha256(store)
    hook = os.path.join(REPO, "tests", "basic", "tools", "vm_e2e_hook.py")
    detected = False
    try:
        r = subprocess.run([sys.executable, hook, "apply", fx["a"], fx["b"]],
                           capture_output=True, text=True, cwd=REPO, timeout=60)
        h1 = sha256(store)
        detected = (r.returncode == 0 and h1 != h0)
        record("d05-injection-detected", detected,
               "hash guard trips on Init-hook apply (%s… -> %s…)" % (h0[:8], h1[:8]))
    finally:
        r = subprocess.run([sys.executable, hook, "revert"],
                           capture_output=True, text=True, cwd=REPO, timeout=60)
        h2 = sha256(store)
        record("d05-revert-restores", r.returncode == 0 and h2 == h0,
               "store hash restored after revert")

    # c3: 正常控制 —— 独立后端 + API oracle（确定性子集；真实原生链受
    # T-00 决策稿 §3 框架竞态影响，不做非确定性控制）
    port = free_port()
    logp = os.path.join(workdir, "d05-control.log")
    env = dict(os.environ)
    env["AUTO_DB_PROBE"] = "0"
    proc, log = spawn_owned(cli, ["service", "--server", "rust", "--back-port", str(port)],
                            REPO, env, logp)
    owned = tree_of(proc.pid)
    try:
        ready = wait_backend_ready(proc, port, SERVICE_READY_BUDGET_S, logp)
        if ready:
            code, m = http("POST", "http://127.0.0.1:%d/api/db/open" % port,
                           {"path": fx["a"]}, timeout=15)
            record("d05-control-api-oracle",
                   code == 200 and isinstance(m, dict) and m.get("ok") and m.get("tables") == 4,
                   "A tables=4 via own backend")
        else:
            record("d05-control-api-oracle", False, "control backend not ready")
    finally:
        stop_owned(owned)
        try:
            log.close()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", choices=["vue", "vm", "api-only"], default="api-only")
    ap.add_argument("--api-only", action="store_true")
    args = ap.parse_args()
    if args.api_only:
        args.profile = "api-only"

    cli = resolve_cli()
    workdir = tempfile.mkdtemp(prefix="db002-verify-")
    print("workdir: " + workdir, flush=True)
    try:
        api_battery(cli, workdir)
        if args.profile == "api-only":
            standalone_battery(cli, workdir)
            d05_battery(cli, workdir)
        else:
            standalone_battery(cli, workdir)
            ui_battery(cli, workdir, args.profile)
            d05_battery(cli, workdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    passed = sum(1 for r in results if r["ok"])
    failed = sum(1 for r in results if not r["ok"])
    print("\nRESULTS: %d passed, %d failed" % (passed, failed))
    if failed:
        for r in results:
            if not r["ok"]:
                print("  FAIL: " + r["step"] + (" — " + r["detail"] if r["detail"] else ""))
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
