"""ラボ 6: 書き込みの道具 (発注・経費の申請) を安全に動かす。確認・二重登録の防止・本人だけ・金額の承認・素の線。

    python run_saas_writes.py                                    # 場面を全部 (短い表示)
    python run_saas_writes.py --only schema,confirm              # モデルに見せる引数の形と、確認の文・承認/断る
    python run_saas_writes.py --only idem,self                   # 同じ request_id の 2 回目・他人の名前の申請
    python run_saas_writes.py --only gold --all                  # 購買の依頼 10 件を正解と照合 (既定は 4 件)
    python run_saas_writes.py --only wire --show                 # 確認 1 往復の素の JSON-RPC (stdio を書き写す)
    python run_saas_writes.py --only tasks,host                  # Tasks の有無を確かめる・mock のホストで確認を出す

Claude は呼ばない (API キー不要)。host の場面だけ mock (筋書きどおりの偽モデル) でホストを回す。
書き込み先 (SOLAHA_STATE_DIR) は実行ごとに一時フォルダを作る (キットの state/ を汚さない)。
"""
from __future__ import annotations

import argparse
import inspect
import json
import logging
import os
import subprocess
import sys
import tempfile

import anyio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp import Client, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

from common import llm as L  # noqa: E402
from common.host import Host, show  # noqa: E402
from common.identity import set_user, staff  # noqa: E402
from common.kit import ROOT, data_path, out_dir, read_json, read_jsonl, state_dir, write_json  # noqa: E402
from common.rules import po_approval  # noqa: E402
from saas_parts import Answer, Recorder, describe, order_plan, short  # noqa: E402
from servers import expense, inventory  # noqa: E402

LAB = "lab06_saas_writes"
HERE = os.path.dirname(os.path.abspath(__file__))
SECTIONS = ["schema", "confirm", "idem", "self", "gold", "wire", "tasks", "host"]
GOLD_SHORT = ["O-01", "O-04", "O-05", "O-08"]
TAXI = {"employee": "山根 翔太", "category": "交通費", "expense_date": "2026-10-20", "amount": 2400,
        "vendor": "東都タクシー", "description": "客先から駅まで", "receipt": True}
META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "lab06-raw", "version": "0"},
        "io.modelcontextprotocol/clientCapabilities": {}}


def _quiet() -> None:
    logging.getLogger("mcp.server.mcpserver.server").setLevel(logging.CRITICAL)


def _count(name: str) -> int:
    p = os.path.join(state_dir(), name)
    return len(read_jsonl(p)) if os.path.exists(p) else 0


def _err(r) -> str:
    return r.content[0].text if r.content else ""


# ------------------------------------------------------------------ 1. モデルに見せる引数の形
async def sec_schema(a) -> dict:
    print("■ 1. 書き込みの道具の引数: Python の関数 と モデルに見せる inputSchema")
    out = {}
    for srv, fn, tool in ((inventory.mcp, inventory.create_purchase_order, "create_purchase_order"),
                          (expense.mcp, expense.submit_expense, "submit_expense")):
        async with Client(srv) as c:
            t = next(t for t in (await c.list_tools()).tools if t.name == tool)
        params = list(inspect.signature(fn).parameters)
        props = list(t.input_schema["properties"])
        ann = t.annotations.model_dump(exclude_none=True)
        out[tool] = {"python": params, "schema": props, "required": t.input_schema.get("required", []),
                     "annotations": ann}
        print(f"  {tool}")
        print(f"    Python の引数 : {', '.join(params)}")
        print(f"    inputSchema   : {', '.join(props)}   (confirm が{'ある' if 'confirm' in props else '無い'})")
        print(f"    必須          : {', '.join(t.input_schema.get('required', []))}")
        print(f"    annotations   : {json.dumps(ann, ensure_ascii=False)}")
    print("  → confirm は Resolve(ask_confirm) で「人に聞いて埋める」引数。モデルは渡せない (自分で承認できない)")
    return out


