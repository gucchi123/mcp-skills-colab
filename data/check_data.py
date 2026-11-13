# -*- coding: utf-8 -*-
"""data/ の正解 (gold) が、規程・チェックリスト・購買規程に書いた規則と食い違っていないかを確かめる。

make_data.py とは別に、規則を書かれた文書 (policy.md など) の言葉どおりに実装し直し、出来上がったファイルだけを読んで照合する。
1 件でも食い違えば AssertionError で止まる。

usage: python check_data.py
"""
import csv, datetime as dt, json, os, re, sys

if hasattr(sys.stdout, "reconfigure"):   # Jupyter の出力先には無い
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
P = lambda *a: os.path.join(HERE, *a)
load = lambda *a: json.load(open(P(*a), encoding="utf-8"))
loadl = lambda *a: [json.loads(l) for l in open(P(*a), encoding="utf-8") if l.strip()]
rcsv = lambda *a: list(csv.DictReader(open(P(*a), encoding="utf-8")))
n_checks = 0


def ok(cond, msg):
    global n_checks
    n_checks += 1
    assert cond, msg


# ---------------------------------------------------------------- 1. 経費精算 (policy.md 第1〜7条)
pol = open(P("expense", "policy.md"), encoding="utf-8").read()
for s in ["翌月10日", "30,000円", "12,000円", "15,000円", "1,500円", "10,000円", "100,000円未満", "3,000円以上", "IC 履歴",
          "5万円以下", "50万円以下", "300万円以下", "一般 ＜ 課長 ＜ 副部長 ＜ 部長 ＜ 本部長 ＜ 代表取締役社長"]:
    ok(s in pol, f"policy.md に「{s}」が無い")
claims = load("expense", "claims.json")
ok(len(claims) >= 40, "経費の件数")
ok(len({c["id"] for c in claims}) == len(claims), "経費の ID が重複")
ORDER = ["一般", "課長", "副部長", "部長", "本部長", "代表取締役社長"]
HOL = {"2026-09-21", "2026-09-22", "2026-09-23"}


def judge(c):
    ed, sd = dt.date.fromisoformat(c["expense_date"]), dt.date.fromisoformat(c["submitted"])
    a, cat, pos = c["amount"], c["category"], c["position"]
    r, f = [], []
    if cat == "宿泊費" and a / c["nights"] > (15000 if ORDER.index(pos) >= 3 else 12000):
        r.append("宿泊")
    if cat == "会議費" and a / c["attendees"] > 1500:
        r.append("会議")
    if cat == "接待交際費":
        if not c["pre_approval"]:
            r.append("事前申請")
        if a / c["attendees"] > 10000:
            r.append("接待上限")
    if cat == "書籍費" and a > 10000:
        r.append("書籍")
    if cat == "消耗品費" and a >= 100000:
        r.append("固定資産")
    if a >= 3000 and not c["receipt"] and not (cat == "交通費" and c["ic_record"]):
        r.append("領収書")
    if any(o is not c and (o["employee"], o["vendor"], o["expense_date"]) == (c["employee"], c["vendor"], c["expense_date"])
           for o in claims):
        r.append("分割")
    if cat == "交通費" and a > 30000:
        f.append("交通上限")
    nm = dt.date(ed.year + (ed.month == 12), ed.month % 12 + 1, 10)
    if sd > nm:
        f.append("期限")
    if cat in ("会議費", "接待交際費", "消耗品費") and (ed.weekday() >= 5 or ed.isoformat() in HOL):
        f.append("休日")
    if r:
        return "reject", len(r), None
    if f:
        return "needs_finance", len(f), None
    if a <= 10000:
        return "auto_approve", 0, None
    man = a / 10000
    lv = "課長" if man <= 5 else "部長" if man <= 50 else "本部長" if man <= 300 else "代表取締役社長"
    if ORDER.index(lv) <= ORDER.index(pos):
        lv = next(x for x in ORDER[ORDER.index(pos) + 1:] if x != "副部長")
    return "needs_manager", 0, lv


