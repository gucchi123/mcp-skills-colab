"""第 7 部: HTTP で公開した顧客台帳のサーバに、トークンを変えて当てる (実際にサーバを別プロセスで立てる)。

  - トークン無し・署名違い・宛先違い・期限切れは 401、範囲 (scope) 不足は 403
  - 正しいトークンなら、トークンの持ち主ごとに見える項目が変わる (U-01 は担当外の連絡先が非表示・U-02 は見える)
  - 引数や環境変数で利用者を名乗っても変わらない (トークンが決める)
"""
from __future__ import annotations

import os
import secrets
import socket
import subprocess
import sys
import time

import httpx2 as httpx
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("SOLAHA_DEMO_AUTH_KEY", secrets.token_hex(32))

from mcp import Client  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402

from common.demo_auth import issue  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    port = _free_port()
    env = {**os.environ, "PYTHONUTF8": "1", "SOLAHA_STATE_DIR": str(tmp_path_factory.mktemp("state")),
           "SOLAHA_USER": "U-04"}                    # 🔴 わざと部長を入れておく。HTTP ではトークンが優先されること
    p = subprocess.Popen([sys.executable, "-m", "servers.http_crm", "--port", str(port)], cwd=ROOT, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}/mcp"
    for _ in range(100):
        try:
            httpx.get(f"http://127.0.0.1:{port}/", timeout=0.3); break
        except Exception:
            time.sleep(0.1)
    yield url
    p.terminate(); p.wait(10)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _post(url, token=None):
    h = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2026-07-28", "Mcp-Method": "tools/list"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    meta = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
            "io.modelcontextprotocol/clientInfo": {"name": "test", "version": "0"},
            "io.modelcontextprotocol/clientCapabilities": {}}
    return httpx.post(url, headers=h, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": meta}})


def test_rejects_bad_tokens(server):
    assert _post(server).status_code == 401
    good = issue("U-02", server, ["crm.read"])
    forged = good[:-4] + ("AAAA" if not good.endswith("AAAA") else "BBBB")
    assert _post(server, forged).status_code == 401
    assert _post(server, issue("U-02", "http://127.0.0.1:1/mcp", ["crm.read"])).status_code == 401     # 宛先違い
    assert _post(server, issue("U-02", server, ["crm.read"], ttl=-5)).status_code == 401              # 期限切れ
    assert _post(server, issue("U-02", server, ["inventory.read"])).status_code == 403                # 範囲不足
    assert _post(server, good).status_code == 200


async def _get(url, token, cid):
    async with Client(streamable_http_client(url, http_client=httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"}))) as c:
        return (await c.call_tool("get_customer", {"customer_id": cid})).structured_content


@pytest.mark.anyio
async def test_token_decides_user(server):
    u1 = await _get(server, issue("U-01", server, ["crm.read"]), "C-002")    # 一般の営業・担当外
    u2 = await _get(server, issue("U-02", server, ["crm.read"]), "C-002")    # 営業の課長
    assert u1["contact"]["email"] == "（非表示）" and u1["rank"] == "（非表示）"
    assert u2["contact"]["email"].endswith(".example") and u2["rank"] != "（非表示）"
