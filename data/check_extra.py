# -*- coding: utf-8 -*-
"""make_extra.py の出来上がりを、規程から別に書き直した規則で照合する (make_extra.py は import しない)。
usage: python check_extra.py
"""
import json, os, sys

if hasattr(sys.stdout, "reconfigure"):   # Jupyter の出力先には無い
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
J = lambda *p: json.load(open(os.path.join(HERE, *p), encoding="utf-8"))
cust, staff, gold = J("crm", "customers.json"), J("crm", "staff.json"), J("crm", "access_gold.json")

BASE = {"id", "type", "products"}
CONTACT3 = {"contact.name", "contact.phone", "contact.email"}
PERSONAL = {"name", "contact.name", "contact.phone", "contact.email", "contact.address"}
MGR = {"課長", "副部長", "部長"}


def rule(u, c):
    s = set(BASE)
    if c["type"] == "個人":                                   # 第4条
        return s | (PERSONAL if u["role"] == "desk" else set())
    s.add("name")                                             # 第3条1
    if u["department"] == "情報システム部":                    # 第5条
        return s
    is_mgr = u["department"] == "営業部" and u["role"] == "sales" and u["position"] in MGR
    if is_mgr or u["department"] == "経理部":                  # 第3条2
        s |= {"rank", "credit_limit_yen"}
    if is_mgr or c["sales_rep"] == u["id"]:                    # 第3条3
        s |= CONTACT3
    elif u["role"] == "desk":
        s |= {"contact.name", "contact.phone"}
    return s


bad = 0
for u in staff:
    for c in cust:
        if set(gold[u["id"]][c["id"]]) != rule(u, c):
            bad += 1
            print("🔴", u["id"], c["id"], sorted(set(gold[u["id"]][c["id"]]) ^ rule(u, c)))
# 架空の連絡先だけを使っているか
for c in cust:
    ph, em = c["contact"]["phone"], c["contact"]["email"]
    if not ph.startswith("03-0000-") or not em.endswith(".example"):
        bad += 1; print("🔴 架空でない連絡先の形", c["id"])
cat = J("questions", "tool_catalog.json")
names = {t for v in cat.values() for t in v}
for ln in open(os.path.join(HERE, "questions", "tool_selection.jsonl"), encoding="utf-8"):
    r = json.loads(ln)
    if any(t not in names for t in r["expected_tools"] + [t for t in r.get("also_ok", []) if t]):
        bad += 1; print("🔴 道具の名前", r["id"])
    if r.get("also_ok") and (not r.get("why") or r["first_tool"] in r["also_ok"]):
        bad += 1; print("🔴 別解の理由が無い・期待の道具と重なる", r["id"])
n = len(staff) * len(cust)
print(f"照合 {n} 組 / 不一致 {bad}")
sys.exit(1 if bad else 0)
