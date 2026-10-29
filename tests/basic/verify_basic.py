#!/usr/bin/env python3
"""DATABASE-001 basic-capabilities verification (Plan §6 V-01..V-04).

Reproducible entry (real app, real files, no in-memory helpers):
    python tests/basic/verify_basic.py --profile vue
    python tests/basic/verify_basic.py --profile vm
    python tests/basic/verify_basic.py --api-only

Batteries:
  api  — real rust backend service (`auto service --server rust`), isolated
         fixture dir (tests/basic/fixtures/make_fixtures.py); V-01 oracle
         comparison against independent Python sqlite3; V-02 failure paths;
         V-03 write-attempt negatives + sha256 unchanged; V-04 large result,
         switch db, handle-release (file renameable between requests).
  ui   — real frontend via `auto run -r <profile>`: vue → Playwright
         (tests/basic/ui_drive.mjs), vm → AutoUI MCP (tests/basic/vm_drive.py).

Exit code 0 = all checks passed. Evidence: stdout log (kept by caller under
docs/plans/attachments/, local-only).

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


def pid_on_port(port):
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-NetTCPConnection -LocalPort %d -State Listen -ErrorAction SilentlyContinue)"
         ".OwningProcess | Select-Object -First 1" % port],
        capture_output=True, text=True).stdout.strip()
    return int(out) if out.isdigit() else None


def kill_port(port):
    for _ in range(6):
        pid = pid_on_port(port)
        if pid is None:
            return
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        time.sleep(1.5)


def kill_stale(scope):
    """Kill leftover auto wrappers/backends whose command line references the
    given scope substring (scoped: other repos' processes untouched)."""
    ps = ("Get-CimInstance Win32_Process | "
          "Where-Object { ($_.Name -eq 'auto.exe' -or $_.Name -like 'auto-database*') "
          "-and $_.CommandLine -like '*%s*' } | ForEach-Object { $_.ProcessId }" % scope)
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                         capture_output=True, text=True).stdout.split()
    for pid in out:
        if pid.isdigit():
            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
    if out:
        time.sleep(2)


def resolve_cli():
    cli = os.environ.get("AUTO_CLI", DEFAULT_CLI)
    if not os.path.exists(cli):
        print("FATAL: auto CLI not found at " + cli + " (set AUTO_CLI)")
        sys.exit(2)
    return cli


def start_service(cli, port, log_path, extra_env=None, timeout_s=420, retries=3):
    """Start `auto service --server rust` and wait until /api/db/open answers.
    Retries survive machine contention (other builds share this box)."""
    env = dict(os.environ)
    env["AUTO_DB_PROBE"] = "0"
    if extra_env:
        env.update(extra_env)
    for attempt in range(1, retries + 1):
        log = open(log_path, "w", encoding="utf-8")
        proc = subprocess.Popen(
            [cli, "service", "--server", "rust", "--back-port", str(port)],
            cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT)
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            code, body = http("POST", "http://127.0.0.1:%d/api/db/open" % port,
                              {"path": "___probe_missing___"}, timeout=4)
            if code in (200, 400) and isinstance(body, dict) and "err_code" in body:
                return proc, log
            time.sleep(3)
        stop_service(proc, log, port)
        print("WARN: service not ready (attempt %d)" % attempt, flush=True)
    return None, None


def stop_service(proc, log, port):
    try:
        proc.terminate()
    except Exception:
        pass
    kill_port(port)
    try:
        log.close()
    except Exception:
        pass
    time.sleep(1)


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


