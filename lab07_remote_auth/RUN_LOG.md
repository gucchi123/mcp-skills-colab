# RUN_LOG ラボ 7

- 記録日: 2026-10-24 / Python 3.13.14 / mcp 2.3.0 (プロトコル 2026-07-28) / Windows 11
- Claude は呼んでいない (このラボは LLM を使わない。servers/http_crm.py を子プロセスで空いているポートに立て、最後に止めた。署名の鍵は実行ごとに作り、表示していない)
- 環境変数: `PYTHONUTF8=1`・`LLM_NO_KEY=1`・`ANTHROPIC_API_KEY=` (空)。キットの根で実行
- 書き込み先は実行ごとの一時フォルダ (キットの state/ は使っていない)

## `python lab07_remote_auth/run_remote_auth.py --users U-01,U-02,U-05 --name teacher`

```text
[サーバ] servers/http_crm.py を http://127.0.0.1:49348/mcp に起動 (子プロセス・SOLAHA_USER=U-04・鍵は表示しない)

■ 1. トークン無しで tools/list を POST
  HTTP 401
  WWW-Authenticate: Bearer error="invalid_token", error_description="Authentication required", resource_metadata="http://127.0.0.1:49348/.well-known/oauth-protected-resource/mcp"
  本文: {"error": "invalid_token", "error_description": "Authentication required"}
  → resource_metadata= の URL を見れば、どの認可サーバからトークンをもらえばよいかが分かる (次の場面)

■ 2. 保護リソースのメタデータ (401 の resource_metadata が指す URL)
  GET /.well-known/oauth-protected-resource/mcp → 200
      resource: http://127.0.0.1:49348/mcp
      authorization_servers: ['https://auth.solaha.example']
      scopes_supported: ['crm.read']
      bearer_methods_supported: ['header']
  GET /.well-known/oauth-protected-resource → 404
  GET /.well-known/oauth-authorization-server → 404
  → メタデータはリソースのパス (/mcp) を後ろに足した場所にある (SDK が置く)。認可サーバのメタデータは
    このサーバには無い (この MCP サーバはトークンを確かめる側だけ。発行者 auth.solaha.example は架空)

■ 3. トークンを変えて tools/list と get_customer C-002 を当てる
  場合                    トークン        HTTP  error              検証役の理由 ※           get_customer
  トークン無し            (なし)          401   invalid_token      -                         -
  形が違う (ただの文字)   hello           401   invalid_token      形が違う                  -
  署名を書き換えた        v1.eyJzdWIiO…  401   invalid_token      署名が合わない            -
  宛先が別のサーバ        v1.eyJzdWIiO…  401   invalid_token      宛先が違う (:1/mcp)       -
  期限切れ (5 秒前)       v1.eyJzdWIiO…  401   invalid_token      期限切れ                  -
  範囲が inventory.read   v1.eyJzdWIiO…  403   insufficient_scope 通る U-02 inventory.read  -
  知らない利用者 U-99     v1.eyJzdWIiO…  200   -                  通る U-99 crm.read        ✗ 知らない利用者のトークンです: U-99
  U-01 crm.read           v1.eyJzdWIiO…  200   -                  通る U-01 crm.read        ✓ 隠した 5 項目
  U-02 crm.read           v1.eyJzdWIiO…  200   -                  通る U-02 crm.read        ✓ 隠した 0 項目
  403 の WWW-Authenticate: Bearer error="insufficient_scope", error_description="Required scope: crm.read"
  ※ サーバと同じ検証のコード (DemoVerifier) を手元で回した結果
  → 401 は「だれか分からない」、403 は「分かったが範囲が足りない」。どちらも道具まで届かない
    サーバの 401 は理由を返さない (Authentication required だけ)。理由はサーバの中の検証役にしか無いので、
    ここでは同じ検証のコードを手元で回して見せている (攻撃する側に手がかりを渡さないのは正しい作り)

■ 4. Host(mode="http") で get_customer C-002 を呼ぶ。利用者はトークンだけで決まる  〇=見える －=（非表示）
  トークンの持ち主      会社名 ランク 与信枠 担当者 電話 メール 隠した数
  U-01 山根(営業一般)   〇     －     －     －     －   －     5
  U-02 石黒(営業課長)   〇     〇     〇     〇     〇   〇     0
  U-05 坂口(窓口)       〇     －     －     〇     〇   －     3
  → Host には user を渡していない (user=None)。HTTP では「起動した人」ではなく「トークンの持ち主」が利用者

■ 5. サーバは環境変数 SOLAHA_USER=U-04 (田村 浩二・部長) で起動してある
  U-01 のトークンで get_customer C-002 → 隠した項目 ['rank', 'credit_limit_yen', 'contact.name', 'contact.phone', 'contact.email']
  (部長として扱われていれば、隠す項目は 0 のはず)
  サーバの監査ログ (最後の行): user=U-01 tool=get_customer customer=C-002 / この実行で 6 行・利用者 ['U-01', 'U-02', 'U-05']
  → common/identity.py はトークンがあればトークンの subject だけを見る (環境変数・set_user は見ない)

■ 6. トークンの中身 (講座の形 v1.<中身>.<署名>。JWT ではない)
  トークン: v1.eyJzdWIiO… (全 221 文字・画面には先頭 12 文字だけ)
  v1 / 中身 174 文字 (base64url) / 署名 43 文字 (HMAC-SHA256。鍵は表示しない)
    sub  : U-02
    aud  : http://127.0.0.1:49348/mcp
    scope: crm.read
    iss  : https://auth.solaha.example
    exp  : 1792837461 (あと 600 秒)
  → 中身は鍵なしで読める (秘密ではない)。書き換えると署名が合わず 401。鍵を持つのは発行者とサーバだけ

[サーバ] 止めました
```

トークンは画面に先頭 12 文字だけ出している (どれも `{"sub":` で始まるので先頭は同じ形になる)。ポート番号は実行ごとに変わる。

## 読み取れること

- トークン無し・形違い・署名の書き換え・宛先違い・期限切れは 401 (`error="invalid_token"`)、範囲不足は 403 (`error="insufficient_scope"`)
- 401 の `WWW-Authenticate` は `resource_metadata="http://127.0.0.1:<port>/.well-known/oauth-protected-resource/mcp"` を指す (RFC 9728)。
  `/.well-known/oauth-protected-resource` (パス無し) と `/.well-known/oauth-authorization-server` は 404
- 署名が正しく範囲も足りるが社員名簿に無い U-99 は、HTTP は 200 で通り、道具 (get_customer) が「知らない利用者」で断る
- 同じ get_customer C-002 で、U-01 は 5 項目、U-05 (窓口) は 3 項目が非表示、U-02 (担当の課長) は 0 項目
- サーバの環境変数 SOLAHA_USER=U-04 (部長) は効かない。監査ログの利用者もトークンの持ち主だけ

## mcp 2.3.0 で気づいたこと (実際に回して確かめた)

- 401 の本文と見出しは、どの理由でも `Authentication required` だけ。断った理由はサーバの中の検証役にしか無い
  (ラボでは同じ DemoVerifier を手元で回して理由を見せている)
- 範囲 (scope) の確かめは SDK のミドルウェアがする。検証役が通したトークンでも、required_scopes に無ければ 403
- `AuthSettings(validate_token_resource=True)` で、SDK も AccessToken.resource が resource_server_url と同じかを確かめる
  (このラボの宛先違いは、それより先に DemoVerifier が aud で断っている)。未指定だと警告が出て、3.0 で既定が True になる予定