# ------------------------------------------------------------------ 2. 確認の文と、承認・断る
async def sec_confirm(a) -> dict:
    set_user(a.user)
    print(f"■ 2. 確認 (elicitation) の文と答え方  利用者 {a.user} {staff(a.user)['name']}")
    out = {}
    cases = [("承認 (accept, ok=true)", Answer("accept")), ("断る (decline)", Answer("decline")),
             ("閉じた (cancel)", Answer("cancel")), ("承認だが ok=false", Answer("accept", ok=False))]
    print("  発注 P-102 (数量は省く = 購買規程どおり):")
    for k, (label, ans) in enumerate(cases, 1):
        before = _count("orders.jsonl")
        async with Client(inventory.mcp, elicitation_callback=ans) as c:
            r = await c.call_tool("create_purchase_order", {"sku": "P-102", "request_id": f"c-{k}"})
        if k == 1:
            print(f"    確認の文: 「{ans.seen[0]}」")
        res = (f"{r.structured_content['order_id']} {r.structured_content['status']}" if not r.is_error
               else f"is_error: {_err(r)}")
        print(f"    {label:<20} → {res}  / 登録 {before}→{_count('orders.jsonl')} 件")
        out[f"po_{ans.action}_{ans.ok}"] = {"is_error": r.is_error, "text": _err(r) if r.is_error else r.structured_content}
    print("  経費 (山根 翔太・交通費 2,400 円):")
    for k, (label, ans) in enumerate([("承認 (accept, ok=true)", Answer("accept")), ("断る (decline)", Answer("decline"))], 1):
        before = _count("expenses.jsonl")
        async with Client(expense.mcp, elicitation_callback=ans) as c:
            r = await c.call_tool("submit_expense", {**TAXI, "request_id": f"e-{k}"})
        if k == 1:
            print(f"    確認の文: 「{ans.seen[0]}」")
        res = (f"{r.structured_content['claim_id']} {r.structured_content['decision']}" if not r.is_error
               else f"is_error: {_err(r)}")
        print(f"    {label:<20} → {res}  / 登録 {before}→{_count('expenses.jsonl')} 件")
        out[f"exp_{ans.action}"] = {"is_error": r.is_error, "text": _err(r) if r.is_error else r.structured_content}
    try:
        async with Client(inventory.mcp) as c:        # 確認に答える仕組み (elicitation_callback) を持たないクライアント
            r = await c.call_tool("create_purchase_order", {"sku": "P-102", "request_id": "c-9"})
        msg = f"is_error={r.is_error}: {_err(r)[:100]}"
    except BaseException as e:                        # noqa: BLE001  道具の結果ではなく、要求そのものの失敗として届く
        while isinstance(e, BaseExceptionGroup):
            e = e.exceptions[0]
        msg = f"{type(e).__name__}: {e}"
    print(f"  答える仕組みの無いクライアント → {msg[:140]} / 登録 {_count('orders.jsonl')} 件")
    print("  → 断る・閉じたは道具の本体まで届かない (SDK が止める)。ok=false は本体が受け取って断る")
    p = os.path.join(state_dir(), "audit.jsonl")
    rows = read_jsonl(p) if os.path.exists(p) else []
    dec = [r for r in rows if r.get("declined")]
    asked = [r for r in rows if r.get("confirm_requested")]
    print(f"  監査ログの「取りやめ」の行: {len(dec)} 行 ({', '.join(r['request_id'] for r in dec)})"
          " = 本体まで届いた ok=false だけ")
    print(f"  監査ログの「確認を求めた」の行: {len(asked)} 行 ({', '.join(r['request_id'] for r in asked)})"
          " = 断る・閉じたの答えは残らないが、確認を求めたことは確認の関数 (ask_confirm) が残す")
    out["no_callback"] = msg
    out["declined_logged"] = [r["request_id"] for r in dec]
    out["confirm_requested_logged"] = [r["request_id"] for r in asked]
    return out


# ------------------------------------------------------------------ 3. 同じ request_id の 2 回目
async def sec_idem(a) -> dict:
    set_user(a.user)
    print("■ 3. 同じ request_id で 2 回呼ぶ (再試行・モデルの呼び直しを想定)")
    ans = Answer("accept")
    async with Client(inventory.mcp, elicitation_callback=ans) as c:
        r1 = (await c.call_tool("create_purchase_order", {"sku": "P-102", "request_id": "O-01"})).structured_content
        r2 = (await c.call_tool("create_purchase_order", {"sku": "P-102", "request_id": "O-01"})).structured_content
    print(f"  発注 1 回目: {r1['order_id']} duplicate={r1['duplicate']}  2 回目: {r2['order_id']} duplicate={r2['duplicate']}"
          f"  / 確認 {len(ans.seen)} 回・登録 {_count('orders.jsonl')} 件")
    ans2 = Answer("accept")
    async with Client(expense.mcp, elicitation_callback=ans2) as c:
        e1 = (await c.call_tool("submit_expense", {**TAXI, "request_id": "req-1"})).structured_content
        e2 = (await c.call_tool("submit_expense", {**TAXI, "request_id": "req-1"})).structured_content
        exp_asked, exp_n = len(ans2.seen), _count("expenses.jsonl")
        e3 = (await c.call_tool("submit_expense", {**TAXI, "request_id": "req-2"})).structured_content
    print(f"  経費 1 回目: {e1['claim_id']} duplicate={e1['duplicate']}  2 回目: {e2['claim_id']} duplicate={e2['duplicate']}"
          f"  / 確認 {exp_asked} 回・登録 {exp_n} 件")
    print(f"  経費 request_id を変えた 3 回目: {e3['claim_id']} {e3['decision']} 事由={e3['reasons']} (確認も出た)")
    print("  → 2 回目は確認も出さず前の結果を返す。request_id を変えると別の申請として扱う (同じ内容でも)")
    return {"po": [r1, r2], "po_asked": len(ans.seen), "exp": [e1, e2, e3], "exp_asked": exp_asked,
            "orders": _count("orders.jsonl"), "expenses": exp_n}