def api_battery(cli, workdir):
    fixdir = os.path.join(workdir, "fix")
    subprocess.run([sys.executable, os.path.join(REPO, "tests", "basic", "fixtures",
                    "make_fixtures.py"), "--out", fixdir], check=True, capture_output=True)
    a_db = os.path.join(fixdir, "basic_a.db")
    b_db = os.path.join(fixdir, "basic_b.db")
    g_db = os.path.join(fixdir, "garbage.db")
    hash_a_before = sha256(a_db)
    hash_b_before = sha256(b_db)
    hash_g_before = sha256(g_db)

    port = free_port()
    logp = os.path.join(workdir, "api-service.log")
    proc, log = start_service(cli, port, logp)
    if proc is None:
        record("service-ready", False, "backend never became ready (see %s)" % logp)
        return
    base = "http://127.0.0.1:%d" % port

    def post(ep, body, timeout=20):
        return http("POST", base + ep, body, timeout=timeout)

    try:
        record("service-ready", True, "rust backend on :%d" % port)

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

        # objects vs oracle
        code, objs = post("/api/db/objects", {"path": a_db})
        want_objs = sorted((t, n) for t, n in oracle(
            a_db, "SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite\\_%' ESCAPE '\\'"))
        got_objs = sorted((o["otype"], o["name"]) for o in objs.get("objects", [])) if isinstance(objs, dict) else []
        record("v01-objects-vs-oracle", got_objs == want_objs,
               "got=%d want=%d" % (len(got_objs), len(want_objs)))

        # table_data vs oracle (values + NULL flags), Chinese table included
        for tname, order in (("customers", "id"), ("客户资料", "id")):
            code, td = post("/api/db/table_data", {"path": a_db, "tname": tname, "page": 1,
                                                   "page_size": 50, "sort_col": order,
                                                   "sort_dir": "asc", "search": ""})
            cols = [c["name"] for c in td.get("columns", [])] if isinstance(td, dict) else []
            want_cols = [r[1] for r in oracle(a_db, "PRAGMA table_info(%s)" % tname)]
            nc = len(cols)
            got_rows = []
            got_nulls = []
            if isinstance(td, dict) and td.get("ok") and nc:
                rows_n = td.get("showing", 0)
                for r in range(rows_n):
                    row = td["cells"][r * nc:(r + 1) * nc]
                    nl = td["nulls"][r * nc:(r + 1) * nc]
                    got_rows.append([None if nl[i] == 1 else row[i] for i in range(nc)])
                    got_nulls.append(nl)
            want_rows = [[None if v is None else str(v) for v in row]
                         for row in oracle(a_db, "SELECT * FROM %s ORDER BY %s" % (tname, order))]
            record("v01-table-%s" % tname, got_rows == want_rows and cols == want_cols,
                   "rows got=%d want=%d" % (len(got_rows), len(want_rows)))

        # search + total
        code, td = post("/api/db/table_data", {"path": a_db, "tname": "customers", "page": 1,
                                               "page_size": 10, "sort_col": "", "sort_dir": "",
                                               "search": "Berlin"})
        want_n = oracle(a_db, "SELECT COUNT(*) FROM customers WHERE company_name LIKE '%Berlin%' "
                              "OR contact_name LIKE '%Berlin%' OR city LIKE '%Berlin%' "
                              "OR country LIKE '%Berlin%' OR phone LIKE '%Berlin%'")[0][0]
        record("v01-search-total", isinstance(td, dict) and td.get("total") == want_n,
               "total=%s want=%s" % (td.get("total") if isinstance(td, dict) else "?", want_n))

        # sort desc first row vs oracle
        code, td = post("/api/db/table_data", {"path": a_db, "tname": "customers", "page": 1,
                                               "page_size": 1, "sort_col": "id", "sort_dir": "desc",
                                               "search": ""})
        want_top = str(oracle(a_db, "SELECT id FROM customers ORDER BY id DESC LIMIT 1")[0][0])
        got_top = td["cells"][0] if isinstance(td, dict) and td.get("cells") else "?"
        record("v01-sort-desc", got_top == want_top, "top=%s want=%s" % (got_top, want_top))

        # query vs oracle: plain / CTE / aggregate / NULL / Unicode
        for name, sql in (
            ("plain", "SELECT id, company_name, contact_name FROM customers ORDER BY id LIMIT 25"),
            ("cte", "WITH c AS (SELECT id, contact_name FROM customers WHERE id <= 20) SELECT * FROM c ORDER BY id"),
            ("agg", "SELECT country, COUNT(*) AS n FROM customers GROUP BY country ORDER BY n DESC, country"),
            ("null-unicode", "SELECT id, 姓名, 备注 FROM 客户资料 ORDER BY id"),
        ):
            code, q = post("/api/db/query", {"path": a_db, "sql": sql})
            nc = len(q.get("columns", [])) if isinstance(q, dict) else 0
            got = []
            if isinstance(q, dict) and q.get("ok") and nc:
                for r in range(q.get("rowcount", 0)):
                    row = q["cells"][r * nc:(r + 1) * nc]
                    nl = q["nulls"][r * nc:(r + 1) * nc]
                    got.append([None if nl[i] == 1 else row[i] for i in range(nc)])
            want = [[None if v is None else str(v) for v in row] for row in oracle(a_db, sql)]
            record("v01-query-%s" % name, got == want, "rows got=%d want=%d" % (len(got), len(want)))

        # ── V-02: failure paths ──
        missing = os.path.join(fixdir, "no_such.db")
        code, m = post("/api/db/open", {"path": missing})
        record("v02-missing-not-found", isinstance(m, dict) and m.get("ok") is False
               and m.get("err_code") == "file_not_found", json.dumps(m, ensure_ascii=False)[:120])
        record("v02-missing-no-create", not os.path.exists(missing), "file must not be created")

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
            # 拒绝可以是守卫(rejected)或引擎(query_failed, 如数据变更 CTE 语法拒绝)
            rejected = (isinstance(q, dict) and q.get("ok") is False
                        and q.get("err_code") in ("rejected", "query_failed"))
            record("v03-reject-%s" % name, rejected,
                   (q.get("err_detail", "") if isinstance(q, dict) else "")[:80])

        for name, sql in (("pragma-flip", "PRAGMA query_only=OFF"),
                          ("attach", "ATTACH DATABASE '%s' AS aux" % os.path.join(fixdir, "aux.db")),
                          ("multi", "SELECT 1; DELETE FROM customers")):
            code, q = post("/api/db/query", {"path": a_db, "sql": sql})
            rejected = isinstance(q, dict) and q.get("ok") is False and q.get("err_code") == "rejected"
            record("v03-reject-%s" % name, rejected,
                   (q.get("err_detail", "") if isinstance(q, dict) else "")[:80])

        code, q = post("/api/db/query", {"path": a_db, "sql": "SELECT * FROM no_such_table"})
        record("v03-engine-error-text", isinstance(q, dict) and q.get("ok") is False
               and "no such table" in str(q.get("err_detail", "")),
               str(q.get("err_detail") if isinstance(q, dict) else "")[:100])

        # sentinel value + file hashes unchanged (AC-03 oracle)
        code, q = post("/api/db/query", {"path": a_db,
                                         "sql": "SELECT v FROM __sentinel WHERE k='guard'"})
        val = q["cells"][0] if isinstance(q, dict) and q.get("cells") else "?"
        record("v03-sentinel-value", val == "original-value-固定哨兵", "v=%s" % val)
        record("v03-hash-unchanged-a", sha256(a_db) == hash_a_before, "sha256(basic_a.db)")
        record("v03-hash-unchanged-b", sha256(b_db) == hash_b_before, "sha256(basic_b.db)")
        record("v03-no-aux-file", not os.path.exists(os.path.join(fixdir, "aux.db")),
               "ATTACH must not create side files")

        # ── V-04: large result, truncation, switch, handle release ──
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

        # switch db: B has different shape; A again restores
        code, m = post("/api/db/open", {"path": b_db})
        record("v04-open-b", isinstance(m, dict) and m.get("ok") is True and m.get("tables") == 3,
               json.dumps(m, ensure_ascii=False)[:120])
        code, q = post("/api/db/query", {"path": b_db, "sql": "SELECT v FROM __sentinel WHERE k='guard'"})
        val_b = q["cells"][0] if isinstance(q, dict) and q.get("cells") else "?"
        record("v04-switch-results-change", val_b == "b-side-哨兵", "b sentinel=%s" % val_b)
        code, q = post("/api/db/query", {"path": a_db, "sql": "SELECT v FROM __sentinel WHERE k='guard'"})
        val_a = q["cells"][0] if isinstance(q, dict) and q.get("cells") else "?"
        record("v04-switch-back", val_a == "original-value-固定哨兵", "a sentinel=%s" % val_a)

        # handle release: no server-side persistent connection → file renameable
        renamed = os.path.join(fixdir, "basic_a_renamed.db")
        try:
            os.rename(a_db, renamed)
            os.rename(renamed, a_db)
            record("v04-handle-released", True, "file renameable between requests")
        except OSError as e:
            record("v04-handle-released", False, "file locked: %s" % e)

        record("v04-final-hash", sha256(a_db) == hash_a_before and sha256(b_db) == hash_b_before,
               "both fixtures unchanged after full battery")
    finally:
        stop_service(proc, log, port)


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


