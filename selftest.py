"""Developer sanity test: every solution must pass, every blank/broken template must fail.
Not needed for normal use. Run: python selftest.py"""
import sys

import cfnutil as U
import core
import snippets
from challenges import CHALLENGES, build

fails = 0
for ch in CHALLENGES:
    student, solution, hints = build(ch)
    sol = core.grade(solution, ch, full=True)
    stu = core.grade(student, ch, full=False)
    L = sol["lint"] or {"errors": "?", "warnings": "?", "items": []}
    good, bad = sol["passed"], not stu["passed"]
    print("%-20s solution:%s student-fails:%s  lint E%s W%s  moto=%s  bonus=%s" % (
        ch["id"], "PASS" if good else "FAIL", "yes" if bad else "NO!", L["errors"], L["warnings"],
        (sol["moto"] or {}).get("status"), sol["bonus"]["got"] if sol["bonus"] else None))
    if not good:
        fails += 1
        for it in L["items"][:6]:
            print("     lint", it)
        for r in sol["reqs"]:
            if not r["ok"]:
                print("     req FAIL:", r["desc"], r["msg"])
    if sol["moto"] and sol["moto"]["status"] != "CREATE_COMPLETE":
        print("     moto:", sol["moto"])
    if not bad:
        fails += 1
for k, (_, body) in snippets.SNIPPETS.items():
    try:
        U.load(body)
    except Exception as e:  # noqa: BLE001
        print("snippet %s does not parse: %s" % (k, e))
        fails += 1
print("\nFAILURES:", fails)
sys.exit(1 if fails else 0)
