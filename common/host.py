"""ホスト: MCP サーバの道具を Claude に見せ、Claude が選んだ道具を MCP で呼んで結果を返す、を繰り返す (第 2 部・第 10 部)。

  Host(["kb", "crm"], user="U-05", provider=get_provider())
    1. サーバごとに MCP の Client をつなぐ (同じプロセス内 / stdio の子プロセス / HTTP + トークン)
    2. tools/list の結果を Claude の道具の形 {name, description, input_schema} に直す。名前は mcp__<サーバ>__<道具>
       (Claude Code と同じ付け方。Skill の allowed-tools: mcp__contract__* がそのまま効く)
    3. Messages API に request を渡し、tool_use が来たら MCP で呼び、tool_result を返す。end_turn まで繰り返す
    4. 確認 (elicitation) が来たら approver に聞く。🔴 既定は「断る」。人が承認する仕組みを入れたときだけ通す

  記録 (trace) には、モデルの発言・道具の呼び出しと結果・確認のやりとりを順に残す (講座の画面とテストで見せる)。

🔴 利用者 (user) はホストが決めてサーバに渡す。モデルには決めさせない (common/identity.py)。
🔴 道具の結果は「データ」。中に指示が書かれていても、ホストは何も特別扱いしない = 判断はモデルと仕組み (権限・確認) が担う。
"""
from __future__ import annotations

import fnmatch
import json
import logging
import os
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import mcp.types as types
from mcp import Client, StdioServerParameters

from common.identity import set_user
from common.kit import ROOT, state_dir
from common.llm import base_request

ALL_SERVERS = ("kb", "crm", "inventory", "expense", "report", "contract")
SEP = "__"


def tool_name(server: str, tool: str) -> str:
    return f"mcp{SEP}{server}{SEP}{tool}"


def split_name(name: str) -> tuple[str, str]:
    _, server, tool = name.split(SEP, 2)
    return server, tool


# ---------------------------------------------------------------- 確認 (elicitation) の答え方
@dataclass
class ConfirmRequest:
    server: str
    tool: str
    args: dict
    message: str
    schema: dict


Approver = Callable[[ConfirmRequest], Awaitable[tuple[str, dict | None]] | tuple[str, dict | None]]


def decline_all(req: ConfirmRequest):
    """既定: すべて断る (人の承認の仕組みが無いなら、書き込みは通さない)。"""
    return ("decline", None)


def accept_all(req: ConfirmRequest):
    """テスト用: すべて承認する。🔴 本番で使わない (人の確認を省くのと同じ)。"""
    return ("accept", {"ok": True})


def ask_terminal(req: ConfirmRequest):
    """ターミナルで人に聞く (ノートブックでも input() で動く)。"""
    print(f"\n[確認] {req.server}.{req.tool} {json.dumps(req.args, ensure_ascii=False)}\n  {req.message}")
    a = input("  承認しますか？ (y/N) > ").strip().lower()
    return ("accept", {"ok": True}) if a in ("y", "yes", "はい") else ("decline", None)


# ---------------------------------------------------------------- 結果
@dataclass
class RunResult:
    text: str                                   # 最後のモデルの文
    trace: list[dict]                           # 起きたことの順の記録
    messages: list[dict]                        # Messages API に渡した会話 (次の質問に続けるときに使う)
    usage: dict = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})
    stop: str = "end_turn"                      # end_turn / max_turns / refusal / max_tokens

    def tool_calls(self) -> list[dict]:
        return [e for e in self.trace if e["type"] == "tool"]

    def called(self) -> list[str]:
        return [e["tool"] for e in self.tool_calls()]


def result_text(r: types.CallToolResult) -> str:
    """MCP の道具の結果を、Claude に返す文字列にする。構造化された結果があれば JSON で渡す。"""
    if r.structured_content is not None and not r.is_error:
        return json.dumps(r.structured_content, ensure_ascii=False)
    parts = [c.text for c in r.content if getattr(c, "type", "") == "text"]
    return "\n".join(parts) if parts else ""


