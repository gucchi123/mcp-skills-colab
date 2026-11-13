"""発注・在庫の MCP サーバ (ユースケース 2)。読む道具と、発注する道具 (書き込み) を持つ。

道具:
  get_stock(sku)                               在庫・発注点・発注先・単価
  list_below_reorder()                         発注点以下の品目
  create_purchase_order(sku, request_id, qty)  発注を登録する (人の確認つき・同じ request_id は二重に登録しない)

🔴 書き込みの道具の守り (サーバの側で守る。モデルへの指示だけに頼らない):
  1. 確認: 登録の前に、利用者に「何を・いくつ・いくらで・どこへ」を見せて確認を取る (MRTR の入力要求)。断れば登録しない
  2. 二重登録の防止: request_id が同じ依頼は、2 回目以降は前の結果を返すだけ (再試行で二重に発注しない)
  3. 規程: 発注先が取引停止なら代わりの発注先へ。どちらも無ければ登録せずに人へ回す。数量は購買規程で丸める
  4. 承認: 金額が 10 万円を超える発注は「承認待ち」で登録する (発注先へは送らない)。承認はこのサーバの外で人がする
起動: python -m servers.inventory
"""
from __future__ import annotations

import datetime as dt
import json
import os
from typing import Annotated

from pydantic import BaseModel, Field

from mcp.server import MCPServer
from mcp.server.mcpserver import Elicit, Resolve
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from common.identity import NotAllowed, audit, audit_confirm_requested, current_user
from common.kit import append_jsonl, data_path, read_csv, read_jsonl, state_dir, utf8_console
from common.rules import po_approval

SERVER = "inventory"
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITES = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=True)

ITEMS = {r["sku"]: r for r in read_csv(data_path("inventory", "inventory.csv"))}
SUPPLIERS = {r["supplier_id"]: r for r in read_csv(data_path("inventory", "suppliers.csv"))}
for r in ITEMS.values():
    for k in ("stock", "reorder_point", "lot_size", "max_stock", "unit_price", "lead_time_days"):
        r[k] = int(r[k])

mcp = MCPServer(SERVER, instructions="ソラハ電機 (架空) の在庫を調べ、発注を登録するサーバ。発注は利用者の確認を取ってから登録する。")


class Stock(BaseModel):
    sku: str
    name: str
    stock: int
    reorder_point: int = Field(description="発注点。在庫がこれ以下なら補充する")
    lot_size: int = Field(description="発注の単位")
    max_stock: int
    unit_price: int
    supplier: str = Field(description="主の発注先 (番号と名前と取引状況)")
    alt_supplier: str | None
    needs_order: bool


class Order(BaseModel):
    order_id: str
    request_id: str
    sku: str
    qty: int
    supplier_id: str
    amount_yen: int
    status: str = Field(description="発注済み / 承認待ち (承認者) / 登録しない (理由)")
    approver: str | None
    note: str | None
    duplicate: bool = Field(description="同じ request_id の 2 回目以降なら true (新たには登録していない)")


def _sup(sid: str | None) -> str | None:
    if not sid:
        return None
    s = SUPPLIERS[sid]
    return f"{sid} {s['name']} ({s['status']})"


def _stock(r: dict) -> Stock:
    return Stock(sku=r["sku"], name=r["name"], stock=r["stock"], reorder_point=r["reorder_point"],
                 lot_size=r["lot_size"], max_stock=r["max_stock"], unit_price=r["unit_price"],
                 supplier=_sup(r["supplier_id"]), alt_supplier=_sup(r["alt_supplier_id"]),
                 needs_order=r["stock"] <= r["reorder_point"])


@mcp.tool(title="在庫を見る", annotations=READ_ONLY)
def get_stock(sku: str) -> Stock:
    """品目番号 (P-101 のような部品、K- 梱包材、T- 工具、M- 組立品) の在庫・発注点・発注の単位・最大在庫・単価・発注先を返す。"""
    r = ITEMS.get(sku.strip().upper())
    if not r:
        raise ToolError(f"品目 {sku} はありません")
    audit(SERVER, "get_stock", sku=r["sku"])
    return _stock(r)


@mcp.tool(title="発注点以下の品目", annotations=READ_ONLY)
def list_below_reorder() -> list[Stock]:
    """在庫が発注点以下になっている品目 (補充が必要な候補) をすべて返す。"""
    rows = [_stock(r) for r in ITEMS.values() if r["stock"] <= r["reorder_point"]]
    audit(SERVER, "list_below_reorder", returned=[s.sku for s in rows])
    return rows


def _orders_path() -> str:
    return os.path.join(state_dir(), "orders.jsonl")


def _existing(request_id: str) -> dict | None:
    p = _orders_path()
    if not os.path.exists(p):
        return None
    return next((o for o in read_jsonl(p) if o["request_id"] == request_id), None)


