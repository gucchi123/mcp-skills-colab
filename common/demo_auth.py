"""講座用の「小さな認可サーバ」と、MCP サーバ側のトークン検証 (第 7 部)。

🔴 これは仕組みを見せるための見本で、本番の OAuth 2.1 の認可サーバではない。
   本番では、社内の認可サーバ (IdP) が利用者のログインと同意を経てトークンを出し、MCP サーバは
   ① 署名 ② 期限 ③ 宛先 (aud = このサーバの URL。RFC 8707 の resource) ④ 範囲 (scope) を確かめる。
   ここでは ①〜③ をこの検証役が確かめ、④ 範囲は SDK の認可の仕組み (AuthSettings の required_scopes) が確かめる
   (検証役は持っている範囲を AccessToken.scopes に入れて返すだけ。足りなければ SDK が 403 を返す)。署名は HMAC-SHA256、鍵は環境変数 SOLAHA_DEMO_AUTH_KEY (無ければ起動ごとに作る)。

トークンの形: v1.<中身を base64url>.<署名を base64url>
  中身: {"sub": 社員番号, "aud": 宛先の URL, "scope": "crm.read ...", "exp": 期限 (UNIX 秒), "iss": 発行者}
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from mcp.server.auth.provider import AccessToken

ISSUER = "https://auth.solaha.example"
CLIENT_ID = "solaha-demo-host"


def _key() -> bytes:
    k = os.environ.get("SOLAHA_DEMO_AUTH_KEY")
    if not k:
        k = secrets.token_hex(32)
        os.environ["SOLAHA_DEMO_AUTH_KEY"] = k        # 子プロセス (HTTP サーバ) にも同じ鍵を渡すため
    return k.encode()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue(user_id: str, audience: str, scopes: list[str], ttl: int = 600) -> str:
    """認可サーバの役: 利用者に、ある MCP サーバ宛てのトークンを出す。"""
    body = _b64(json.dumps({"sub": user_id, "aud": audience, "scope": " ".join(scopes),
                            "exp": int(time.time()) + ttl, "iss": ISSUER}).encode())
    sig = _b64(hmac.new(_key(), body.encode(), hashlib.sha256).digest())
    return f"v1.{body}.{sig}"


class DemoVerifier:
    """MCP サーバの役: 受け取ったトークンを確かめる (TokenVerifier の約束どおり、だめなら None)。"""

    def __init__(self, audience: str):
        self.audience = audience
        self.rejected: list[str] = []         # 断った理由 (講座で見せる)

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            ver, body, sig = token.split(".")
        except ValueError:
            self.rejected.append("形が違う"); return None
        want = _b64(hmac.new(_key(), body.encode(), hashlib.sha256).digest())
        if ver != "v1" or not hmac.compare_digest(sig, want):
            self.rejected.append("署名が合わない"); return None
        c = json.loads(_unb64(body))
        if c["exp"] < time.time():
            self.rejected.append("期限切れ"); return None
        if c["iss"] != ISSUER:
            self.rejected.append("発行者が違う"); return None
        if c["aud"] != self.audience:
            self.rejected.append(f"宛先が違う ({c['aud']})"); return None
        return AccessToken(token=token, client_id=CLIENT_ID, scopes=c["scope"].split(), expires_at=c["exp"],
                           resource=c["aud"], subject=c["sub"], claims=c)