# ------------------------------------------------------------------ 4. 本人だけが申請できる
async def sec_self(a) -> dict:
    set_user(a.user)
    me = staff(a.user)["name"]
    other = "田村 浩二"
    print(f"■ 4. 経費は本人だけ  利用者 {a.user} {me} が「{other}」の名前で申請させられたら")
    ans = Answer("accept")
    async with Client(expense.mcp, elicitation_callback=ans) as c:
        r = await c.call_tool("submit_expense", {**TAXI, "employee": other, "request_id": "self-1"})
    print(f"  → is_error={r.is_error}: {_err(r)}")
    print(f"  登録 {_count('expenses.jsonl')} 件。確認は {len(ans.seen)} 回" + (f": 「{ans.seen[0]}」" if ans.seen else ""))
    print("  (Resolve の確認は道具の本体より先に走る。だから断る条件 (本人以外) は Resolve の中でも先に見て、人に聞かずに断る)")
    return {"is_error": r.is_error, "text": _err(r), "asked": len(ans.seen), "expenses": _count("expenses.jsonl")}


# ------------------------------------------------------------------ 5. 購買の依頼を正解と照合 (金額の承認)
async def sec_gold(a) -> dict:
    set_user(a.user)
    reqs = read_json(data_path("inventory", "requests.json"))
    if not a.all:
        reqs = [r for r in reqs if r["id"] in GOLD_SHORT]
    print("■ 5. 購買の依頼 (data/inventory/requests.json) を道具で処理し、正解と照合")
    print("  承認の線 (common.rules.po_approval): " +
          " / ".join(f"{x:,} 円→{po_approval(x) or '不要'}" for x in (100_000, 100_001, 500_001, 3_000_001)))
    print(f"  {'依頼':<6}{'品目':<7}{'数量':>7}{'発注先':>5}{'金額':>11}  {'状態':<6}{'承認':<8}確認 照合")
    rows, ok_n = [], 0
    for rq in reqs:
        for k, plan in enumerate(rq["gold"]["plans"]):
            ans = Answer("accept")
            async with Client(inventory.mcp, elicitation_callback=ans) as c:
                r = (await c.call_tool("create_purchase_order",
                                       {"sku": plan["sku"], "request_id": f"{rq['id']}-{k}"})).structured_content
            if plan["action"] == "order":
                ok = (r["qty"], r["supplier_id"], r["amount_yen"], r["approver"]) == \
                     (plan["qty"], plan["supplier"], plan["amount"], plan["approval"]) and \
                     r["status"] == ("承認待ち" if plan["approval"] else "発注済み")
            else:
                ok = r["status"] == "登録しない"
            ok_n += ok
            rows.append({"id": rq["id"], "sku": plan["sku"], "gold": plan["action"], "status": r["status"],
                         "qty": r["qty"], "amount_yen": r["amount_yen"], "approver": r["approver"],
                         "asked": len(ans.seen), "ok": ok, "note": r["note"]})
            print(f"  {rq['id']:<6}{plan['sku']:<7}{r['qty']:>7,}{r['supplier_id']:>5}{r['amount_yen']:>11,}  "
                  f"{r['status']:<6}{(r['approver'] or '-'):<8}{len(ans.seen):>2}   {'✓' if ok else '✗'}")
            if r["status"] == "登録しない":
                print(f"        理由: {r['note']}")
            if rq["gold"].get("asked_to_skip_approval"):
                print(f"        依頼文「{rq['request']}」→ それでも {r['status']} (承認はサーバが決める)")
    print(f"→ 正解と一致 {ok_n}/{len(rows)}・登録 {_count('orders.jsonl')} 件 (登録しない案は確認も出さない)")
    return {"rows": rows, "match": ok_n, "n": len(rows)}


