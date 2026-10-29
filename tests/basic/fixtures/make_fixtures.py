#!/usr/bin/env python3
"""Deterministic SQLite fixtures for DATABASE-001 verification.

Generates REAL sqlite files used by capability probes (T-01) and the
verify_basic battery (T-05). Run with an explicit --out directory; never
touches user data.

    python tests/basic/fixtures/make_fixtures.py --out <dir>

Files produced:
    basic_a.db   customers / 客户资料 / audit_logs(1200) / view / indexes /
                 __sentinel row ("guard" -> "original-value-固定哨兵")
    basic_b.db   different shape (products / warehouses) for switch tests
    garbage.db   plain bytes, not a database
Journal mode stays default (delete) so a quiet fixture has no side files and
its sha256 is a stable read-only oracle.
"""

import argparse
import os
import sqlite3

AUDIT_ROWS = 1200


def make_basic_a(path):
    db = sqlite3.connect(path)
    c = db.cursor()
    c.execute("CREATE TABLE customers ("
              " id INTEGER PRIMARY KEY,"
              " company_name TEXT NOT NULL,"
              " contact_name TEXT,"
              " city TEXT,"
              " country TEXT,"
              " phone TEXT)")
    rows = [
        (1, "Alfreds Futterkiste", "Maria Anders", "Berlin", "Germany", "030-0074321"),
        (2, "Ana Trujillo Emparedados", "Ana Trujillo", "México D.F.", "Mexico", "(5) 555-4729"),
        (3, "Antonio Moreno Taquería", None, "México D.F.", "Mexico", None),
        (4, "Around the Horn", "Thomas Hardy", None, "UK", "(171) 555-7788"),
        (5, "Berglunds snabbköp", "Christina Berglund", "Luleå", "Sweden", "0921-12 34 65"),
        (6, "Blauer See Delikatessen", "Hanna Moos", "Mannheim", "Germany", None),
        (7, "Blondel père et fils", "Frédérique Citeaux", "Strasbourg", "France", "88.60.15.31"),
        (8, "中文公司 “引号”", "张三", "北京", "中国", "010-12345678"),
        (9, "Bon app'", "Laurence Lebihan", "Marseille", "France", "91.24.45.40"),
        (10, "Bottom-Dollar Markets", "Elizabeth Lincoln", "Tsawwassen", "Canada", "(604) 555-4729"),
        (11, "B's Beverages", "Victoria Ashworth", "London", "UK", "(171) 555-1212"),
        (12, "Cactus Comidas para llevar", None, "Buenos Aires", "Argentina", "(1) 135-5555"),
        (13, "Centro comercial Moctezuma", "Francisco Chang", "México D.F.", None, "(5) 555-3392"),
        (14, "Chop-suey Chinese", "Yang Wang", "Bern", "Switzerland", "0452-076545"),
        (15, "Comércio Mineiro", "Pedro Afonso", "Sao Paulo", "Brazil", "(11) 555-7647"),
        (16, "肉・新鲜食材", "田中太郎", "東京", "日本", None),
        (17, "Handle'd Row", "Quote'Step", None, None, None),
        (18, "Percent%Row", "Like_Col", "Oslo", "Norway", "47-0000"),
        (19, "多行\n文本行", "tab\t制表", "首尔", "韩国", "82-0000"),
        (20, "Emoji 🎯 Row", None, None, None, None),
    ]
    c.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?)", rows)

    c.execute("CREATE TABLE 客户资料 ("
              " id INTEGER PRIMARY KEY,"
              " 姓名 TEXT NOT NULL,"
              " 备注 TEXT)")
    c.executemany("INSERT INTO 客户资料 VALUES (?,?,?)", [
        (1, "张三", "老客户"),
        (2, "李四", None),
        (3, "Richard 王混排", "vip 'quoted'"),
        (4, "王五", "多行\n备注"),
        (5, "赵六", None),
    ])

    c.execute("CREATE TABLE audit_logs ("
              " id INTEGER PRIMARY KEY,"
              " ts TEXT NOT NULL,"
              " action TEXT NOT NULL,"
              " actor TEXT,"
              " ip TEXT)")
    c.executemany("INSERT INTO audit_logs VALUES (?,?,?,?,?)",
                  [(i, "2026-01-01 00:%02d:%02d" % (i // 60 % 60, i % 60),
                    ("EVT-%03d" % (i % 50)) if i % 97 else "IN%LITERAL",
                    ("user-%d" % (i % 7)) if i % 5 else None,
                    "10.0.0.%d" % (i % 256)) for i in range(1, AUDIT_ROWS + 1)])

    c.execute("CREATE VIEW country_summary AS"
              " SELECT country, COUNT(*) AS n FROM customers"
              " WHERE country IS NOT NULL GROUP BY country")
    c.execute("CREATE INDEX idx_customers_country ON customers(country)")
    c.execute("CREATE INDEX idx_audit_actor ON audit_logs(actor)")

    c.execute("CREATE TABLE __sentinel (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
    c.execute("INSERT INTO __sentinel VALUES ('guard', 'original-value-固定哨兵')")
    db.commit()
    db.close()


def make_basic_b(path):
    db = sqlite3.connect(path)
    c = db.cursor()
    c.execute("CREATE TABLE products ("
              " id INTEGER PRIMARY KEY,"
              " sku TEXT NOT NULL,"
              " price REAL NOT NULL,"
              " stock INTEGER)")
    c.executemany("INSERT INTO products VALUES (?,?,?,?)", [
        (1, "SKU-A1", 18.5, 39),
        (2, "SKU-B2", 19.0, None),
        (3, "SKU-C3", 10.25, 13),
        (4, "SKU-D4 中文", 99.99, 0),
        (5, "SKU-E5", 21.35, 53),
    ])
    c.execute("CREATE TABLE warehouses ("
              " id INTEGER PRIMARY KEY, city TEXT, code TEXT)")
    c.executemany("INSERT INTO warehouses VALUES (?,?,?)", [
        (1, "Berlin", "BER"), (2, "北京", "PEK"), (3, "Luleå", "LLA"),
    ])
    c.execute("CREATE TABLE __sentinel (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
    c.execute("INSERT INTO __sentinel VALUES ('guard', 'b-side-哨兵')")
    db.commit()
    db.close()


def make_garbage(path):
    with open(path, "wb") as f:
        f.write(b"this is definitely not a sqlite database header at all" * 8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    a = os.path.join(args.out, "basic_a.db")
    b = os.path.join(args.out, "basic_b.db")
    g = os.path.join(args.out, "garbage.db")
    for p in (a, b, g):
        if os.path.exists(p):
            os.remove(p)
        side = p + "-wal"
        if os.path.exists(side):
            os.remove(side)
        side = p + "-shm"
        if os.path.exists(side):
            os.remove(side)
    make_basic_a(a)
    make_basic_b(b)
    make_garbage(g)
    print("fixtures written to " + args.out)


if __name__ == "__main__":
    main()