for c in claims:
    d, nr, ap = judge(c)
    g = c["gold"]
    ok(d == g["decision"], f"{c['id']}: 判定 {d} / gold {g['decision']}")
    ok(nr == len(g["reasons"]), f"{c['id']}: 事由の数 {nr} / gold {g['reasons']}")
    ok(ap == g["approver"], f"{c['id']}: 承認者 {ap} / gold {g['approver']}")
dec = {c["gold"]["decision"] for c in claims}
ok(dec == {"auto_approve", "needs_manager", "needs_finance", "reject"}, "四つの判定がすべて出ていない")

# ---------------------------------------------------------------- 2. 問い合わせ (faq.md の規則 1〜5)
faq = open(P("inquiry", "faq.md"), encoding="utf-8").read()
faq_ids = set(re.findall(r"^## (FAQ-\d+)", faq, re.M))
inqs = loadl("inquiry", "inquiries.jsonl")
ok(len(inqs) >= 60 and len({q["id"] for q in inqs}) == len(inqs), "問い合わせの件数・ID")
for q in inqs:
    g, t = q["gold"], q["text"]
    ok(g["category"] in {"使い方", "不具合", "請求", "返品", "苦情"}, f"{q['id']}: 区分")
    ok(g["faq_id"] is None or g["faq_id"] in faq_ids, f"{q['id']}: FAQ が無い {g['faq_id']}")
    if g["category"] == "苦情":
        want = (True, "高")
    elif g["category"] == "不具合" and any(w in t for w in ["発熱", "煙", "焦げ", "異臭", "膨らん"]):
        want = (True, "緊急")
    elif g["category"] == "請求" and any(w in t for w in ["二重", "金額が違", "返金"]):
        want = (True, "高")
    else:
        want = (g["faq_id"] is None, "通常")
    ok((g["human_required"], g["priority"]) == want, f"{q['id']}: {t} → {want} / gold {g}")
    if g["category"] == "返品" and g["faq_id"]:  # 規則 5: 30 日以内かつ未開封だけ
        m1, m2 = re.search(r"(\d+) 日目", t), re.search(r"(\d+) 週間前", t)
        days = int(m1.group(1)) if m1 else int(m2.group(1)) * 7
        ok(days <= 30 and ("未開封" in t or "開けていない" in t), f"{q['id']}: 返品の条件")
    if g["category"] == "返品" and not g["faq_id"]:
        ok("か月" in t or "開封して" in t, f"{q['id']}: 返品を人に回す理由が文面に無い")

# ---------------------------------------------------------------- 3. 契約書 (checklist.md R1〜R7)
gold = load("contract", "gold_findings.json")
ok(len(gold) == 8, "契約の本数")
for cid, g in gold.items():
    t = open(P("contract", f"{cid}.md"), encoding="utf-8").read()
    f = {}
    m = re.search(r"期間満了の(\d+)日前", t)
    if "更新され" in t and m and int(m.group(1)) >= 90:
        f["R1"] = "中"
    if re.search(r"甲は、本契約に関して乙に生じた損害の一切を賠償する", t):
        f["R2"] = "高"
    m = re.search(r"乙が甲に対して負う損害賠償の額は、本契約に基づく月額料金の([\d.]+)か月分", t)
    if m is None or float(m.group(1)) <= 1:
        f["R3"] = "中"
    if "その裁量により" in t:
        f["R4"] = "高"
    elif "通知することにより" in t:
        f["R4"] = "中"
    if not re.search(r"本契約は日本法に準拠する", t):
        f["R5"] = "高"
    if "東京地方裁判所を第一審" not in t:
        f["R6"] = "低"
    if "秘密保持" not in t:
        f["R7"] = "中"
    got = {x["rule"]: x["level"] for x in g["findings"]}
    ok(f == got, f"{cid}: 本文から {f} / gold {got}")
    lv = set(f.values())
    ov = "法務室レビュー必須" if "高" in lv else "部長確認" if "中" in lv else "担当者確認" if "低" in lv else "問題なし"
    ok(ov == g["overall"], f"{cid}: 総合 {ov} / gold {g['overall']}")
