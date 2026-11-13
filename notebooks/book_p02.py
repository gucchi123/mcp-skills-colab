from build_notebooks import C, M, nb

BOOKS = {}

BOOKS["p02_protocol.ipynb"] = nb("P02 MCP の仕組み ― 電文を自分の手で送る", "社内規程のサーバに、ホストが送るのと同じ JSON-RPC を自分で書いて送り、返事をそのまま見ます。版は 2026-07-28 (initialize の握手もセッション ID もありません)。", [
    (M, "## 1. stdio で 1 行 1 通の JSON を送る\nサーバを子プロセスで立て、server/discover → tools/list → tools/call → 資料 → 定型文 の順に送ります。どの要求も `params._meta` に版・名乗り・できることを持ちます。返事は画面用に縮めています。"),
    (C, '''from run_protocol import amain as protocol
with safe():
    r = await protocol(["--part", "stdio"])'''),
    (M, "## 2. 旧来の initialize を送ると\n1 本の接続の「時代」は最初の 1 通で決まります。initialize で始めると古い版 (2025-11-25) になり、2026-07-28 の接続では initialize が断られます。"),
    (C, '''with safe():
    r = await protocol(["--part", "legacy"])'''),
    (M, "## 3. Streamable HTTP で送る\n同じサーバを `127.0.0.1` の空きポートで立て、POST にヘッダー (MCP-Protocol-Version・Mcp-Method・Mcp-Name) を付けます。`ttlMs`・`cacheScope` はキャッシュの目安です。最後に `Client(url)` が実際に送った POST を数えます。"),
    (C, '''with safe():
    r = await protocol(["--part", "http"])'''),
    (M, "## 4. 同じことを Client(kb.mcp) で\n同じプロセスでつなぎます (子プロセスもポートも無し)。受け取る tools/list は、上で生で受け取ったものと同じ中身です。"),
    (C, '''with safe():
    r = await protocol(["--part", "client"])'''),
], llm=False)
