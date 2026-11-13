"""Claude (モデル) の呼び先をまとめる。MCP×Skills 講座のホストはすべてここから get_provider() で受け取る。

呼び先 (provider)。引数か環境変数 LLM_PROVIDER で選ぶ:
  - mock      : API キー不要。ラボごとの筋書き (plan) で答える偽モデル。道具の呼び出しも出す。🔴 数字は性能の証拠にならない
  - replay    : 講師の実行記録 (.cache/llm.sqlite) だけで答える。記録に無い依頼は API を呼ばずに CacheMiss (費用 0)
  - anthropic : 本物の Claude (anthropic SDK の messages)。同じ依頼の記録があればそれを返す (費用 0)

どれも create(request) -> response を持つ。request は Messages API に渡す辞書 (model・system・tools・messages…)、
response は Messages API の応答を辞書にしたもの ({"content": [...], "stop_reason": ..., "usage": {...}})。
ホスト (common/host.py) は辞書しか見ないので、呼び先を替えてもホストの作りは変わらない。

  - 記録 : キーは request 全体 (JSON を並べ替えたもの) の SHA-256。API キーはキーにも記録にも入らない
  - 台帳 : 本当に API を呼んだときだけ _api_cost_ledger.jsonl に 1 行 (入出力トークン・費用・秒・tag)。
           記録から返したときは cached=true の行 (費用 0)。合計が LLM_BUDGET_USD に近づくと止まる
  - LLM_CACHE_ONLY=1 で記録だけ (replay と同じ)。LLM_CACHE=0 で記録を見ずに API を呼ぶ (記録は上書き)

🔴 API キーは画面にもファイルにも出さない。受講者は各自のキーを環境変数 ANTHROPIC_API_KEY に入れる。
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Callable, Sequence

from common.kit import ROOT

# MCP の SDK がログを INFO で出す設定にするので、API への通信 1 回ごとの行 (HTTP Request: POST …) が画面に混ざる。黙らせる
for _name in ("httpx", "anthropic"):
    logging.getLogger(_name).setLevel(logging.WARNING)

# 🔴 2026-10-18 ユーザー指示「使うモデルは Opus5.5 の高い推論でいい」→ 既定は claude-opus-5-5・effort high
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "claude-opus-5-5")
DEFAULT_EFFORT = os.environ.get("LLM_EFFORT", "high")
CACHE_PATH = os.environ.get("LLM_CACHE_PATH", os.path.join(ROOT, ".cache", "llm.sqlite"))
def _ledger() -> str:
    return os.environ.get("LLM_LEDGER", os.path.join(ROOT, "_api_cost_ledger.jsonl"))


BUDGET_USD = float(os.environ.get("LLM_BUDGET_USD", "200"))

# 公式単価 (USD / 100 万トークン、2026-10 時点): (入力, 出力, キャッシュ読み)。キャッシュ書きは入力の 1.25 倍
PRICES = {
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
}


class CacheMiss(RuntimeError):
    """記録だけで回す設定なのに、記録に無い依頼が来た (API は呼んでいない)。"""


class BudgetExceeded(RuntimeError):
    pass


# ---------------------------------------------------------------- tag (台帳でラボ・場面を分ける印)
_tag: contextvars.ContextVar[str] = contextvars.ContextVar("llm_tag", default="")


@contextmanager
def tag(name: str):
    """with tag("lab05/Q-901"): ... の中の呼び出しは台帳にその印で残る。"""
    tok = _tag.set(name)
    try:
        yield
    finally:
        _tag.reset(tok)


# ---------------------------------------------------------------- 費用と台帳
_lock = threading.Lock()


def price(model: str) -> tuple[float, float, float]:
    for k, v in PRICES.items():
        if model.startswith(k):
            return v
    return (5.0, 25.0, 0.5)


def cost_of(model: str, usage: dict | None) -> float:
    """Messages API の usage から費用 (USD)。input_tokens はキャッシュ分を含まない (langchain と違う)。"""
    u = usage or {}
    inp, out = int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0)
    cr, cw = int(u.get("cache_read_input_tokens") or 0), int(u.get("cache_creation_input_tokens") or 0)
    pin, pout, pcr = price(model)
    return (inp * pin + out * pout + cr * pcr + cw * pin * 1.25) / 1_000_000


def _record(entry: dict) -> None:
    entry = {"t": datetime.now().isoformat(timespec="seconds"), "tag": _tag.get(), **entry}
    with _lock:
        os.makedirs(os.path.dirname(_ledger()) or ".", exist_ok=True)
        with open(_ledger(), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _read_ledger() -> list[dict]:
    if not os.path.exists(_ledger()):
        return []
    rows = []
    with open(_ledger(), encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return rows


def spent() -> float:
    return sum(float(e.get("cost_usd", 0)) for e in _read_ledger())


def ledger_summary(since: str | None = None, tag_prefix: str | None = None) -> dict:
    """台帳の集計 (RUN_LOG 用)。since は 'YYYY-MM-DDTHH:MM:SS' 以上、tag_prefix は tag の前方一致。"""
    s = {"calls": 0, "cached_calls": 0, "cost_usd": 0.0, "in": 0, "out": 0, "seconds": 0.0}
    for e in _read_ledger():
        if since and e.get("t", "") < since:
            continue
        if tag_prefix and not str(e.get("tag", "")).startswith(tag_prefix):
            continue
        if e.get("cached"):
            s["cached_calls"] += 1
            continue
        s["calls"] += 1
        s["cost_usd"] += float(e.get("cost_usd", 0))
        s["in"] += int(e.get("in", 0))
        s["out"] += int(e.get("out", 0))
        s["seconds"] += float(e.get("seconds", 0))
    s["cost_usd"] = round(s["cost_usd"], 4)
    s["seconds"] = round(s["seconds"], 1)
    return s


# ---------------------------------------------------------------- 記録 (SQLite)
class Record:
    """request → response の記録。標準ライブラリの sqlite3 だけで動く。"""

    def __init__(self, path: str = CACHE_PATH):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS llm_record (k TEXT PRIMARY KEY, request TEXT, response TEXT, t TEXT)")
        self._db.commit()

    @staticmethod
    def key(request: dict) -> str:
        return hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def get(self, request: dict) -> dict | None:
        with self._lock:
            row = self._db.execute("SELECT response FROM llm_record WHERE k=?", (self.key(request),)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, request: dict, response: dict) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO llm_record VALUES (?,?,?,?)",
                             (self.key(request), json.dumps(request, ensure_ascii=False),
                              json.dumps(response, ensure_ascii=False), datetime.now().isoformat(timespec="seconds")))
            self._db.commit()

    def size(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM llm_record").fetchone()[0]


# ---------------------------------------------------------------- 本物 (Anthropic) と記録の再生
def _api_key() -> str | None:
    k = os.environ.get("ANTHROPIC_API_KEY")
    if k:
        return k
    if os.environ.get("LLM_NO_KEY") == "1":   # 自己検査用: キーを持たない人の手元を再現する
        return None
    if os.name == "nt":   # Windows: 起動中のシェルに無くてもユーザー環境変数から読む (表示しない)
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as h:
                return winreg.QueryValueEx(h, "ANTHROPIC_API_KEY")[0]
        except OSError:
            return None
    return None


class RecordedProvider:
    """記録にあれば記録から、無ければ (replay でなければ) API を呼んで記録する。"""

    name = "anthropic"

    def __init__(self, replay: bool = False, record: Record | None = None):
        self.replay = replay or os.environ.get("LLM_CACHE_ONLY", "0") == "1"
        self.use_record = os.environ.get("LLM_CACHE", "1") != "0"
        self.record = record or Record()
        self._client = None
        if self.replay:
            self.name = "replay"

    def _api(self):
        if self._client is None:
            from anthropic import Anthropic
            key = _api_key()
            if not key:
                raise RuntimeError("ANTHROPIC_API_KEY が見つかりません。provider=mock か replay を使ってください")
            self._client = Anthropic(api_key=key)   # キーは SDK に渡すだけ。表示しない
            del key
        return self._client

    def create(self, request: dict) -> dict:
        if self.use_record:
            hit = self.record.get(request)
            if hit is not None:
                _record({"provider": "anthropic", "model": request.get("model"), "cached": True, "cost_usd": 0})
                return hit
        if self.replay:
            raise CacheMiss("記録 (.cache/llm.sqlite) にこの依頼がありません。replay なので API は呼びません")
        if spent() + 0.25 >= BUDGET_USD:
            raise BudgetExceeded(f"予算 {BUDGET_USD} USD に近づいたので止めます (使用済み {spent():.2f} USD)")
        t0 = time.time()
        # 長い出力でも途中で切れないよう stream で受けて、最後に 1 つの応答にまとめる
        with self._api().messages.stream(**request) as s:
            msg = s.get_final_message()
        resp = msg.model_dump(mode="json", exclude_none=True)
        u = resp.get("usage", {})
        _record({"provider": "anthropic", "model": request.get("model"), "cached": False,
                 "in": u.get("input_tokens", 0), "out": u.get("output_tokens", 0),
                 "cost_usd": round(cost_of(request.get("model", ""), u), 6), "seconds": round(time.time() - t0, 2)})
        self.record.put(request, resp)
        return resp


def base_request(model: str | None = None, max_tokens: int = 16000) -> dict:
    """request の共通部分。Opus 5.5 は思考が常に入り、深さは output_config.effort で決める。"""
    m = model or DEFAULT_MODEL
    req = {"model": m, "max_tokens": max_tokens}
    if m.startswith("claude-opus-5-5") and DEFAULT_EFFORT:
        req["output_config"] = {"effort": DEFAULT_EFFORT}
    return req


# ---------------------------------------------------------------- 偽モデル (mock)
# plan(messages, 道具の名前) -> content ブロックの並び。ホストから見ると本物の応答と同じ形になる
Plan = Callable[[Sequence[dict], list[str]], list[dict]]


def say(text: str) -> dict:
    return {"type": "text", "text": text}


def use(name: str, args: dict, call_id: str) -> dict:
    return {"type": "tool_use", "id": call_id, "name": name, "input": args}


def default_plan(messages: Sequence[dict], tools: list[str]) -> list[dict]:
    return [say("（mock の応答です。キーを登録すると本物のモデルが答えます）")]


class MockProvider:
    """API を呼ばない偽モデル。🔴 答えは筋書きどおり。正答率・費用などの数字は性能の証拠にならない。"""

    name = "mock"

    def __init__(self, plan: Plan | None = None):
        self.plan = plan or default_plan
        self.requests: list[dict] = []    # 何を渡されたか (テストと講座で見せる)

    def create(self, request: dict) -> dict:
        self.requests.append(request)
        tools = [t["name"] for t in request.get("tools", [])]
        content = self.plan(request["messages"], tools)
        n_in = len(json.dumps(request, ensure_ascii=False)) // 4
        return {"type": "message", "role": "assistant", "model": "mock", "content": content,
                "stop_reason": "tool_use" if any(b["type"] == "tool_use" for b in content) else "end_turn",
                "usage": {"input_tokens": n_in, "output_tokens": len(json.dumps(content, ensure_ascii=False)) // 4}}


# ---------------------------------------------------------------- 入口
def provider_name(provider: str | None = None) -> str:
    return (provider or os.environ.get("LLM_PROVIDER") or "mock").lower()


def get_provider(provider: str | None = None, *, mock_plan: Plan | None = None):
    """mock / replay / anthropic (省略時は LLM_PROVIDER、無ければ mock)。"""
    p = provider_name(provider)
    if p == "mock":
        return MockProvider(mock_plan)
    if p in ("anthropic", "replay"):
        return RecordedProvider(replay=(p == "replay"))
    if p == "agent-sdk":                        # 講師の収録用 (プランのログインで呼ぶ)。common/sdk_provider.py
        from common.sdk_provider import AgentSDKProvider
        return AgentSDKProvider()
    raise ValueError(f"provider が不明です: {p} (mock / replay / anthropic / agent-sdk)")


# ---------------------------------------------------------------- mock の筋書きを書くための道具
def last_user_text(messages: Sequence[dict]) -> str:
    """最後の利用者の文 (tool_result だけの user は飛ばす)。"""
    for m in reversed(messages):
        if m["role"] != "user":
            continue
        c = m["content"]
        if isinstance(c, str):
            return c
        texts = [b["text"] for b in c if b.get("type") == "text"]
        if texts:
            return "\n".join(texts)
    return ""


def tool_results(messages: Sequence[dict]) -> list[dict]:
    """最後の利用者の文より後の tool_result (筋書きで「何を呼び終えたか」を見るのに使う)。
    各要素は {"tool_use_id", "name", "is_error", "text"}。"""
    names = {}
    out: list[dict] = []
    for m in messages:
        if isinstance(m["content"], str):
            if m["role"] == "user":
                out = []
            continue
        if m["role"] == "user" and any(b.get("type") == "text" for b in m["content"]):
            out = []
        for b in m["content"]:
            if b.get("type") == "tool_use":
                names[b["id"]] = b["name"]
            elif b.get("type") == "tool_result":
                txt = b["content"] if isinstance(b["content"], str) else "".join(x.get("text", "") for x in b["content"])
                out.append({"tool_use_id": b["tool_use_id"], "name": names.get(b["tool_use_id"]),
                            "is_error": bool(b.get("is_error")), "text": txt})
    return out
