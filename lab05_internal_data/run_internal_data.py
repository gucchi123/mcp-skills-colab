"""ラボ 5: 社内データを安全に読む (資料と道具・利用者ごとの出し分け・監査ログ・キャッシュの目安・読むだけの数字)。

    python run_internal_data.py                                   # 5 つの場面を全部 (短い表示)
    python run_internal_data.py --only resources --show           # 資料 (resource) の一覧と中身を長めに
    python run_internal_data.py --only visibility --customer C-002,IND-001
    python run_internal_data.py --only visibility --all           # 9 人 × 21 社 = 189 組を規程の正解と照合
    python run_internal_data.py --only audit                      # 監査ログ (state/audit.jsonl) の行
    python run_internal_data.py --only cache,report --name teacher  # 結果を out/summary_teacher.json に残す

Claude は呼ばない (API キー不要)。サーバには MCP の Client で同じプロセスのまま直接つなぐ。
書き込み先 (SOLAHA_STATE_DIR) は実行ごとに一時フォルダを作る (キットの state/ を汚さない)。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import unicodedata

import anyio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from mcp import Client  # noqa: E402
from mcp.shared.exceptions import MCPError  # noqa: E402

from common.identity import set_user, staff  # noqa: E402
from common.kit import data_path, out_dir, read_json, read_jsonl, state_dir, write_json  # noqa: E402
from servers import crm, expense, inventory, kb, report  # noqa: E402

LAB = "lab05_internal_data"
SECTIONS = ["resources", "visibility", "audit", "cache", "report"]
SERVERS = {"crm": crm.mcp, "kb": kb.mcp, "inventory": inventory.mcp, "report": report.mcp, "expense": expense.mcp}
USERS = [f"U-0{i}" for i in range(1, 10)]
# 表の列: 規程の項目 (common/policy.py の名前) と画面の短い名前。法人と個人で項目が違う (個人にランク・与信枠は無い)
COLS = {"法人": [("name", "会社名"), ("rank", "ランク"), ("credit_limit_yen", "与信枠"), ("contact.name", "担当者"),
                ("contact.phone", "電話"), ("contact.email", "メール")],
        "個人": [("name", "氏名"), ("contact.name", "連絡先氏名"), ("contact.phone", "電話"),
                ("contact.email", "メール"), ("contact.address", "住所")]}


def _w(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WFA" else 1 for ch in s)


def _pad(s: str, n: int) -> str:
    """全角を 2 文字分と数えて右を埋める (表の列をそろえる)。"""
    return s + " " * max(1, n - _w(s))


def _quiet() -> None:
    # 道具・資料の失敗は同じプロセスのサーバのログにも出る (トレースバックが画面に混ざる)。結果で見せるので黙らせる
    logging.getLogger("mcp.server.mcpserver.server").setLevel(logging.CRITICAL)


def _audit_rows() -> list[dict]:
    p = os.path.join(state_dir(), "audit.jsonl")
    return read_jsonl(p) if os.path.exists(p) else []


def _label(uid: str) -> str:
    s = staff(uid)
    role = "窓口" if s["role"] == "desk" else s["department"][:2] + s["position"]
    return f"{uid} {s['name'].split()[0]}({role})"


# ------------------------------------------------------------------ 1. 資料 (resource) と道具 (tool)
async def sec_resources(a) -> dict:
    print("■ 1. 資料 (resource) と資料のひな形 (resource template)")
    out = {}
    for name in ("crm", "kb", "inventory", "report"):
        async with Client(SERVERS[name]) as c:
            res = (await c.list_resources()).resources
            tmpl = (await c.list_resource_templates()).resource_templates
            tools = (await c.list_tools()).tools
        out[name] = {"resources": [r.uri for r in res], "templates": [t.uri_template for t in tmpl],
                     "tools": [t.name for t in tools]}
        items = [f"{r.uri} ({r.title})" for r in res] + [f"{t.uri_template} ({t.title}・ひな形)" for t in tmpl]
        print(f"  {name:<9} 資料: {', '.join(items) or 'なし'}")
        print(f"  {'':<9} 道具: {', '.join(t.name for t in tools)}")

    before = len(_audit_rows())
    set_user("U-01")
    async with Client(crm.mcp) as c:
        r = await c.read_resource("crm://policy")
    body = r.contents[0]
    lines = body.text.splitlines()
    print(f"\n■ crm://policy を読む ({body.mime_type}・{len(lines)} 行)")
    for ln in (lines if a.show else [x for x in lines if x.startswith(("# ", "## 第3条", "3. "))]):
        print("  " + ln[:110])
    async with Client(kb.mcp) as c:
        r = await c.read_resource("kb://regulations/a-05")
        doc = r.contents[0].text.splitlines()
        print(f"\n■ kb://regulations/a-05 を読む (ひな形の {{doc_id}} に a-05 を入れた URI・{len(doc)} 行)")
        for ln in (doc if a.show else doc[:1] + [x for x in doc if x.startswith("## ")][:4]):
            print("  " + ln[:110])
        try:
            await c.read_resource("kb://regulations/zz")
            bad = "読めてしまった"
        except MCPError as e:
            bad = str(e)
        print(f"  無い番号 kb://regulations/zz → MCPError: {bad}")
        print("    (サーバの ToolError の文「文書 zz はありません」は、資料の読み出しでは利用者に届かない)")
    after = len(_audit_rows())
    print(f"\n  資料を 3 回読んだあとの監査ログの行: {before} → {after} (資料の読み出しはサーバが記録していない)")
    print("\n■ 使い分け")
    print("  資料: アプリや人が選んで文脈に入れる・URI で指す・だれが読んでも同じ中身 (規程・型・方針)")
    print("  道具: モデルが判断して呼ぶ・引数で探す/計算する・利用者で中身が変わる・監査が要る (顧客 1 件・数字)")
    print("  このキットの Host はモデルに道具だけを渡す。だから kb は同じ規程を道具 get_regulation でも出している")
    out.update(bad_uri_error=bad, audit_before=before, audit_after=after)
    return out


# ------------------------------------------------------------------ 2. 利用者ごとの出し分け
async def _view(uid: str, cid: str) -> dict:
    set_user(uid)                                   # 利用者はホスト (ここでは自分) が決める。モデルの引数ではない
    async with Client(crm.mcp) as c:
        return (await c.call_tool("get_customer", {"customer_id": cid})).structured_content


async def sec_visibility(a) -> dict:
    gold = read_json(data_path("crm", "access_gold.json"))
    custs = [c["id"] for c in read_json(data_path("crm", "customers.json"))]
    want = custs if a.all else a.customer.split(",")
    out, n_ok, n = {}, 0, 0
    for cid in want:
        views = {u: await _view(u, cid) for u in USERS}
        cols = COLS[views[USERS[0]]["type"]]
        out[cid] = {u: v["hidden"] for u, v in views.items()}
        for u, v in views.items():
            shown = {k for k, _ in cols} - set(v["hidden"])
            ok = shown == {k for k, _ in cols} & set(gold[u][cid])     # 正解は「見てよい項目」の一覧
            n_ok += ok; n += 1
        if a.all:
            continue
        v0 = views[USERS[0]]
        print(f"■ 2. get_customer {cid} ({v0['type']}・担当営業 {v0['sales_rep'] or 'なし'}) を 9 人の名前で呼ぶ  〇=見える －=（非表示）")
        cw = [max(_w(lab), 4) + 1 for _, lab in cols]
        print("  " + _pad("利用者", 22) + "".join(_pad(lab, w) for (_, lab), w in zip(cols, cw)) + "隠した数")
        for u, v in views.items():
            marks = "".join(_pad("－" if k in v["hidden"] else "〇", w) for (k, _), w in zip(cols, cw))
            print(f"  {_pad(_label(u), 22)}{marks}{len(v['hidden'])}")
        rep = views["U-01"]
        print(f"  例) U-01 に返った hidden: {rep['hidden']}")
        print(f"      U-01 に返った contact: {json.dumps(rep['contact'], ensure_ascii=False)}")
    print(f"→ 規程の正解 (data/crm/access_gold.json) と一致: {n_ok}/{n} 組")
    return {"hidden": out, "match": n_ok, "n": n}


# ------------------------------------------------------------------ 3. 監査ログ
async def sec_audit(a) -> dict:
    start = len(_audit_rows())
    calls = [("U-01", "get_customer", {"customer_id": "C-002"}), ("U-05", "get_customer", {"customer_id": "IND-001"}),
             ("U-09", "get_customer", {"customer_id": "C-002"}), ("U-02", "find_customer", {"query": "フーズ"})]
    for uid, tool, args in calls:
        set_user(uid)
        async with Client(crm.mcp) as c:
            await c.call_tool(tool, args)
    set_user(None)
    os.environ.pop("SOLAHA_USER", None)
    async with Client(crm.mcp) as c:
        r = await c.call_tool("get_customer", {"customer_id": "C-001"})      # 利用者が決まっていない呼び出し
    rows = _audit_rows()[start:]
    print(f"■ 3. 監査ログ {os.path.basename(state_dir())}/audit.jsonl に足された行 ({len(rows)} 行)")
    for e in rows:
        rest = {k: v for k, v in e.items() if k not in ("at", "server", "user", "tool")}
        print(f"  {e['at'][11:]} {e['user']} {e['server']}.{e['tool']} {json.dumps(rest, ensure_ascii=False)}")
    print(f"  利用者なしの呼び出し → is_error={r.is_error}: {r.content[0].text} (顧客を読む前に止まり、ログにも残らない)")
    print("  ログに残るのは「だれが・どの顧客を・どの項目を隠されたか」。値そのもの (メールなど) は書かない")
    return {"rows": rows, "no_user_error": r.content[0].text}


# ------------------------------------------------------------------ 4. キャッシュの目安
async def sec_cache(a) -> dict:
    print("■ 4. 一覧のキャッシュの目安 (結果に付く ttl_ms / cache_scope) と、読むだけの印")
    print(f"  {'サーバ':<10}{'tools/list':<20}{'resources/list':<20}読むだけの道具")
    out = {}
    for name, srv in SERVERS.items():
        async with Client(srv) as c:
            lt, lr = await c.list_tools(), await c.list_resources()
        ro = [t.name for t in lt.tools if t.annotations and t.annotations.read_only_hint]
        out[name] = {"tools_ttl_ms": lt.ttl_ms, "tools_scope": lt.cache_scope, "resources_ttl_ms": lr.ttl_ms,
                     "resources_scope": lr.cache_scope, "read_only": len(ro), "tools": len(lt.tools)}
        print(f"  {name:<10}{f'{lt.ttl_ms:,} {lt.cache_scope}':<20}{f'{lr.ttl_ms:,} {lr.cache_scope}':<20}"
              f"{len(ro)}/{len(lt.tools)}")
    print("  ttl_ms=300,000 は「5 分は一覧を取り直さなくてよい」。public は利用者をまたいで使い回してよい")
    print("  cache_hints を書かないサーバ (inventory・expense) は 0 private = 使い回さない (SDK の既定)")
    print("  読むだけの印 (read_only_hint) はヒント。守りは道具の中 (出し分け・確認) で行う")
    return out


# ------------------------------------------------------------------ 5. 読むだけの数字
async def sec_report(a) -> dict:
    gold = read_json(data_path("report", "gold_numbers.json"))
    months = sorted(gold) if a.all or not a.month else a.month.split(",")
    print("■ 5. report サーバの数字を正解 (data/report/gold_numbers.json) と照合")
    print(f"  {'月':<9}{'売上合計':>12}{'前月比':>8}  {'1位':<8}{'問合せ':>6}  {'在庫割れ':<20}照合")
    rows, ok_all = [], True
    async with Client(report.mcp) as c:
        for m in months:
            s = (await c.call_tool("get_monthly_sales", {"month": m})).structured_content
            q = (await c.call_tool("get_inquiry_counts", {"month": m})).structured_content
            inv = (await c.call_tool("get_inventory_snapshot", {"month": m})).structured_content["result"]
            low = sorted(r["sku"] for r in inv if r["below_reorder"])
            g = gold[m]
            ok = (s["total_yen"], s["total_change_pct"], s["top_product"], q["total"], low) == \
                 (g["revenue_total"], g["revenue_mom_pct"], g["top_product"], g["inquiries_total"], sorted(g["low_stock_skus"]))
            ok_all &= ok
            rows.append({"month": m, "total_yen": s["total_yen"], "mom_pct": s["total_change_pct"],
                         "top": s["top_product"], "inquiries": q["total"], "low_stock": low, "ok": ok})
            print(f"  {m:<9}{s['total_yen']:>12,}{s['total_change_pct']:>7}%  {s['top_product']:<8}{q['total']:>6}  "
                  f"{','.join(low):<24}{'✓' if ok else '✗'}")
        if a.show:
            s = (await c.call_tool("get_monthly_sales", {"month": months[-1], "product": "TL-200"})).structured_content
            print("  get_monthly_sales(TL-200) の構造化結果:", json.dumps(s, ensure_ascii=False))
        try:
            r = await c.call_tool("get_monthly_sales", {"month": "2025-01"})
            print(f"  無い月 2025-01 → is_error={r.is_error}: {r.content[0].text}")
        except MCPError as e:
            print("  無い月 2025-01 →", e)
    print(f"→ {sum(r['ok'] for r in rows)}/{len(rows)} か月が一致。足し算・前月比はサーバが計算して返す (モデルにさせない)")
    return {"rows": rows, "all_ok": ok_all}


RUN = {"resources": sec_resources, "visibility": sec_visibility, "audit": sec_audit, "cache": sec_cache,
       "report": sec_report}


async def amain(argv=None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="場面をカンマ区切り: " + ",".join(SECTIONS))
    ap.add_argument("--all", action="store_true", help="visibility は 21 社すべて、report は全月")
    ap.add_argument("--customer", default="C-002,IND-001", help="visibility で見る顧客 (カンマ区切り)")
    ap.add_argument("--month", help="report で見る月 (カンマ区切り。省くと全月)")
    ap.add_argument("--show", action="store_true", help="資料の全文などを長めに出す")
    ap.add_argument("--name", default="")
    a = ap.parse_args(argv)
    want = a.only.split(",") if a.only else SECTIONS
    bad = [w for w in want if w not in RUN]
    if bad:
        raise SystemExit(f"--only が不明です: {bad} (使える: {SECTIONS})")
    _quiet()
    prev_state, prev_user = os.environ.get("SOLAHA_STATE_DIR"), os.environ.pop("SOLAHA_USER", None)
    os.environ["SOLAHA_STATE_DIR"] = tempfile.mkdtemp(prefix="lab05_state_")
    result = {"state_dir": os.environ["SOLAHA_STATE_DIR"]}
    try:
        for i, w in enumerate(want):
            if i:
                print()
            result[w] = await RUN[w](a)
        result["audit_total"] = len(_audit_rows())
    finally:
        set_user(None)
        if prev_state is None:
            os.environ.pop("SOLAHA_STATE_DIR", None)
        else:
            os.environ["SOLAHA_STATE_DIR"] = prev_state
        if prev_user is not None:
            os.environ["SOLAHA_USER"] = prev_user
    if a.name:
        write_json(os.path.join(out_dir(LAB), f"summary_{a.name}.json"), {k: v for k, v in result.items() if k != "state_dir"})
    return result


def main(argv=None) -> dict:
    return anyio.run(amain, argv)


if __name__ == "__main__":
    from common.kit import utf8_console
    utf8_console()
    main()
