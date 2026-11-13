"""顧客台帳のサーバを、ネットワーク越し (Streamable HTTP) に、トークンつきで公開する (第 7 部)。

stdio では「起動した人 = 利用者」だった。HTTP では一つのサーバを大勢が使うので、要求ごとにトークンで利用者を決める。
  - トークンが無い・署名が違う・期限切れ・宛先 (aud) が別のサーバ → 401 で断る (道具まで届かない)
  - 範囲 (scope) に crm.read が無い → 403 で断る
  - 通れば、トークンの subject が利用者になり、common/policy.py の出し分けがそのまま効く

起動: python -m servers.http_crm [--port 8770]
トークン: python -c "from common.demo_auth import issue; print(issue('U-02', 'http://127.0.0.1:8770/mcp', ['crm.read']))"
          (サーバと同じ SOLAHA_DEMO_AUTH_KEY を環境変数で渡すこと)
"""
from __future__ import annotations

import argparse

from mcp.server.auth.settings import AuthSettings

from common.demo_auth import ISSUER, DemoVerifier
from common.kit import utf8_console
from servers.crm import build

SCOPE = "crm.read"


def url_for(port: int) -> str:
    return f"http://127.0.0.1:{port}/mcp"


def make(port: int):
    """(サーバ, 検証役) を返す。"""
    verifier = DemoVerifier(audience=url_for(port))
    srv = build(token_verifier=verifier,
                auth=AuthSettings(issuer_url=ISSUER, resource_server_url=url_for(port),
                                  validate_token_resource=True, required_scopes=[SCOPE]))
    return srv, verifier


if __name__ == "__main__":
    utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8770)
    a = ap.parse_args()
    srv, _ = make(a.port)
    srv.run("streamable-http", host="127.0.0.1", port=a.port)