# ---------------------------------------------------------------- ホスト
class Host:
    """async with Host([...], user=..., provider=...) as h: r = await h.run("質問")"""

    def __init__(self, servers=ALL_SERVERS, *, user: str | None, provider, mode: str = "inprocess",
                 system: str | None = None, allowed_tools: list[str] | None = None,
                 approver: Approver = decline_all, model: str | None = None, max_tokens: int = 16000,
                 urls: dict[str, str] | None = None, tokens: dict[str, str] | None = None, env: dict | None = None,
                 extra: dict[str, Any] | None = None, tag_user: bool = False):
        """servers: サーバ名の並び (ALL_SERVERS から)
        mode   : inprocess (同じプロセス・講座のテスト向け) / stdio (子プロセス・Claude Desktop と同じつなぎ方) /
                 http (urls と tokens で。利用者はトークンが決める)
        extra  : servers/ 以外のサーバ {名前: MCPServer のインスタンス か Client に渡せるつなぎ先}。servers に名前を並べると使う
        allowed_tools: 見せる道具を mcp__crm__* のような型で絞る (最小権限。Skill の allowed-tools と同じ考え)
        tag_user: request に metadata.user_id (= user) を入れる。モデルに見える文は変わらない。同じ問いを利用者を替えて
                  回すラボ (11・12) で、記録 (.cache/llm.sqlite) が利用者ごとに分かれるようにする (2026-11-01)
        """
        self.server_names = list(servers)
        self.user = user
        self.provider = provider
        self.mode = mode
        self.system = system
        self.allowed = allowed_tools
        self.approver = approver
        self.model = model
        self.max_tokens = max_tokens
        self.urls = urls or {}
        self.tokens = tokens or {}
        self.env = env or {}
        self.extra = extra or {}
        self.tag_user = tag_user
        self.clients: dict[str, Client] = {}
        self.tools: list[dict] = []             # Claude に渡す形
        self.mcp_tools: dict[str, types.Tool] = {}
        self._stack: AsyncExitStack | None = None
        self._calling: tuple[str, str, dict] | None = None
        self._trace: list[dict] = []

    # ---- つなぐ
    def _target(self, name: str):
        if self.mode == "inprocess":
            import importlib
            return importlib.import_module(f"servers.{name}").mcp
        if self.mode == "stdio":
            env = {**os.environ, "PYTHONUTF8": "1", **self.env}
            if self.user:
                env["SOLAHA_USER"] = self.user          # stdio では「起動した人 = 利用者」
            from mcp.client.stdio import stdio_client
            params = StdioServerParameters(command=sys.executable, args=["-m", f"servers.{name}"], cwd=ROOT, env=env)
            # 子プロセスの標準エラーはファイルに残す (Jupyter の出力先には fileno が無く、そのまま渡すと落ちる)
            log = self._stack.enter_context(open(os.path.join(state_dir(), f"stdio_{name}.log"), "a", encoding="utf-8"))
            return stdio_client(params, errlog=log)
        if self.mode == "http":
            import httpx2
            from mcp.client.streamable_http import streamable_http_client
            h = {"Authorization": f"Bearer {self.tokens[name]}"} if name in self.tokens else {}
            return streamable_http_client(self.urls[name], http_client=httpx2.AsyncClient(headers=h))
        raise ValueError(f"mode が不明です: {self.mode}")

    async def __aenter__(self):
        if self.mode == "inprocess":
            set_user(self.user)                          # 同じプロセスのサーバは contextvar で受け取る
            # 道具の失敗はサーバのログにも出る (同じプロセスなので画面に混ざる)。記録 (trace) に残るので黙らせる
            logging.getLogger("mcp.server.mcpserver.server").setLevel(logging.WARNING)
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()
        for name in self.server_names:
            target = self.extra[name] if name in self.extra else self._target(name)
            c = await self._stack.enter_async_context(Client(target, elicitation_callback=self._on_elicit))
            self.clients[name] = c
        await self.refresh_tools()
        return self

    async def __aexit__(self, *exc):
        await self._stack.__aexit__(*exc)

    async def refresh_tools(self) -> None:
        self.tools, self.mcp_tools = [], {}
        for name, c in self.clients.items():
            for t in (await c.list_tools()).tools:
                full = tool_name(name, t.name)
                if self.allowed is not None and not any(fnmatch.fnmatchcase(full, p) for p in self.allowed):
                    continue
                self.mcp_tools[full] = t
                self.tools.append({"name": full, "description": t.description or "", "input_schema": t.input_schema})

    # ---- 確認 (サーバ → ホスト)
    async def _on_elicit(self, ctx, params: types.ElicitRequestParams):
        server, tool, args = self._calling or ("?", "?", {})
        req = ConfirmRequest(server, tool, args, params.message,
                             getattr(params, "requested_schema", None) or {})
        ans = self.approver(req)
        if hasattr(ans, "__await__"):
            ans = await ans
        action, content = ans
        self._trace.append({"type": "confirm", "server": server, "tool": tool, "message": params.message,
                            "action": action})
        return types.ElicitResult(action=action, content=content)

    # ---- 道具を 1 つ呼ぶ
    async def call(self, full: str, args: dict) -> tuple[str, bool]:
        if full not in self.mcp_tools:
            # 見せていない道具をモデルが名乗ってきた (幻の道具・絞った道具)。呼ばずに断る
            self._trace.append({"type": "tool", "server": None, "tool": full, "args": args, "is_error": True,
                                "text": "その道具はありません", "blocked": True})
            return f"道具 {full} はありません (使える道具だけを使ってください)", True
        server, tool = split_name(full)
        self._calling = (server, tool, args)
        try:
            r = await self.clients[server].call_tool(tool, args)
        finally:
            self._calling = None
        txt = result_text(r)
        self._trace.append({"type": "tool", "server": server, "tool": tool, "args": args,
                            "is_error": bool(r.is_error), "text": txt, "structured": r.structured_content})
        return txt, bool(r.is_error)

    # ---- 質問 1 つを最後まで
    def request(self, messages: list[dict]) -> dict:
        req = base_request(self.model, self.max_tokens)
        if self.system:
            req["system"] = self.system
        if self.tools:
            req["tools"] = self.tools
        if self.tag_user and self.user:
            req["metadata"] = {"user_id": self.user}
        req["messages"] = messages
        return req

    async def run(self, question: str | list[dict], *, history: list[dict] | None = None, max_turns: int = 10) -> RunResult:
        content = question if isinstance(question, list) else [{"type": "text", "text": question}]
        messages = list(history or []) + [{"role": "user", "content": content}]
        self._trace = []
        usage = {"input_tokens": 0, "output_tokens": 0}
        stop, text = "max_turns", ""
        for _ in range(max_turns):
            resp = self.provider.create(json.loads(json.dumps(self.request(messages))))   # 呼び先に渡すのは複製
            for k in usage:
                usage[k] += int(resp.get("usage", {}).get(k, 0) or 0)
            blocks = resp["content"]
            messages.append({"role": "assistant", "content": blocks})   # 思考ブロックも含めてそのまま返す
            text = "".join(b.get("text", "") for b in blocks if b["type"] == "text")
            uses = [b for b in blocks if b["type"] == "tool_use"]
            self._trace.append({"type": "model", "text": text, "tool_uses": [{"name": b["name"], "input": b["input"]} for b in uses],
                                "stop_reason": resp.get("stop_reason")})
            if resp.get("stop_reason") != "tool_use" or not uses:
                stop = resp.get("stop_reason") or "end_turn"
                break
            results = []
            for b in uses:
                txt, err = await self.call(b["name"], b["input"])
                r = {"type": "tool_result", "tool_use_id": b["id"], "content": txt}
                if err:
                    r["is_error"] = True
                results.append(r)
            messages.append({"role": "user", "content": results})
        return RunResult(text=text, trace=list(self._trace), messages=messages, usage=usage, stop=stop)


def show(r: RunResult, width: int = 160) -> None:
    """記録を画面に出す (講座の録画で見せる形)。"""
    for e in r.trace:
        if e["type"] == "model":
            if e["text"]:
                print(f"🤖 {e['text']}")
            for u in e["tool_uses"]:
                print(f"   → {u['name']} {json.dumps(u['input'], ensure_ascii=False)}")
        elif e["type"] == "tool":
            mark = "✗" if e["is_error"] else "✓"
            t = e["text"].replace("\n", " ")
            print(f"   {mark} {e['tool']}: {t[:width]}{'…' if len(t) > width else ''}")
        elif e["type"] == "confirm":
            print(f"   ? 確認 {e['tool']}: {e['message']} → {e['action']}")
    print(f"[{r.stop}] in={r.usage['input_tokens']} out={r.usage['output_tokens']}")
