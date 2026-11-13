"""講師の収録用の呼び先: Messages API の代わりに、Claude Agent SDK (同梱の Claude Code) をプランのログインで呼ぶ。

  LLM_PROVIDER=agent-sdk で get_provider() が返す。ホスト (common/host.py) から見ると RecordedProvider と同じ
  create(request) -> response の形。中では
    1. request の system・tools・最初の質問を、そのまま Agent SDK に渡す
       - system_prompt は request の system で丸ごと置き換える (Claude Code の既定の指示は入れない)
       - 組み込みの道具 (Read・Bash など) は外し (tools=[])、道具は request の tools だけを同じ名前・説明・型で見せる
       - 道具を後から読む仕組み (tool search) は切る (ENABLE_TOOL_SEARCH=false) → 最初から全部の道具が見える
    2. モデルが道具を選んだら、そこでいったん返す (stop_reason=tool_use)。道具はホストが本物の MCP で呼ぶ
       (権限・確認・監査はいつもどおりホストとサーバが受け持つ)
    3. 次の create(request) に入っている tool_result を、待っている道具の返事として Agent SDK に渡し、続きを待つ
  1 ターンごとに request → response を .cache/llm.sqlite に記録する。受講者のノートブックは replay でこれを再生する
  (受講者が自分のキーで回すときは、いつもどおり Messages API を呼ぶ)。

🔴 受講者向けの道ではない (講師の手元で、API クレジットを使わずに記録を作るためのもの)。キーは渡さない。
🔴 Messages API と同じではない点: Claude Code が会話に挟む短い注記が入りうる・max_tokens は効かない。記録の provider 欄に
   "agent-sdk" と残し、RUN_LOG にもそう書く。
"""
from __future__ import annotations

import asyncio
import json
import queue
import tempfile
import threading
import time

from common.llm import Record, _record

TURN_TIMEOUT = 900          # 1 ターンを待つ上限 (秒)


def _canon(args: dict) -> str:
    return json.dumps(args, sort_keys=True, ensure_ascii=False)