def ui_battery(cli, workdir, profile):
    fixdir = os.path.join(workdir, "fix")
    subprocess.run([sys.executable, os.path.join(REPO, "tests", "basic", "fixtures",
                    "make_fixtures.py"), "--out", fixdir], check=True, capture_output=True)
    a_db = os.path.join(fixdir, "basic_a.db")
    b_db = os.path.join(fixdir, "basic_b.db")

    back = free_port()
    front = free_port()
    logp = os.path.join(workdir, "ui-run.log")
    env = dict(os.environ)
    env["AUTO_DB_PROBE"] = "0"
    mcp_port = None
    if profile == "vm":
        mcp_port = free_port()
        env["AUTOUI_MCP_PORT"] = str(mcp_port)

    def spawn():
        log = open(logp, "a", encoding="utf-8")
        return subprocess.Popen(
            [cli, "run", "-r", profile, "-B", str(back), "-F", str(front)],
            cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT)

    kill_stale("auto-database")
    proc = spawn()
    ready = False
    for attempt in range(3):
        deadline = time.time() + 420
        while time.time() < deadline:
            code, body = http("POST", "http://127.0.0.1:%d/api/db/open" % back,
                              {"path": "___probe_missing___"}, timeout=4)
            if code in (200, 400) and isinstance(body, dict) and "err_code" in body:
                ready = True
                break
            if proc.poll() is not None:
                break
            time.sleep(3)
        if ready or proc.poll() is None and ready:
            break
        print("WARN: ui run not ready (attempt %d)" % (attempt + 1), flush=True)
        kill_port(back)
        kill_port(front)
        try:
            proc.terminate()
        except Exception:
            pass
        time.sleep(3)
        proc = spawn()
    if not record("ui-backend-ready", ready, "back :%d front :%d profile=%s" % (back, front, profile)):
        try:
            proc.terminate()
        except Exception:
            pass
        return

    try:
        if profile == "vue":
            pw = find_playwright_module()
            if not pw:
                record("vue-ui", False, "playwright module not found")
                return
            env2 = dict(os.environ)
            env2["PLAYWRIGHT_MODULE"] = pw
            r = subprocess.run(["node", os.path.join(REPO, "tests", "basic", "ui_drive.mjs"),
                                "http://localhost:%d" % front, a_db, b_db],
                               cwd=REPO, env=env2, capture_output=True, text=True, timeout=600)
            sys.stdout.write(r.stdout)
            if r.stderr:
                sys.stdout.write(r.stderr[-400:])
            summary = None
            for line in r.stdout.splitlines():
                if line.startswith("SUMMARY "):
                    summary = json.loads(line[8:])
            ok = summary is not None and all(x["ok"] for x in summary["results"]) and r.returncode == 0
            record("vue-ui", ok, "rc=%d" % r.returncode)
        else:
            mcp_url = "http://127.0.0.1:%d/mcp" % mcp_port
            up = False
            for _ in range(30):
                try:
                    rr = http("POST", mcp_url, {"jsonrpc": "2.0", "method": "tools/list",
                                                "params": {}, "id": 1}, timeout=3)
                    if rr[0] == 200:
                        up = True
                        break
                except Exception:
                    pass
                time.sleep(2)
            if not record("vm-mcp-ready", up, mcp_url):
                return
            r = subprocess.run([sys.executable, os.path.join(REPO, "tests", "basic", "vm_drive.py"),
                                mcp_url, a_db, b_db],
                               cwd=REPO, capture_output=True, text=True, timeout=600)
            sys.stdout.write(r.stdout)
            if r.stderr:
                sys.stdout.write(r.stderr[-400:])
            summary = None
            for line in r.stdout.splitlines():
                if line.startswith("SUMMARY "):
                    summary = json.loads(line[8:])
            ok = summary is not None and all(x["ok"] for x in summary["results"]) and r.returncode == 0
            record("vm-ui", ok, "rc=%d" % r.returncode)
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        kill_port(back)
        kill_port(front)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", choices=["vue", "vm", "api-only"], default="api-only")
    ap.add_argument("--api-only", action="store_true")
    args = ap.parse_args()
    if args.api_only:
        args.profile = "api-only"

    cli = resolve_cli()
    kill_stale("auto-database")
    workdir = tempfile.mkdtemp(prefix="db001-verify-")
    print("workdir: " + workdir, flush=True)
    try:
        api_battery(cli, workdir)
        if args.profile != "api-only":
            ui_battery(cli, workdir, args.profile)
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