# ------------------------------------------------------------------ 6. 素の線 (確認 1 往復)
async def sec_wire(a) -> dict:
    log = os.path.join(state_dir(), "wire.log")
    env = {**os.environ, "PYTHONUTF8": "1", "SOLAHA_USER": a.user}
    tee = os.path.join(HERE, "wire_tee.py")
    params = StdioServerParameters(command=sys.executable, args=[tee, log, sys.executable, "-m", "servers.inventory"],
                                   cwd=ROOT, env=env)
    ans = Answer("accept")
    print("■ 6. 確認 1 往復の素の線: SDK の Client ⇄ 書き写す中継 (wire_tee.py) ⇄ stdio のサーバ")
    with open(os.path.join(state_dir(), "stdio_inventory.log"), "a", encoding="utf-8") as err:
        async with Client(stdio_client(params, errlog=err), elicitation_callback=ans) as c:
            r = await c.call_tool("create_purchase_order", {"sku": "P-102", "request_id": "w-1"})
    lines = [ln.rstrip("\n") for ln in open(log, encoding="utf-8") if ln.strip()]
    msgs = [(ln[0], json.loads(ln[2:])) for ln in lines]
    for mark, m in msgs:
        print("  " + describe(mark, m).replace("\n", "\n  "))
        if a.show:
            print("    素: " + short(json.dumps(m, ensure_ascii=False), 400))
    ir = next(m for _, m in msgs if m.get("result", {}).get("resultType") == "input_required")
    again = next(m for _, m in msgs if "inputResponses" in (m.get("params") or {}))
    same_state = again["params"]["requestState"] == ir["result"]["requestState"]
    print(f"  → 結果: {r.structured_content['order_id']} {r.structured_content['status']}。"
          f"同じ tools/call を新しい id で送り直し、requestState は{'同じ' if same_state else '別'}")
    print("    最初の server/discover は握手ではなく問い合わせ (セッション ID は無い)。最後の tools/list は")
    print("    SDK が結果を outputSchema で確かめるために取りに行ったもの (まだ一覧を持っていなかったため)")
    methods = [m.get("method") or ("result" if "result" in m else "error") for _, m in msgs]
    return {"methods": methods, "same_request_state": same_state, "asked": ans.seen,
            "result": r.structured_content, "n_lines": len(lines)}