def _block(b) -> dict | None:
    from claude_agent_sdk import TextBlock, ThinkingBlock, ToolUseBlock
    if isinstance(b, TextBlock):
        return {"type": "text", "text": b.text}
    if isinstance(b, ThinkingBlock):
        return {"type": "thinking", "thinking": b.thinking, "signature": getattr(b, "signature", "")}
    if isinstance(b, ToolUseBlock):
        return {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
    return None


class _Session:
    """1 つの会話 = 1 つの Agent SDK のセッション (別スレッドの event loop で動かす)。"""

    def __init__(self, request: dict):
        self.request = request
        self.turns: queue.Queue = queue.Queue()          # create() へ返すターン (または例外)
        self.results: dict[str, queue.Queue] = {}         # tool_use の id → ホストが返した結果
        self.lock = threading.Lock()
        self.blocks: list[dict] = []                      # いま組み立て中のターンのブロック
        self.seen: list[dict] = []                        # この会話で読んだ tool_use ブロック (全部)
        self.claimed: set[str] = set()                    # 道具の呼び出しに割り当て済みの id
        self.pushed_ids: set[str] = set()                 # create() へ返し済みの id
        self.n_messages = 1                               # この会話でホストが送った messages の数
        self.loop: asyncio.AbstractEventLoop | None = None
        self.client = None
        self.done = False
        self.thread = threading.Thread(target=self._thread, daemon=True)
        self.thread.start()

    # ---- create() から
    def next_turn(self) -> dict:
        try:
            t = self.turns.get(timeout=TURN_TIMEOUT)
        except queue.Empty:
            raise TimeoutError(f"Agent SDK の応答が {TURN_TIMEOUT} 秒来ません")
        if isinstance(t, BaseException):
            raise t
        return t

    def deliver(self, last_user_content: list[dict]) -> None:
        """ホストが本物の MCP で呼んだ結果 (最後の user の tool_result) を、待っている道具に渡す。"""
        for r in last_user_content:
            if r.get("type") != "tool_result":
                continue
            content = r.get("content", "")
            if isinstance(content, list):
                content = "\n".join(c.get("text", "") for c in content if c.get("type") == "text")
            self._result_q(r["tool_use_id"]).put({"text": content, "is_error": bool(r.get("is_error"))})

    def close(self) -> None:
        if self.loop and self.client and not self.done:
            try:
                asyncio.run_coroutine_threadsafe(self.client.disconnect(), self.loop).result(timeout=30)
            except Exception:  # noqa: BLE001 - 片付けの失敗は無視 (子プロセスは daemon スレッドと一緒に終わる)
                pass
        for q in list(self.results.values()):                 # 待っている道具を起こす
            q.put({"text": "（会話は終わりました）", "is_error": True})
        self.thread.join(timeout=30)

    # ---- スレッドの中
    def _result_q(self, key: str) -> queue.Queue:
        with self.lock:
            return self.results.setdefault(key, queue.Queue())

    def _thread(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._main())
        except BaseException as e:  # noqa: BLE001 - create() 側で投げ直す
            self.turns.put(e)
        finally:
            self.done = True
            self.loop.close()

    def _push_turn(self, stop_reason: str, usage: dict | None = None) -> None:
        with self.lock:
            content, self.blocks = self.blocks, []
            self.pushed_ids.update(b["id"] for b in content if b["type"] == "tool_use")
        self.turns.put({"type": "message", "role": "assistant", "model": self.request.get("model"),
                        "content": content, "stop_reason": stop_reason,
                        "usage": usage or {"input_tokens": 0, "output_tokens": 0}})

    def _claim(self, full: str, args: dict) -> str | None:
        """この道具の呼び出しに当たる tool_use の id を 1 つ取る (引数が同じものを優先し、無ければ同じ名前の古い順)。"""
        with self.lock:
            cands = [b for b in self.seen if b["name"] == full and b["id"] not in self.claimed]
            if not cands:
                return None
            exact = [b for b in cands if _canon(b["input"]) == _canon(args)]
            bid = (exact or cands)[0]["id"]
            self.claimed.add(bid)
            return bid

    def _make_handler(self, full: str):
        async def handler(args: dict) -> dict:
            # 1) 受け取りのループが、この道具の tool_use ブロックを読み終えるまで待ってから、id を取る
            bid = None
            for _ in range(1500):
                bid = self._claim(full, args)
                if bid:
                    break
                await asyncio.sleep(0.02)
            if bid is None:
                raise RuntimeError(f"道具 {full} の tool_use ブロックが見つかりません")
            # 2) 並べて呼ばれる道具のブロックを少し待ってから、まだ返していないターンを返す (返すのは 1 回だけ)
            await asyncio.sleep(0.5)
            with self.lock:
                need = bid not in self.pushed_ids
            if need:
                self._push_turn("tool_use")
            # 3) ホストが本物の MCP で呼んだ結果を待つ
            r = await asyncio.to_thread(self._result_q(bid).get)
            return {"content": [{"type": "text", "text": r["text"]}], "is_error": r["is_error"]}
        return handler

    async def _main(self) -> None:
        from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, \
            SdkMcpTool, create_sdk_mcp_server
        req = self.request
        by_server: dict[str, list] = {}
        names = []
        for t in req.get("tools", []):
            _, server, tool = t["name"].split("__", 2)
            by_server.setdefault(server, []).append(
                SdkMcpTool(name=tool, description=t.get("description", ""), input_schema=t["input_schema"],
                           handler=self._make_handler(t["name"])))
            names.append(t["name"])
        first = req["messages"][0]["content"]
        prompt = first if isinstance(first, str) else "".join(c.get("text", "") for c in first if c.get("type") == "text")
        model = req.get("model", "claude-opus-5-5")
        effort = (req.get("output_config") or {}).get("effort")
        opts = ClaudeAgentOptions(
            model=model,
            system_prompt=req.get("system") or "",
            tools=[],                                     # 組み込みの道具は使わせない
            mcp_servers={s: create_sdk_mcp_server(s, tools=ts) for s, ts in by_server.items()},
            allowed_tools=names,
            strict_mcp_config=True,
            setting_sources=[],                           # 講師の手元の設定 (CLAUDE.md など) を読まない
            max_turns=60,
            cwd=tempfile.mkdtemp(prefix="sdkprov_"),
            env={"ANTHROPIC_API_KEY": "", "ENABLE_TOOL_SEARCH": "false"},
            **({"effort": effort} if effort else {}),
            **({} if effort or req.get("thinking") else {"thinking": {"type": "disabled"}}),
        )
        async with ClaudeSDKClient(opts) as c:
            self.client = c
            await c.query(prompt)
            async for m in c.receive_response():
                if isinstance(m, AssistantMessage):
                    with self.lock:
                        for b in m.content:
                            x = _block(b)
                            if x:
                                self.blocks.append(x)
                                if x["type"] == "tool_use":
                                    self.seen.append(x)
                elif isinstance(m, ResultMessage):
                    if m.is_error and not any(b["type"] == "text" for b in self.blocks):
                        raise RuntimeError(f"Agent SDK がエラーで終わりました: {(m.result or '')[:200]}")
                    u = getattr(m, "usage", None) or {}
                    self._push_turn("end_turn", {"input_tokens": int(u.get("input_tokens", 0) or 0),
                                                 "output_tokens": int(u.get("output_tokens", 0) or 0)})
                    break


class AgentSDKProvider:
    """create(request) -> response。記録にあれば記録から (LLM_CACHE=0 で記録を見ない)、無ければ Agent SDK で。"""

    name = "agent-sdk"

    def __init__(self, record: Record | None = None):
        import os
        self.record = record or Record()
        self.use_record = os.environ.get("LLM_CACHE", "1") != "0"
        self.sess: _Session | None = None

    def close(self) -> None:
        if self.sess:
            self.sess.close()
            self.sess = None

    def __del__(self):
        try:
            self.close()
        except Exception:  # noqa: BLE001
            pass

    def create(self, request: dict) -> dict:
        msgs = request["messages"]
        if self.use_record:
            hit = self.record.get(request)
            if hit is not None:
                _record({"provider": "agent-sdk", "model": request.get("model"), "cached": True, "cost_usd": 0})
                return hit
        t0 = time.time()
        if len(msgs) == 1:                                    # 新しい会話
            self.close()
            self.sess = _Session(request)
        else:
            s = self.sess
            if s is None or s.done or len(msgs) != s.n_messages + 2 or msgs[-1]["role"] != "user":
                raise RuntimeError("Agent SDK の会話の途中から続けられません (前のターンが記録の再生だった、など)。"
                                   "LLM_CACHE=0 で会話の最初から回してください")
            s.deliver(msgs[-1]["content"])
        resp = self.sess.next_turn()
        self.sess.n_messages = len(msgs)
        _record({"provider": "agent-sdk", "model": request.get("model"), "cached": False, "cost_usd": 0.0,
                 "seconds": round(time.time() - t0, 2)})
        self.record.put(request, {**resp, "provider": "agent-sdk"})
        if resp["stop_reason"] != "tool_use":
            self.close()
        return resp
