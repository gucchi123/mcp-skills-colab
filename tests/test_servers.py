"""MCP サーバの試験 (LLM なし・API キー不要・子プロセスもポートも不要)。

python -m pytest -q tests          (キットの根で)

確かめること:
  - 道具の名前がデータの道具一覧 (data/questions/tool_catalog.json) と一致する
  - 顧客台帳の「見てよい項目」が正解 189 組と一致する (規程 → common/policy.py)
  - 経費の判定が過去の申請 42 件の正解と一致する / 本人以外は申請できない / 二重に登録しない
  - 発注が購買規程の正解 (10 依頼) と一致する / 確認を断れば登録しない / 二重に発注しない
  - 月次の数字が正解 (gold_numbers.json) と一致する
  - 確認の引数 (confirm) がモデルに見せる引数の形に出ない
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["SOLAHA_STATE_DIR"] = tempfile.mkdtemp(prefix="solaha_test_")

import mcp.types as types  # noqa: E402
from mcp import Client  # noqa: E402

from common.identity import set_user, staff  # noqa: E402
from common.kit import data_path, read_json, read_jsonl  # noqa: E402
from common.policy import visible_fields  # noqa: E402
from servers import contract, crm, expense, inventory, kb, report  # noqa: E402

pytestmark = pytest.mark.anyio
SERVERS = {"kb": kb.mcp, "crm": crm.mcp, "inventory": inventory.mcp, "expense": expense.mcp, "report": report.mcp,
           "contract": contract.mcp}


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def fresh_state(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLAHA_STATE_DIR", str(tmp_path))
    yield


def as_user(uid):
    return set_user(uid)


def accept(ctx, params):
    return types.ElicitResult(action="accept", content={"ok": True})


async def _accept(ctx, params):
    return accept(ctx, params)


async def _decline(ctx, params):
    return types.ElicitResult(action="decline")


# ------------------------------------------------------------ 道具の名前
async def test_tool_names_match_catalog():
    cat = read_json(data_path("questions", "tool_catalog.json"))
    for name, srv in SERVERS.items():
        async with Client(srv) as c:
            got = sorted(t.name for t in (await c.list_tools()).tools)
        assert got == sorted(cat[name]), name


async def test_confirm_is_hidden_from_model():
    for srv, tool in ((inventory.mcp, "create_purchase_order"), (expense.mcp, "submit_expense")):
        async with Client(srv) as c:
            t = next(t for t in (await c.list_tools()).tools if t.name == tool)
        assert "confirm" not in t.input_schema["properties"]
        assert t.annotations.read_only_hint is False


# ------------------------------------------------------------ 顧客台帳
def test_policy_matches_gold_189():
    gold = read_json(data_path("crm", "access_gold.json"))
    cust = read_json(data_path("crm", "customers.json"))
    n = 0
    for uid, row in gold.items():
        for c in cust:
            assert visible_fields(staff(uid), c) == set(row[c["id"]]), (uid, c["id"])
            n += 1
    assert n == 189


async def test_crm_redacts_by_user_and_audits(tmp_path):
    tok = as_user("U-01")      # 山根 (一般の営業)。C-001 の担当、C-002 は担当外
    try:
        async with Client(crm.mcp) as c:
            own = (await c.call_tool("get_customer", {"customer_id": "C-001"})).structured_content
            other = (await c.call_tool("get_customer", {"customer_id": "C-002"})).structured_content
            person = (await c.call_tool("get_customer", {"customer_id": "IND-001"})).structured_content
    finally:
        set_user(None) if tok is None else None
    assert own["contact"]["email"].endswith(".example") and own["rank"] == crm.HIDDEN
    assert other["contact"]["email"] == crm.HIDDEN and "contact.email" in other["hidden"]
    assert person["name"] == crm.HIDDEN and person["contact"]["phone"] == crm.HIDDEN
    log = read_jsonl(os.path.join(str(tmp_path), "audit.jsonl"))
    assert [r["customer"] for r in log] == ["C-001", "C-002", "IND-001"] and all(r["user"] == "U-01" for r in log)


async def test_crm_without_user_is_error(monkeypatch):
    monkeypatch.delenv("SOLAHA_USER", raising=False)
    set_user(None)
    async with Client(crm.mcp) as c:
        r = await c.call_tool("get_customer", {"customer_id": "C-001"})
    assert r.is_error and "利用者" in r.content[0].text


# ------------------------------------------------------------ 経費
async def test_expense_matches_gold_42():
    set_user("U-01")
    claims = read_json(data_path("expense", "claims.json"))
    ja = expense.DECISION_JA
    async with Client(expense.mcp) as c:
        for cl in claims:
            r = (await c.call_tool("get_expense_status", {"claim_id": cl["id"]})).structured_content
            assert r["decision"] == ja[cl["gold"]["decision"]], cl["id"]
            assert r["approver"] == cl["gold"]["approver"], cl["id"]


async def test_expense_submit_self_only_and_idempotent(tmp_path):
    set_user("U-01")           # 山根 翔太
    args = {"employee": "山根 翔太", "category": "交通費", "expense_date": "2026-10-20", "amount": 2400,
            "vendor": "東都タクシー", "description": "客先から駅まで", "receipt": True, "request_id": "req-1"}
    async with Client(expense.mcp, elicitation_callback=_accept) as c:
        a = (await c.call_tool("submit_expense", args)).structured_content
        b = (await c.call_tool("submit_expense", args)).structured_content
        bad = await c.call_tool("submit_expense", {**args, "employee": "田村 浩二", "request_id": "req-2"})
    assert a["decision"] == "自動承認" and a["duplicate"] is False
    assert b["duplicate"] is True and b["claim_id"] == a["claim_id"]
    assert bad.is_error and "本人" in bad.content[0].text
    assert len(read_jsonl(os.path.join(str(tmp_path), "expenses.jsonl"))) == 1


async def test_expense_decline_does_not_register(tmp_path):
    set_user("U-01")
    args = {"employee": "山根 翔太", "category": "書籍費", "expense_date": "2026-10-20", "amount": 3300,
            "vendor": "青林書店", "description": "参考書", "receipt": True, "request_id": "req-9"}
    async with Client(expense.mcp, elicitation_callback=_decline) as c:
        r = await c.call_tool("submit_expense", args)
    assert r.is_error
    assert not os.path.exists(os.path.join(str(tmp_path), "expenses.jsonl"))


# ------------------------------------------------------------ 発注
async def test_purchase_matches_gold_requests():
    set_user("U-01")
    reqs = read_json(data_path("inventory", "requests.json"))
    async with Client(inventory.mcp, elicitation_callback=_accept) as c:
        for rq in reqs:
            for k, plan in enumerate(rq["gold"]["plans"]):
                want_qty = next((q for s, q in rq.get("items", []) if s == plan["sku"]), None) if rq.get("items") else None
                r = (await c.call_tool("create_purchase_order",
                                       {"sku": plan["sku"], "request_id": f"{rq['id']}-{k}",
                                        **({"qty": want_qty} if want_qty else {})})).structured_content
                if plan["action"] == "order":
                    assert (r["qty"], r["supplier_id"], r["amount_yen"], r["approver"]) == \
                           (plan["qty"], plan["supplier"], plan["amount"], plan["approval"]), rq["id"]
                    assert r["status"] == ("承認待ち" if plan["approval"] else "発注済み")
                else:
                    assert r["status"] == "登録しない", rq["id"]


async def test_purchase_decline_and_duplicate(tmp_path):
    set_user("U-01")
    async with Client(inventory.mcp, elicitation_callback=_decline) as c:
        r = await c.call_tool("create_purchase_order", {"sku": "P-102", "request_id": "x-1"})
    assert r.is_error and not os.path.exists(os.path.join(str(tmp_path), "orders.jsonl"))
    seen = []

    async def count(ctx, params):
        seen.append(params.message)
        return types.ElicitResult(action="accept", content={"ok": True})

    async with Client(inventory.mcp, elicitation_callback=count) as c:
        a = (await c.call_tool("create_purchase_order", {"sku": "P-102", "request_id": "x-2"})).structured_content
        b = (await c.call_tool("create_purchase_order", {"sku": "P-102", "request_id": "x-2"})).structured_content
    assert a["order_id"] == b["order_id"] and b["duplicate"] is True
    assert len(seen) == 1                       # 2 回目は確認も求めない
    assert len(read_jsonl(os.path.join(str(tmp_path), "orders.jsonl"))) == 1


# ------------------------------------------------------------ 月次の数字
async def test_report_numbers_match_gold():
    gold = read_json(data_path("report", "gold_numbers.json"))
    async with Client(report.mcp) as c:
        for m, g in gold.items():
            s = (await c.call_tool("get_monthly_sales", {"month": m})).structured_content
            q = (await c.call_tool("get_inquiry_counts", {"month": m})).structured_content
            inv = (await c.call_tool("get_inventory_snapshot", {"month": m})).structured_content["result"]
            assert s["total_yen"] == g["revenue_total"] and s["total_change_pct"] == g["revenue_mom_pct"], m
            assert s["top_product"] == g["top_product"], m
            assert q["total"] == g["inquiries_total"], m
            assert sorted(r["sku"] for r in inv if r["below_reorder"]) == sorted(g["low_stock_skus"]), m


# ------------------------------------------------------------ 規程・契約
async def test_kb_search_finds_expected_doc():
    cases = {"出張の申請はいつまでに出せばいいですか": "a-06", "IT 機器を買うときの決裁者": "a-07",
             "在宅勤務の申請": "a-11", "経費精算の決裁基準": "a-05", "部長が不在のときの代理": "a-04"}
    async with Client(kb.mcp) as c:
        for q, doc in cases.items():
            hits = (await c.call_tool("search_regulations", {"query": q})).structured_content["result"]
            assert hits and hits[0]["doc_id"] == doc, (q, [h["doc_id"] for h in hits])


async def test_contracts_listed():
    async with Client(contract.mcp) as c:
        rows = (await c.call_tool("list_contracts", {})).structured_content["result"]
        text = (await c.call_tool("get_contract", {"contract_id": "lc-03"})).content[0].text
    assert [r["id"] for r in rows] == [f"LC-0{i}" for i in range(1, 9)]
    assert "LC-03" in text