# ------------------------------------------------------------------ 7. Tasks (長い処理) は使えるか
def _raw_stdio(requests: list[dict]) -> list[dict]:
    """サーバを子プロセスで立て、JSON-RPC を 1 通書いては返事を 1 行読む (SDK を通さない素の確認)。
    まとめて書いてすぐ閉じると、サーバは入力の終わりで止まり、2 通目以降に返事をしない (確かめ済み)。"""
    env = {**os.environ, "PYTHONUTF8": "1", "SOLAHA_USER": "U-01"}
    p = subprocess.Popen([sys.executable, "-m", "servers.inventory"], cwd=ROOT, env=env, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    out = []
    try:
        for r in requests:
            p.stdin.write((json.dumps(r) + "\n").encode()); p.stdin.flush()
            out.append(json.loads(p.stdout.readline().decode("utf-8")))
    finally:
        p.stdin.close()
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            p.kill()
    return out


async def sec_tasks(a) -> dict:
    import mcp
    import mcp_types
    from mcp.server import MCPServer
    from mcp_types import _v2025_11_25 as v25, _v2026_07_28 as v26
    print("■ 7. Tasks (長い処理を後で受け取る仕組み) は mcp 2.3.0 で使えるか")
    old = [n for n in ("Task", "GetTaskRequest", "CreateTaskResult") if hasattr(v25, n)]
    new = [n for n in ("Task", "GetTaskRequest", "CreateTaskResult") if hasattr(v26, n)]
    print(f"  型: 2025-11-25 の型に {old or 'なし'} / 2026-07-28 の型に {new or 'なし'}")
    srv = [n for n in dir(MCPServer) if "task" in n.lower()]
    cli = [n for n in dir(Client) if "task" in n.lower()]
    print(f"  MCPServer・Client の task を含む名前: {srv or 'なし'} / {cli or 'なし'}")
    hits = []
    for base in (os.path.dirname(mcp.__file__), os.path.dirname(mcp_types.__file__)):
        for dp, _, fs in os.walk(base):
            for f in fs:
                if f.endswith(".py") and "io.modelcontextprotocol/tasks" in open(os.path.join(dp, f), encoding="utf-8").read():
                    hits.append(os.path.relpath(os.path.join(dp, f), os.path.dirname(base)).replace("\\", "/"))
    print(f"  拡張の名前 io.modelcontextprotocol/tasks が出てくるファイル: {hits} (説明文の例としてだけ)")
    replies = _raw_stdio([{"jsonrpc": "2.0", "id": 1, "method": "tasks/get", "params": {"taskId": "t-1", "_meta": META}},
                          {"jsonrpc": "2.0", "id": 2, "method": "tasks/list", "params": {"_meta": META}}])
    for m in replies:
        print("  " + describe("←", m))
    print("  → 2026-07-28 では Tasks は本体から外れて拡張になった。mcp 2.3.0 はその拡張を同梱しておらず、")
    print("    講座のサーバに送っても Method not found。長い処理は「受付番号を返す道具 + 状況を返す道具」で組む")
    return {"types_2025": old, "types_2026": new, "server_attrs": srv, "client_attrs": cli, "ext_files": hits,
            "replies": replies}


# ------------------------------------------------------------------ 8. mock のホストで確認を出す
async def sec_host(a) -> dict:
    q = "P-102 の在庫を確認して、必要なら補充してください。(依頼 O-01)"
    print("■ 8. ホストで発注係を動かす  🔴 モデルは mock (筋書きどおりに動く偽物。Claude は呼んでいない)")
    print(f"  質問: {q}")
    out = []
    for label, action in (("① 人が断る", "decline"), ("② 人が承認する", "accept"), ("③ 同じ依頼をもう一度 (承認役は承認)", "accept")):
        rec = Recorder(action)
        prov = L.MockProvider(order_plan)
        async with Host(["inventory"], user=a.user, provider=prov, approver=rec) as h:
            r = await h.run(q)
        print(f"  {label}  承認役が聞かれた回数 {len(rec.asked)}")
        show(r)
        out.append({"label": label, "asked": rec.asked, "text": r.text, "called": r.called()})
        if action == "decline":
            t = next(t for t in prov.requests[0]["tools"] if t["name"].endswith("create_purchase_order"))
            seen_props = list(t["input_schema"]["properties"])
    print(f"  モデルに渡した create_purchase_order の引数: {seen_props} (confirm は無い)")
    print(f"  登録 {_count('orders.jsonl')} 件 (① は登録しない・③ は二重に登録しない)")
    return {"runs": out, "model_props": seen_props, "orders": _count("orders.jsonl")}


RUN = {"schema": sec_schema, "confirm": sec_confirm, "idem": sec_idem, "self": sec_self, "gold": sec_gold,
       "wire": sec_wire, "tasks": sec_tasks, "host": sec_host}


async def amain(argv=None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="場面をカンマ区切り: " + ",".join(SECTIONS))
    ap.add_argument("--all", action="store_true", help="gold で購買の依頼 10 件すべて (既定は 4 件)")
    ap.add_argument("--user", default="U-01", help="利用者 (既定 U-01 山根 翔太)")
    ap.add_argument("--show", action="store_true", help="wire で素の JSON も出す")
    ap.add_argument("--name", default="")
    a = ap.parse_args(argv)
    want = a.only.split(",") if a.only else SECTIONS
    bad = [w for w in want if w not in RUN]
    if bad:
        raise SystemExit(f"--only が不明です: {bad} (使える: {SECTIONS})")
    _quiet()
    prev_state, prev_user = os.environ.get("SOLAHA_STATE_DIR"), os.environ.pop("SOLAHA_USER", None)
    result = {}
    try:
        for i, w in enumerate(want):
            # 場面ごとに書き込み先を新しくする (発注番号・二重登録の判定が前の場面に引きずられない)
            os.environ["SOLAHA_STATE_DIR"] = tempfile.mkdtemp(prefix=f"lab06_{w}_")
            if i:
                print()
            result[w] = await RUN[w](a)
    finally:
        set_user(None)
        if prev_state is None:
            os.environ.pop("SOLAHA_STATE_DIR", None)
        else:
            os.environ["SOLAHA_STATE_DIR"] = prev_state
        if prev_user is not None:
            os.environ["SOLAHA_USER"] = prev_user
    if a.name:
        write_json(os.path.join(out_dir(LAB), f"summary_{a.name}.json"), result)
    return result


def main(argv=None) -> dict:
    return anyio.run(amain, argv)


if __name__ == "__main__":
    from common.kit import utf8_console
    utf8_console()
    main()