def _plan(sku: str, qty: int | None) -> dict:
    """購買規程を当てはめた発注の案 (登録はしない)。"""
    r = ITEMS.get(sku.strip().upper())
    if not r:
        raise ToolError(f"品目 {sku} はありません")
    if r["stock"] > r["reorder_point"]:
        return {"sku": r["sku"], "status": "登録しない", "note": f"在庫 {r['stock']:,} が発注点 {r['reorder_point']:,} を上回っている"}
    sup = r["supplier_id"] if SUPPLIERS[r["supplier_id"]]["status"] == "取引中" else (
        r["alt_supplier_id"] if r["alt_supplier_id"] and SUPPLIERS[r["alt_supplier_id"]]["status"] == "取引中" else None)
    if not sup:
        return {"sku": r["sku"], "status": "登録しない", "note": "主の発注先が取引停止で、代わりの発注先がない。人に回す"}
    room = (r["max_stock"] - r["stock"]) // r["lot_size"] * r["lot_size"]
    if qty is None:                       # 数を言われなければ、規程どおり最大在庫まで (発注の単位で切り捨て)
        qty = max(r["lot_size"], room)
    q = max(r["lot_size"], min(qty, room) // r["lot_size"] * r["lot_size"])
    note = None if q == qty else f"求められた {qty:,} 個を、発注の単位 {r['lot_size']:,} と最大在庫 {r['max_stock']:,} に合わせて {q:,} 個にした"
    amount = q * r["unit_price"]
    return {"sku": r["sku"], "qty": q, "supplier_id": sup, "amount_yen": amount, "approver": po_approval(amount), "note": note,
            "status": "承認待ち" if po_approval(amount) else "発注済み"}


class Confirm(BaseModel):
    ok: bool = Field(description="この内容で登録してよければ true")


def ask_confirm(sku: str, request_id: str, qty: int | None = None) -> Elicit[Confirm] | Confirm:
    """登録の前に利用者へ確認する。登録しない案 (在庫が足りている・発注先が無い) や、同じ依頼の 2 回目は確認を求めない。"""
    if _existing(request_id):
        return Confirm(ok=True)
    p = _plan(sku, qty)
    if p["status"] == "登録しない":
        return Confirm(ok=True)
    sup = SUPPLIERS[p["supplier_id"]]["name"]
    msg = (f"発注を登録します: {p['sku']} {ITEMS[p['sku']]['name']} を {p['qty']:,} 個、{sup} へ、{p['amount_yen']:,} 円。"
           + (f" {p['approver']}の承認待ちで登録します。" if p["approver"] else " 発注先へそのまま送ります。")
           + (f"（{p['note']}）" if p["note"] else "") + " よろしいですか。")
    # 🔴 断られた (decline) ときは本体まで来ない (SDK が先に失敗を返す)。確認を求めたことはここで残す
    audit_confirm_requested(SERVER, "create_purchase_order", request_id, sku=p["sku"], qty=p["qty"],
                            amount_yen=p["amount_yen"])
    return Elicit(msg, Confirm)


@mcp.tool(title="発注を登録する", annotations=WRITES)
def create_purchase_order(sku: str, request_id: str, confirm: Annotated[Confirm, Resolve(ask_confirm)],
                          qty: int | None = None) -> Order:
    """品目の発注を登録する。登録の前に利用者に内容を見せて確認を取る。
    qty を省くと、購買規程どおり最大在庫まで (発注の単位で切り捨て) 発注する。数を言われたときだけ qty を渡す。
    request_id は依頼ごとに一つ決めた文字列 (例: 依頼の番号)。同じ request_id で呼び直しても二重には発注しない。
    在庫が発注点を上回る・発注先が取引停止で代わりも無いときは登録しない。10 万円を超える発注は承認待ちで登録する。"""
    try:
        user = current_user()
    except NotAllowed as e:
        raise ToolError(str(e)) from None
    prev = _existing(request_id)
    if prev:
        audit(SERVER, "create_purchase_order", request_id=request_id, duplicate=True, order_id=prev["order_id"])
        return Order(**{**prev, "duplicate": True})
    p = _plan(sku, qty)
    if p["status"] == "登録しない":
        audit(SERVER, "create_purchase_order", request_id=request_id, sku=p["sku"], refused=p["note"])
        return Order(order_id="-", request_id=request_id, sku=p["sku"], qty=0, supplier_id="-", amount_yen=0,
                     status="登録しない", approver=None, note=p["note"], duplicate=False)
    if not confirm.ok:
        audit(SERVER, "create_purchase_order", request_id=request_id, sku=p["sku"], declined=True)
        raise ToolError("利用者が登録を取りやめました。発注は登録していません")
    n = len(read_jsonl(_orders_path())) + 1 if os.path.exists(_orders_path()) else 1
    order = {"order_id": f"PO-{n:04d}", "request_id": request_id, "sku": p["sku"], "qty": p["qty"],
             "supplier_id": p["supplier_id"], "amount_yen": p["amount_yen"], "status": p["status"],
             "approver": p["approver"], "note": p["note"], "by": user["id"],
             "at": dt.datetime.now().isoformat(timespec="seconds")}
    append_jsonl(_orders_path(), [order])
    audit(SERVER, "create_purchase_order", request_id=request_id, order_id=order["order_id"], status=order["status"],
          amount_yen=order["amount_yen"])
    return Order(**{k: order[k] for k in Order.model_fields if k != "duplicate"}, duplicate=False)


@mcp.resource("inventory://purchase_policy", title="購買規程", mime_type="text/markdown")
def purchase_policy() -> str:
    """発注してよいとき・発注数・発注先・承認の規程。"""
    with open(data_path("inventory", "purchase_policy.md"), encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    utf8_console()
    mcp.run()