ok({g["overall"] for g in gold.values()} == {"法務室レビュー必須", "部長確認", "担当者確認", "問題なし"}, "総合の四段がそろっていない")

# ---------------------------------------------------------------- 4. 発注・在庫 (purchase_policy.md 第1〜4条)
inv = {r["sku"]: r for r in rcsv("inventory", "inventory.csv")}
sup = {r["supplier_id"]: r for r in rcsv("inventory", "suppliers.csv")}
ok(len(inv) == 30, "品目数")
for r in inv.values():
    ok(r["supplier_id"] in sup and (not r["alt_supplier_id"] or r["alt_supplier_id"] in sup), f"{r['sku']}: 発注先が無い")
    ok(int(r["lead_time_days"]) == int(sup[r["supplier_id"]]["lead_time_days"]), f"{r['sku']}: リードタイム")
for req in load("inventory", "requests.json"):
    for p in req["gold"]["plans"]:
        r = inv[p["sku"]]
        stock, rop, lot, mx, price = (int(r[k]) for k in ("stock", "reorder_point", "lot_size", "max_stock", "unit_price"))
        if stock > rop:
            ok(p["action"] == "no_order", f"{req['id']}: 発注点より上なのに {p['action']}")
            continue
        s_ok = sup[r["supplier_id"]]["status"] == "取引中"
        a_ok = bool(r["alt_supplier_id"]) and sup[r["alt_supplier_id"]]["status"] == "取引中"
        if not s_ok and not a_ok:
            ok(p["action"] == "escalate", f"{req['id']}: 発注先が無いのに {p['action']}")
            continue
        ok(p["action"] == "order", f"{req['id']}: 発注すべき")
        ok(p["supplier"] == (r["supplier_id"] if s_ok else r["alt_supplier_id"]), f"{req['id']}: 発注先")
        ok(p["qty"] % lot == 0 and p["qty"] >= lot, f"{req['id']}: ロットの倍数でない")
        ok(stock + p["qty"] <= mx or p["qty"] == lot, f"{req['id']}: 最大在庫を超える")
        ok(stock + p["qty"] + lot > mx or p["qty"] < (mx - stock) // lot * lot, f"{req['id']}: もっと発注できる")
        amt = p["qty"] * price
        ok(amt == p["amount"], f"{req['id']}: 金額")
        ap = None if amt <= 100000 else "製造部課長" if amt <= 500000 else "製造部長" if amt <= 3000000 else "事業本部長"
        ok(ap == p["approval"], f"{req['id']}: 承認 {ap} / gold {p['approval']}")
    ok(req["gold"]["needs_human_approval"] == any(p.get("approval") for p in req["gold"]["plans"]), f"{req['id']}: 承認の要否")
acts = {p["action"] for q in load("inventory", "requests.json") for p in q["gold"]["plans"]}
ok(acts == {"order", "no_order", "escalate"}, "三つの動きがそろっていない")

# ---------------------------------------------------------------- 5. 月次レポート (CSV から数え直す)
sales = rcsv("report", "sales.csv")
inqm = rcsv("report", "inquiries_monthly.csv")
invm = rcsv("report", "inventory_monthly.csv")
rg = load("report", "gold_numbers.json")
months = sorted({r["month"] for r in sales})
ok(len(months) == 6, "6 か月ない")
rev = lambda m, p=None: sum(int(r["revenue"]) for r in sales if r["month"] == m and (p is None or r["product"] == p))
for r in sales:
    ok(int(r["units"]) * int(r["unit_price"]) == int(r["revenue"]), "売上 = 数量 × 単価")
prods = sorted({r["product"] for r in sales})
for i, m in enumerate(months[1:], 1):
    pm, g = months[i - 1], rg[m]
    ok(g["revenue_total"] == rev(m), f"{m}: 売上合計")
    ok(abs(g["revenue_mom_pct"] - round((rev(m) / rev(pm) - 1) * 100, 1)) < 1e-9, f"{m}: 前月比")
    ok(g["top_product"] == max(prods, key=lambda p: rev(m, p)), f"{m}: 最大の製品")
    gr = {p: rev(m, p) / rev(pm, p) - 1 for p in prods}
    ok(g["fastest_growth_product"] == max(gr, key=gr.get) and g["weakest_mom_product"] == min(gr, key=gr.get), f"{m}: 伸び")
    ic = {r["category"]: int(r["count"]) for r in inqm if r["month"] == m}
    ok(g["inquiries_total"] == sum(ic.values()) and g["complaints"] == ic["苦情"], f"{m}: 問い合わせ")
    ok(g["top_inquiry_category"] == max(ic, key=ic.get), f"{m}: 最多の区分")
    low = sorted(r["sku"] for r in invm if r["month"] == m and int(r["end_stock"]) <= int(r["reorder_point"]))
    ok(g["low_stock_skus"] == low, f"{m}: 在庫")
for s in [r["sku"] for r in invm if r["month"] == "2026-09"]:  # 9 月末は inventory.csv の現在庫と同じ
    ok(next(int(r["end_stock"]) for r in invm if r["month"] == "2026-09" and r["sku"] == s) == int(inv[s]["stock"]), f"9月末 {s}")

# ---------------------------------------------------------------- 評価用の問い
by_claim = {c["id"]: c for c in claims}
by_inq = {q["id"]: q for q in inqs}
reqs = {r["id"]: r for r in load("inventory", "requests.json")}
for name in ["expense", "inquiry", "contract", "inventory", "report"]:
    qs = loadl("questions", f"{name}.jsonl")
    ok(len(qs) == 10, f"{name}: 問いが 10 問でない ({len(qs)})")
    ok(len({q["id"] for q in qs}) == 10, f"{name}: ID 重複")
    for q in qs:
        ok(q["expected_steps"] and isinstance(q["human_approval"], bool), f"{q['id']}: 手順・承認の欄")
        if name == "expense":
            ok(q["gold"] == by_claim[q["input"]["claim_id"]]["gold"], f"{q['id']}: 正解が元と違う")
        if name == "inquiry":
            ok(q["gold"] == by_inq[q["input"]["inquiry_id"]]["gold"], f"{q['id']}: 正解が元と違う")
        if name == "inventory":
            ok(q["gold"] == reqs[q["input"]["request_id"]]["gold"], f"{q['id']}: 正解が元と違う")
        if name == "contract" and q["input"].get("contract_id"):
            ok(q["gold"]["overall"] == gold[q["input"]["contract_id"]]["overall"], f"{q['id']}: 正解が元と違う")
rep = {q["id"]: q for q in loadl("questions", "report.jsonl")}
ok(rep["rep-01"]["gold"]["answer"] == rev("2026-09"), "rep-01")
ok(rep["rep-09"]["gold"]["answer"] == ["2026-08", rg["2026-08"]["weakest_mom_product"]], "rep-09")
spike = max(months[1:], key=lambda m: int(next(r["count"] for r in inqm if r["month"] == m and r["category"] == "不具合")))
ok(spike == "2026-08", "不具合が急に増えた月が 8 月でない")

# ---------------------------------------------------------------- 架空であること・実在の名前が無いこと
# 出してはいけない名前の一覧は、作った人の手元の .banned_names.txt (1 行 1 語・配布しない) から読む。無ければ飛ばす
_banned_file = os.path.join(HERE, ".banned_names.txt")
_banned = [w.strip() for w in open(_banned_file, encoding="utf-8")] if os.path.exists(_banned_file) else []
_banned = [w for w in _banned if w]
for root, _, files in os.walk(HERE):
    for fn in files:
        if _banned and fn.endswith((".md", ".json", ".jsonl", ".csv")):
            t = open(os.path.join(root, fn), encoding="utf-8").read()
            ok(not any(w.lower() in t.lower() for w in _banned), f"{fn}: 出してはいけない名前")
for d in ["expense/policy.md", "inquiry/faq.md", "contract/checklist.md", "inventory/purchase_policy.md", "report/template.md"]:
    ok("架空" in open(P(*d.split("/")), encoding="utf-8").read(), f"{d}: 架空の断りが無い")

print(f"✅ 照合 {n_checks} 件、食い違い 0")
