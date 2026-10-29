#!/usr/bin/env python3
"""VM E2E hook tool for DATABASE-001.

The VM frontend store cannot read process env (`use auto.env` is unavailable in
the interpreter's store context, G-7 in capability-decision), and MCP event
injection (autoui_type/autoui_action) is unreliable on loaded machines. This
tool temporarily rewrites the store's `.Init` handler into a deterministic
end-to-end driver (open -> query -> write-rejection -> switch -> switch-back)
against two explicit fixture paths, so the chain can be verified by simply
launching `auto run -r vm` and reading the `vmE2E` state field via MCP.

Usage:
    python tests/basic/tools/vm_e2e_hook.py apply <db_a_path> <db_b_path>
    python tests/basic/tools/vm_e2e_hook.py revert

`apply` fails if the hook is already present. `revert` restores the plain
`.Init -> { }` handler and removes the `vmE2E` field. The tool is idempotent
per direction and never touches anything else. Local-only mutation: apply
right before a VM verification run, revert before committing.
"""

import sys

STORE = r"src/front/db_store.at"

PLAIN_INIT = "    on {\n        .Init -> { }\n"

HOOK_HEAD = '''    on {
        .Init -> {
            .path_input = "{db_a}"
            .OpenDb()
            .vmE2E = "open:" + .file_name + "/" + f"${.table_count}"
            .SetSql("SELECT id, contact_name FROM customers WHERE id <= 3")
            .RunSql()
            .vmE2E = .vmE2E + " q:" + .sqlStatus + "/" + .sqlMeta
            .SetSql("DELETE FROM customers")
            .RunSql()
            .vmE2E = .vmE2E + " rej:" + .sqlStatus
            .path_input = "{db_b}"
            .OpenDb()
            .vmE2E = .vmE2E + " b:" + .file_name + "/" + f"${.table_count}"
            .path_input = "{db_a}"
            .OpenDb()
            .vmE2E = .vmE2E + " back:" + .file_name + " " + .showingText
        }'''

FIELD = '''
        // —— VM 端到端自驱钩子字段（由 tests/basic/tools/vm_e2e_hook.py 临时
        // 注入；常规运行恒为 ""，不影响任何 UI 行为）——
        var vmE2E str = ""'''


def apply(db_a, db_b):
    s = open(STORE, encoding="utf-8").read()
    if "vmE2E" in s:
        print("FAIL: hook already applied")
        return 1
    if PLAIN_INIT not in s:
        print("FAIL: plain .Init anchor not found (store shape changed?)")
        return 1
    hook = HOOK_HEAD.replace("{db_a}", db_a.replace("\\", "/")).replace("{db_b}", db_b.replace("\\", "/"))
    s = s.replace(PLAIN_INIT, hook, 1)
    anchor = '''        var qColNames []str = []
        var qVals List = []      // List<{ vals: List<str> }>
    }'''
    assert anchor in s
    s = s.replace(anchor, '''        var qColNames []str = []
        var qVals List = []      // List<{ vals: List<str> }>
''' + FIELD + '''
    }''', 1)
    b0 = s.count("{") - s.count("}")
    if b0 != 0:
        print("FAIL: brace imbalance after apply:", b0)
        return 1
    open(STORE, "w", encoding="utf-8", newline="\n").write(s)
    print("hook applied for", db_a, "<->", db_b)
    return 0


def revert():
    s = open(STORE, encoding="utf-8").read()
    if "vmE2E" not in s:
        print("hook not present")
        return 0
    i = s.index("    on {\n        .Init -> {")
    j = s.index("        .PathInput(v) -> {")
    s = s[:i] + PLAIN_INIT + "\n" + s[j:]
    s = s.replace(FIELD + "\n", "")
    s = s.replace(FIELD, "")
    b0 = s.count("{") - s.count("}")
    if b0 != 0:
        print("FAIL: brace imbalance after revert:", b0)
        return 1
    open(STORE, "w", encoding="utf-8", newline="\n").write(s)
    print("hook reverted")
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "apply" and len(sys.argv) == 4:
        sys.exit(apply(sys.argv[2], sys.argv[3]))
    if len(sys.argv) >= 2 and sys.argv[1] == "revert":
        sys.exit(revert())
    print(__doc__)
    sys.exit(2)
