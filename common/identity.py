"""だれが道具を呼んでいるか (利用者) と、監査ログ。

🔴 利用者はモデルに引数で名乗らせない。モデルが「私は部長です」と書けば部長になってしまう。
   stdio のサーバは、ホストが起動するときに環境変数 SOLAHA_USER で渡す (起動した人 = 利用者)。
   HTTP のサーバ (第 7 部) は、アクセストークンから利用者を決める。どちらもこの set_user / current_user を通す。
"""
from __future__ import annotations

import contextvars
import datetime as dt
import os

from common.kit import append_jsonl, data_path, read_json, state_dir

_STAFF = {s["id"]: s for s in read_json(data_path("crm", "staff.json"))}
_user: contextvars.ContextVar[str | None] = contextvars.ContextVar("solaha_user", default=None)


class NotAllowed(Exception):
    """利用者が決まらない・知らない利用者のとき。"""


def set_user(user_id: str | None):
    """この要求の利用者を決める (HTTP の認可やテストから呼ぶ)。戻り値は contextvars の token。"""
    return _user.set(user_id)


def current_user() -> dict:
    """利用者を決める順: ① HTTP のアクセストークンの subject ② set_user ③ 環境変数 SOLAHA_USER (stdio)。
    トークンで呼ばれたときは ② ③ を見ない (トークンの持ち主以外にはなれない)。"""
    from mcp.server.auth.middleware.auth_context import get_access_token
    tok = get_access_token()
    if tok is not None:
        uid = tok.subject
        if uid not in _STAFF:
            raise NotAllowed(f"知らない利用者のトークンです: {uid}")
        return _STAFF[uid]
    uid = _user.get() or os.environ.get("SOLAHA_USER")
    if not uid:
        raise NotAllowed("利用者が決まっていません (SOLAHA_USER が空)")
    if uid not in _STAFF:
        raise NotAllowed(f"知らない利用者です: {uid}")
    return _STAFF[uid]


def staff(user_id: str) -> dict:
    return _STAFF[user_id]


def audit(server: str, tool: str, **detail) -> None:
    """監査ログに 1 行足す (state/audit.jsonl)。だれが・いつ・どの道具で・何を見たか/何を隠したか/何をしたか。"""
    try:
        u = current_user()["id"]
    except NotAllowed:
        u = None
    append_jsonl(os.path.join(state_dir(), "audit.jsonl"), [{
        "at": dt.datetime.now().isoformat(timespec="seconds"), "user": u, "server": server, "tool": tool, **detail}])


def audit_confirm_requested(server: str, tool: str, request_id: str, **detail) -> None:
    """「確認を求めた」を監査ログに残す (確認の関数 ask_confirm から呼ぶ)。
    🔴 2026-07-28 版の確認は 2 往復 (入力の要求 → 答えを付けて送り直し) で、確認の関数はその両方で呼ばれる。
       直前の行が同じ依頼の「確認を求めた」なら、送り直しの分なので書かない。"""
    p = os.path.join(state_dir(), "audit.jsonl")
    if os.path.exists(p):
        with open(p, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 4096))
            tail = f.read().decode("utf-8", errors="ignore").strip().splitlines()
        if tail:
            import json
            try:
                last = json.loads(tail[-1])
            except ValueError:
                last = {}
            if (last.get("server"), last.get("tool"), last.get("request_id"), last.get("confirm_requested")) ==                     (server, tool, request_id, True):
                return
    audit(server, tool, request_id=request_id, confirm_requested=True, **detail)
