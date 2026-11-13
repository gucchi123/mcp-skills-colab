"""ラボ 7 の部品: HTTP の顧客台帳サーバを子プロセスで立てる・素の POST・トークンを読む。

🔴 鍵 (SOLAHA_DEMO_AUTH_KEY) は表示しない。トークンも画面には先頭 12 文字だけ出す (短い期限の講座用のものでも)。
"""
from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager

import httpx2 as httpx

from common.kit import ROOT

PROTO = "2026-07-28"
META = {"io.modelcontextprotocol/protocolVersion": PROTO,
        "io.modelcontextprotocol/clientInfo": {"name": "lab07-raw", "version": "0"},
        "io.modelcontextprotocol/clientCapabilities": {}}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def http_crm(server_user: str | None = "U-04"):
    """servers/http_crm.py を空いているポートで立て、(URL, 状態フォルダ) を渡す。抜けるときに必ず止める。

    server_user: サーバの環境変数 SOLAHA_USER にわざと入れる利用者 (HTTP ではトークンが優先されることを見せるため)。
    鍵は呼び出し側の os.environ["SOLAHA_DEMO_AUTH_KEY"] を子プロセスに引き継ぐ (表示しない)。
    """
    port = free_port()
    state = tempfile.mkdtemp(prefix="lab07_state_")
    env = {**os.environ, "PYTHONUTF8": "1", "SOLAHA_STATE_DIR": state}
    if server_user:
        env["SOLAHA_USER"] = server_user
    log = open(os.path.join(state, "http_crm.log"), "w", encoding="utf-8")
    p = subprocess.Popen([sys.executable, "-m", "servers.http_crm", "--port", str(port)], cwd=ROOT, env=env,
                         stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(150):
            if p.poll() is not None:
                raise RuntimeError(f"サーバが起動しませんでした (終了コード {p.returncode})")
            try:
                httpx.get(base + "/", timeout=0.3)
                break
            except Exception:
                time.sleep(0.1)
        yield base + "/mcp", state
    finally:
        p.terminate()
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            p.kill(); p.wait(10)
        log.close()


def post(url: str, token: str | None, method: str = "tools/list", params: dict | None = None,
         name: str | None = None) -> httpx.Response:
    """2026-07-28 の素の POST 1 通 (initialize もセッション ID も無い)。"""
    h = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": PROTO, "Mcp-Method": method}
    if name:
        h["Mcp-Name"] = name
    if token is not None:
        h["Authorization"] = f"Bearer {token}"
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": {**(params or {}), "_meta": META}}
    return httpx.post(url, headers=h, json=body, timeout=10)


def short(token: str | None) -> str:
    """画面に出すトークンの形: 先頭 12 文字 + …"""
    if token is None:
        return "(なし)"
    return token if len(token) <= 12 else f"{token[:12]}…"


def decode(token: str) -> dict:
    """v1.<中身>.<署名> の中身を読む (署名は確かめない。読むだけなら鍵は要らない = 中身は秘密ではない)。"""
    body = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
