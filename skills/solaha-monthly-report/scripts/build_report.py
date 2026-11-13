"""report MCP サーバの返事 (JSON) 3 つから、月次レポートの 1〜3 節を作る。計算はすべてここで行う。

usage: python build_report.py sales.json inquiries.json inventory.json
  sales.json      get_monthly_sales の返事 (structured content)
  inquiries.json  get_inquiry_counts の返事
  inventory.json  get_inventory_snapshot の返事 ({"result": [...]} でも [...] でもよい)
数字が食い違っていれば 🔴 を出して止まる (終了コード 1)。
"""
import json
import sys


def pct(a, b):
    return None if not b else round((a - b) / b * 100, 1)


def build(sales: dict, inq: dict, inv) -> tuple[str, dict]:
    inv = inv["result"] if isinstance(inv, dict) else inv
    m = sales["month"]
    if inq["month"] != m:
        raise SystemExit(f"🔴 月が違う: 売上 {m} / 問い合わせ {inq['month']}")
    rows = sales["rows"]
    total = sum(r["revenue_yen"] for r in rows)
    if total != sales["total_yen"]:
        raise SystemExit(f"🔴 売上の合計が合わない: 行の和 {total} / 返事 {sales['total_yen']}")
    top = max(rows, key=lambda r: r["revenue_yen"])
    growth = [r for r in rows if r["change_pct"] is not None]
    fast = max(growth, key=lambda r: r["change_pct"]) if growth else None
    by = inq["by_category"]
    if sum(by.values()) != inq["total"]:
        raise SystemExit("🔴 問い合わせの合計が合わない")
    top_cat = max(by, key=by.get)
    low = sorted(r["sku"] for r in inv if r["end_stock"] <= r["reorder_point"])
    nums = {"revenue_total": total, "revenue_mom_pct": pct(total, sales["prev_total_yen"]),
            "top_product": top["product"], "top_product_revenue": top["revenue_yen"],
            "fastest_growth_product": fast["product"] if fast else None,
            "fastest_growth_pct": fast["change_pct"] if fast else None,
            "inquiries_total": inq["total"], "inquiries_mom_pct": pct(inq["total"], inq["prev_total"]),
            "top_inquiry_category": top_cat, "top_inquiry_count": by[top_cat], "complaints": by.get("苦情", 0),
            "low_stock_count": len(low), "low_stock_skus": low}
    f = lambda v: "—" if v is None else f"{v:+.1f}%"
    md = f"""# 月次レポート（{m}）ソラハ電機・架空

## 1. 売上
- 売上合計: {total:,} 円（前月比 {f(nums['revenue_mom_pct'])}）
- 最も大きい製品: {top['product']}（{top['revenue_yen']:,} 円）
- 前月から最も伸びた製品: {nums['fastest_growth_product'] or '—'}（{f(nums['fastest_growth_pct'])}）

## 2. 問い合わせ
- 件数の合計: {inq['total']:,} 件（前月比 {f(nums['inquiries_mom_pct'])}）
- 最も多い区分: {top_cat}（{by[top_cat]:,} 件）
- 苦情: {nums['complaints']:,} 件

## 3. 在庫
- 月末に発注点以下だった主要品目: {len(low)} 品目（{'、'.join(low) if low else 'なし'}）

## 4. 次の一手（人が書く）
"""
    return md, nums


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load = lambda p: json.load(open(p, encoding="utf-8"))
    md, _ = build(load(sys.argv[1]), load(sys.argv[2]), load(sys.argv[3]))
    print(md)
