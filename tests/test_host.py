"""ホスト (common/host.py) と呼び先 (common/llm.py) の試験。API キー不要・API は呼ばない。

確かめること:
  - 6 サーバの道具が mcp__<サーバ>__<道具> の名前で Claude の道具の形になる (17 個・confirm は見せない)
  - allowed_tools で見せる道具を絞れる。見せていない道具をモデルが名乗っても呼ばない
  - 偽モデルの筋書きで「道具を呼ぶ → 結果を返す → 答える」が回り、結果がモデルに渡る
  - 確認 (elicitation) は既定で断る → 発注は登録されない。承認役を入れたときだけ登録される
  - stdio で子プロセスのサーバにつないでも、利用者 (SOLAHA_USER) で見える項目が変わる
  - 記録の再生: 記録にあれば返す・無ければ API を呼ばずに CacheMiss。記録にも request にも API キーが入らない
"""
from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from common.host import Host, accept_all, tool_name  # noqa: E402
from common.kit import read_json, data_path, read_jsonl  # noqa: E402
from common.llm import CacheMiss, MockProvider, Record, RecordedProvider, say, tool_results, use  # noqa: E402

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def fresh_state(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLAHA_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_LEDGER", str(tmp_path / "ledger.jsonl"))
    yield


async def test_tools_are_claude_shaped():
    async with Host(user="U-05", provider=MockProvider()) as h:
        names = [t["name"] for t in h.tools]
        cat = read_json(data_path("questions", "tool_catalog.json"))
        assert sorted(names) == sorted(tool_name(s, t) for s, ts in cat.items() for t in ts)
        assert len(names) == 17
        po = next(t for t in h.tools if t["name"] == "mcp__inventory__create_purchase_order")
        assert set(po) == {"name", "description", "input_schema"} and "confirm" not in po["input_schema"]["properties"]


async def test_allowed_tools_and_unknown_tool():
    def plan(msgs, tools):
        if not tool_results(msgs):
            return [use("mcp__crm__get_customer", {"customer_id": "C-001"}, "t1")]
        return [say("できませんでした")]

    p = MockProvider(plan)
    async with Host(["kb", "crm"], user="U-05", provider=p, allowed_tools=["mcp__kb__*"]) as h:
        assert [t["name"] for t in h.tools] == ["mcp__kb__search_regulations", "mcp__kb__get_regulation"]
        r = await h.run("C-001 の連絡先は？")
    assert r.trace[1]["blocked"] is True and r.trace[1]["is_error"] is True
    assert not os.path.exists(os.path.join(os.environ["SOLAHA_STATE_DIR"], "audit.jsonl"))   # サーバまで届いていない


async def test_mock_loop_passes_results_back():
    def plan(msgs, tools):
        done = tool_results(msgs)
        if not done:
            return [say("顧客を探します。"), use("mcp__crm__find_customer", {"query": "丸星"}, "t1")]
        if len(done) == 1:
            cid = json.loads(done[0]["text"])["result"][0]["id"]
            return [use("mcp__crm__get_customer", {"customer_id": cid}, "t2")]
        c = json.loads(done[1]["text"])
        return [say(f"{c['name']} の担当営業は {c['sales_rep']} です。")]

    p = MockProvider(plan)
    async with Host(["crm"], user="U-02", provider=p, system="ソラハ電機の社内アシスタント") as h:
        r = await h.run("丸星の担当営業は？")
    assert r.called() == ["find_customer", "get_customer"] and r.stop == "end_turn"
    assert "担当営業は U-" in r.text
    last = p.requests[-1]
    assert last["system"] == "ソラハ電機の社内アシスタント" and last["model"] == "claude-opus-5-5"
    assert last["output_config"] == {"effort": "high"}
    assert [m["role"] for m in last["messages"]] == ["user", "assistant", "user", "assistant", "user"]


def _po_plan(msgs, tools):
    if not tool_results(msgs):
        return [use("mcp__inventory__create_purchase_order", {"sku": "P-102", "request_id": "h-1"}, "t1")]
    return [say("処理しました")]


async def test_confirm_declined_by_default(tmp_path):
    async with Host(["inventory"], user="U-02", provider=MockProvider(_po_plan)) as h:
        r = await h.run("P-102 を発注して")
    assert [e["action"] for e in r.trace if e["type"] == "confirm"] == ["decline"]
    assert r.tool_calls()[0]["is_error"] is True
    assert not os.path.exists(tmp_path / "orders.jsonl")


async def test_confirm_accepted_registers(tmp_path):
    async with Host(["inventory"], user="U-02", provider=MockProvider(_po_plan), approver=accept_all) as h:
        r = await h.run("P-102 を発注して")
    assert [e["action"] for e in r.trace if e["type"] == "confirm"] == ["accept"]
    assert r.tool_calls()[0]["is_error"] is False
    assert len(read_jsonl(str(tmp_path / "orders.jsonl"))) == 1


async def test_stdio_user_from_env():
    def plan(msgs, tools):
        if not tool_results(msgs):
            return [use("mcp__crm__get_customer", {"customer_id": "C-002"}, "t1")]
        return [say("ok")]

    out = {}
    for uid in ("U-01", "U-02"):
        async with Host(["crm"], user=uid, provider=MockProvider(plan), mode="stdio") as h:
            out[uid] = (await h.run("C-002 は？")).tool_calls()[0]["structured"]
    assert out["U-01"]["contact"]["email"] == "（非表示）"
    assert out["U-02"]["contact"]["email"].endswith(".example")


def test_replay_record(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_NO_KEY", "1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rec = Record(str(tmp_path / "llm.sqlite"))
    req = {"model": "claude-opus-5-5", "max_tokens": 100, "messages": [{"role": "user", "content": "こんにちは"}]}
    resp = {"content": [{"type": "text", "text": "記録の答え"}], "stop_reason": "end_turn",
            "usage": {"input_tokens": 3, "output_tokens": 4}}
    rec.put(req, resp)
    p = RecordedProvider(replay=True, record=rec)
    assert p.create(dict(req))["content"][0]["text"] == "記録の答え"
    assert Record.key({"messages": req["messages"], "max_tokens": 100, "model": "claude-opus-5-5"}) == Record.key(req)
    with pytest.raises(CacheMiss):
        p.create({**req, "max_tokens": 101})
    led = read_jsonl(os.environ["LLM_LEDGER"])
    assert led[-1]["cached"] is True and led[-1]["cost_usd"] == 0


async def test_no_key_in_request_or_record(tmp_path, monkeypatch):
    secret = "sk-ant-test-" + "x" * 20
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    p = MockProvider()
    async with Host(["kb"], user="U-05", provider=p) as h:
        await h.run("出張の申請はいつまで？")
    assert secret not in json.dumps(p.requests, ensure_ascii=False)
    rec = Record(str(tmp_path / "llm.sqlite"))
    rec.put(p.requests[0], {"content": []})
    assert secret.encode() not in (tmp_path / "llm.sqlite").read_bytes()
