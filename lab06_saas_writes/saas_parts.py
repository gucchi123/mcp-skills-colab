"""ラボ 6 の部品: 確認への答え方 (記録つき)・mock の筋書き・線の記録の読み方。

🔴 mock の筋書きは「モデルがこう動いたら」を決め打ちしたもの。性能の証拠にはならない。
"""
from __future__ import annotations

import json

import mcp.types as types

from common import llm as L


# ------------------------------------------------------------------ Client に渡す確認の答え方 (elicitation_callback)
class Answer:
    """確認 (elicitation) に決まった答えを返し、聞かれた文を覚えておく。

    action: accept (承認) / decline (断る) / cancel (閉じた)。ok は accept のときの中身 {"ok": ok}。
    """

    def __init__(self, action: str = "accept", ok: bool = True):
        self.action, self.ok = action, ok
        self.seen: list[str] = []

    async def __call__(self, ctx, params: types.ElicitRequestParams) -> types.ElicitResult:
        self.seen.append(params.message)
        if self.action == "accept":
            return types.ElicitResult(action="accept", content={"ok": self.ok})
        return types.ElicitResult(action=self.action)


# ------------------------------------------------------------------ Host に渡す承認役 (approver)
class Recorder:
    """Host の approver。聞かれた確認を覚えて、決めた答え (accept / decline) を返す。"""

    def __init__(self, action: str):
        self.action = action
        self.asked: list[dict] = []

    def __call__(self, req):
        self.asked.append({"tool": f"{req.server}.{req.tool}", "message": req.message})
        return ("accept", {"ok": True}) if self.action == "accept" else ("decline", None)


# ------------------------------------------------------------------ mock の筋書き (発注係)
def order_plan(messages, tool_names):
    """在庫を見る → 発注を登録する → 結果を伝える、の 3 手。"""
    done = L.tool_results(messages)
    if not done:
        return [L.say("在庫を確認します。"), L.use("mcp__inventory__get_stock", {"sku": "P-102"}, "m1")]
    if len(done) == 1:
        st = json.loads(done[0]["text"])
        return [L.say(f"在庫 {st['stock']:,} が発注点 {st['reorder_point']:,} 以下なので発注を登録します。"),
                L.use("mcp__inventory__create_purchase_order", {"sku": "P-102", "request_id": "O-01"}, "m2")]
    last = done[-1]
    if last["is_error"]:
        why = "確認で断られました" if "decline" in last["text"] else last["text"].split(": ", 1)[-1][:60]
        return [L.say(f"発注は登録していません ({why})。")]
    o = json.loads(last["text"])
    head = f"依頼 {o['request_id']} は登録済みでした" if o["duplicate"] else "発注を登録しました"
    return [L.say(f"{head}: {o['order_id']}・{o['qty']:,} 個・{o['amount_yen']:,} 円・{o['status']}"
                  + (f" ({o['approver']})" if o["approver"] else "") + "。")]


# ------------------------------------------------------------------ 線の記録を短く読む
def short(s: str, n: int = 24) -> str:
    return s if len(s) <= n else f"{s[:n]}…({len(s)} 文字)"


def describe(mark: str, msg: dict) -> str:
    """記録の 1 行 (JSON-RPC 1 通) を、画面で読める 1〜2 行にする。"""
    i = msg.get("id")
    if "method" in msg:
        p = dict(msg.get("params") or {})
        p.pop("_meta", None)
        s = f"{mark} id={i} {msg['method']}"
        if msg["method"] == "tools/call":
            s += f" {p.get('name')} {json.dumps(p.get('arguments'), ensure_ascii=False)}"
            if "inputResponses" in p:
                s += f"\n      inputResponses={json.dumps(p['inputResponses'], ensure_ascii=False)}"
                s += f"\n      requestState={short(p.get('requestState') or '')} (受け取ったものをそのまま返す)"
            else:
                s += "  (inputResponses なし)"
        return s
    if "error" in msg:
        return f"{mark} id={i} error {msg['error'].get('code')} {msg['error'].get('message')} {msg['error'].get('data', '')}"
    r = msg.get("result", {})
    rt = r.get("resultType")
    if rt == "input_required":
        lines = [f"{mark} id={i} resultType=input_required (まだ終わっていない。入力が要る)"]
        for k, q in r.get("inputRequests", {}).items():
            lines.append(f"      inputRequests[\"{k}\"]: {q['method']} 「{q['params'].get('message')}」")
            lines.append(f"      requestedSchema={json.dumps(q['params'].get('requestedSchema', {}).get('properties'), ensure_ascii=False)}")
        lines.append(f"      requestState={short(r.get('requestState') or '')} (サーバが中身を封じた札)")
        return "\n".join(lines)
    if "structuredContent" in r:
        return f"{mark} id={i} resultType={rt} isError={r.get('isError')} structuredContent={json.dumps(r['structuredContent'], ensure_ascii=False)}"
    if "tools" in r:
        return f"{mark} id={i} resultType={rt} 道具 {len(r['tools'])} 個 ({', '.join(t['name'] for t in r['tools'])})"
    if "supportedVersions" in r:
        return f"{mark} id={i} resultType={rt} supportedVersions={r['supportedVersions']} capabilities={list(r.get('capabilities', {}))}"
    return f"{mark} id={i} result {short(json.dumps(r, ensure_ascii=False), 120)}"
