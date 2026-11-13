"""サーバの試験の書き方の見本: Client(サーバ) で同じプロセスにつなぐ (子プロセスもポートも要らない)。

    python -m pytest -q lab03_first_server/tests
"""
from __future__ import annotations

import os
import sys

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

from mcp import Client  # noqa: E402
from mcp.shared.exceptions import MCPError  # noqa: E402

import step1_server  # noqa: E402
import step2_server  # noqa: E402

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_step1_search():
    async with Client(step1_server.mcp) as c:
        r = await c.call_tool("search_regulations", {"keyword": "在宅勤務", "limit": 1})
        assert r.is_error is False
        assert r.content[0].text.startswith("a-11")


async def test_step1_no_hit_is_not_error():
    async with Client(step1_server.mcp) as c:
        r = await c.call_tool("search_regulations", {"keyword": "存在しない言葉"})
        assert r.is_error is False and "ありません" in r.content[0].text


async def test_step2_structured():
    async with Client(step2_server.mcp) as c:
        r = await c.call_tool("search_regulations", {"keyword": "経費", "limit": 2})
        hits = r.structured_content["result"]
        assert len(hits) == 2 and set(hits[0]) == {"doc_id", "title", "matched", "first_line"}
        g = await c.call_tool("get_regulation", {"doc_id": "A-05"})            # 大文字でも引ける
        assert g.structured_content["doc_id"] == "a-05"


async def test_step2_tool_error():
    async with Client(step2_server.mcp) as c:
        r = await c.call_tool("get_regulation", {"doc_id": "a-99"})
        assert r.is_error is True                                              # 例外ではなく結果で返る
        assert "文書 a-99 はありません" in r.content[0].text


async def test_step2_limit_range():
    async with Client(step2_server.mcp) as c:
        r = await c.call_tool("search_regulations", {"keyword": "出張", "limit": 50})
        assert r.is_error is True and "less than or equal to 10" in r.content[0].text


async def test_step2_resource_and_prompt():
    async with Client(step2_server.mcp) as c:
        rr = await c.read_resource("regs://a-01")
        assert rr.contents[0].text.startswith("# 組織規程")
        with pytest.raises(MCPError):                                          # 資料の失敗は結果ではなく例外で届く
            await c.read_resource("regs://a-99")
        p = await c.get_prompt("answer_with_citation", {"question": "Q"})
        assert "根拠" in p.messages[0].content.text
