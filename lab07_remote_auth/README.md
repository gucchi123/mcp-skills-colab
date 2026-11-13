# ラボ 7 リモート化と認可 ― トークンで利用者を決める

> データはすべて架空 (ソラハ電機)。Claude は呼びません (API キー不要)。

顧客台帳のサーバ (`servers/http_crm.py`) を Streamable HTTP で子プロセスに立て、トークンを変えて当てます。
stdio では「起動した人 = 利用者」でしたが、HTTP では一つのサーバを大勢が使うので、**要求ごとにトークンで利用者を決めます**。

```
python run_remote_auth.py                                      # 場面を全部 (サーバを 1 つ立てて最後に止める)
python run_remote_auth.py --only noauth,prm                    # トークン無しの 401 と保護リソースのメタデータ
python run_remote_auth.py --only tokens                        # 401 / 403 / 200 の表
python run_remote_auth.py --only users --users U-01,U-02,U-05  # 同じ get_customer をトークンの持ち主ごとに
python run_remote_auth.py --only envuser,decode                # サーバの SOLAHA_USER は効かない・トークンの中身
```

| 場面 | 見ること |
|---|---|
| noauth | トークン無し → 401 と `WWW-Authenticate: Bearer error="invalid_token", ..., resource_metadata="…"` |
| prm | `/.well-known/oauth-protected-resource/mcp` (リソースのパスを後ろに足した場所) の中身 (RFC 9728) |
| tokens | 形違い・署名の書き換え・宛先違い・期限切れ → 401、範囲不足 → 403、名簿に無い利用者 → HTTP は通り道具が断る |
| users | `Host(mode="http", urls=..., tokens=...)` で同じ `get_customer` を呼ぶと、持ち主ごとに見える項目が変わる |
| envuser | サーバを `SOLAHA_USER=U-04` (部長) で起動しても、U-01 のトークンなら U-01 の見え方。監査ログも U-01 |
| decode | トークン `v1.<中身>.<署名>` の中身 (sub・aud・scope・exp・iss)。中身は鍵なしで読める |

## 鍵とトークンの扱い

- 署名の鍵 `SOLAHA_DEMO_AUTH_KEY` は、実行ごとにこのプロセスで乱数から作り、子プロセスのサーバに環境変数で渡します。**表示しません**。終わったら元に戻します。
- トークンは短い期限 (10 分) の講座用ですが、画面には先頭 12 文字だけ出します。
- サーバの 401 は理由を返しません (`Authentication required` だけ)。表の「検証役の理由」は、同じ `DemoVerifier` を手元で回した結果です。

## demo_auth は本物の OAuth 2.1 ではない

`common/demo_auth.py` は、MCP サーバが確かめること (① 署名 ② 期限 ③ 宛先 aud ④ 範囲 scope) の順を見せるための見本です。
トークンを出す「認可サーバ」の役は、手元の関数 `issue()` が利用者のログインも同意も無しにやっています。本物の IdP (社内の認可サーバ) は次を足します。

- **ログインと同意**: 利用者本人が IdP でログインし、どのアプリ (クライアント) にどの範囲を渡すかに同意する。トークンを出すのはその後だけ
- **CIMD (Client ID Metadata Document)**: クライアント (MCP のホスト) が自分の情報を HTTPS の URL に置き、その URL を client_id として使う。
  IdP は URL の中身 (名前・戻り先 URL) を読んでクライアントを確かめる。事前の登録なしで、知らないホストを見分けられる
- **PKCE**: 認可コードを途中で盗まれても使えないように、ホストが作った秘密の値 (code_verifier) のハッシュを最初に送り、交換のときに本体を見せる
- **RFC 8707 の resource indicator**: ホストが「どのサーバ宛てのトークンか」(`resource=https://…/mcp`) を IdP に伝え、IdP はその宛先 (aud) に縛ったトークンを出す。
  別の MCP サーバ宛てのトークンを使い回せない (このラボの「宛先が別のサーバ」の 401 がそれ)
- そのほか: 公開鍵の署名 (JWT と JWKS。サーバは鍵を共有しない)・リフレッシュトークン・失効・発行者のメタデータ (`/.well-known/oauth-authorization-server`)

このラボのサーバは「トークンを確かめる側」(リソースサーバ) だけです。保護リソースのメタデータの `authorization_servers` にある
`https://auth.solaha.example` は架空の発行者で、実際には存在しません。

## 注意

- サーバは空いているポートに立て、場面が終わると必ず止めます (ノートブックのセルも 1 つずつ立てて止める)。
- 試験: `python -m pytest -q lab07_remote_auth/tests` (キットの根で・`PYTHONUTF8=1`。サーバを 1 回立てる)
- 実際の出力と、mcp 2.3.0 で気づいたことは `RUN_LOG.md`。
