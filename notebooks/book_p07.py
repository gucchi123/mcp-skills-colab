from build_notebooks import C, M, nb

BOOKS = {}

BOOKS["p07_remote_auth.ipynb"] = nb("P07 リモート化と認可 ― トークンで利用者を決める", "顧客台帳のサーバを HTTP で立て、トークンの有無・署名・宛先・期限・範囲で 401 / 403 / 200 がどう変わるか、トークンの持ち主ごとに見える項目がどう変わるかを確かめます。各セルはサーバを子プロセスで立て、終わると止めます。", [
    (M, "## 1. トークン無しの 401 と、保護リソースのメタデータ\n401 の `WWW-Authenticate` が指す URL を開くと、どの認可サーバからどの範囲のトークンをもらえばよいかが書いてあります。"),
    (C, '''from run_remote_auth import amain as remote
with safe():
    r = await remote(["--only", "noauth,prm"])'''),
    (M, "## 2. トークンを変えて当てる\n署名の書き換え・宛先違い・期限切れ・範囲不足・知らない利用者・正しいトークン。🔴 署名の鍵は表示しません。トークンも先頭 12 文字だけ出します。"),
    (C, '''with safe():
    r = await remote(["--only", "tokens"])'''),
    (M, "## 3. 同じ道具を、トークンの持ち主ごとに\nホストは `Host(mode='http', urls=..., tokens=...)` でつなぎます。利用者を決めるのはトークンだけです。サーバの環境変数 `SOLAHA_USER=U-04` (部長) は効きません。"),
    (C, '''with safe():
    r = await remote(["--only", "users,envuser", "--users", "U-01,U-02,U-05"])'''),
    (M, "## 4. トークンの中身\n講座のトークンは `v1.<中身>.<署名>` の形です。中身は鍵なしで読めます (秘密ではない)。書き換えると署名が合いません。"),
    (C, '''with safe():
    r = await remote(["--only", "decode"])'''),
])
