# RUN_LOG ラボ 2

記録日 2026-10-24 / Python 3.13.14 / mcp 2.3.0 / Windows 11・キットの根で `PYTHONUTF8=1` / Claude は呼んでいない (API キー不要)

下は `python lab02_protocol/run_protocol.py --part <名前>` を 1 つずつ回した出力そのもの (縮めているのはプログラムの表示の縮め方だけ)。
HTTP のポートは毎回変わるので、画面では `<空きポート>` と出している。

## 読み取れること

- stdio: 6 往復とも initialize なし・セッション ID なしで通る。どの要求も `params._meta` に版・名乗り・できることを持つ
- `tools/list` は `ttlMs=300000 cacheScope=public` (kb.py の cache_hints)。何も指定していない `server/discover`・`resources/read`・`prompts/list` は `ttlMs=0 cacheScope=private`
- 🔴 mcp 2.3.0 のサーバは新旧どちらも話せる。1 本の接続の「時代」は最初の 1 通で決まる
  - 最初に initialize → 2026-07-28 を頼んでも `protocolVersion: 2025-11-25` で答える。その接続に 2026-07-28 の封筒を送ると `-32600`
  - 先に 2026-07-28 の要求 → 後から initialize は `-32022` (data に supported / requested)
  - 2026-07-28 の接続で `_meta` を付け忘れると `-32602`
- HTTP: 2026-07-28 の POST は `application/json` で返り、`mcp-session-id` は付かない。旧来の initialize だけ `text/event-stream` と `mcp-session-id` が付く
- HTTP: `Mcp-Name` とボディの name が食い違うと `400 / -32020`
- `Client(url)` はつないだ時点で `server/discover` を 1 通送る。`list_tools` の 2 回目は POST 0 通 (ttl のあいだ手元の写し)、`cache_mode="bypass"` で 1 通
- `Client(kb.mcp)` の `list_tools()` は stdio で生で受け取った tools/list と同じ中身

## 出力

```
$ python lab02_protocol/run_protocol.py --part stdio
■ stdio: python -m servers.kb を子プロセスで起動 (利用者 U-05)。標準入出力に 1 行 1 通の JSON
  → {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientInfo": {"name": "lab02-raw", "version": "0.1"}, "io.modelcontextprotocol/clientCapabilities": {}}}}
  ← {"jsonrpc": "2.0", "id": 1, "result": {"cacheScope": "private", "capabilities": {"prompts": {"listChanged": true}, "resources": {"listChanged": true, "subscribe": true}, "tools": {"listChanged": true}}, "instructions": "ソラハ電機 (架空) の社内規程・手続きを探して読むサーバ。答えるときは文書番号…(全53字)", "resultType": "complete", "supportedVersions": ["2026-07-28"], "ttlMs": 0, "_meta": {"io.modelcontextprotocol/serverInfo": {"name": "kb", "version": ""}}}}
  → {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {"_meta": "…(上と同じ _meta)"}}
  ← {"jsonrpc": "2.0", "id": 2, "result": {"cacheScope": "public", "resultType": "complete", "tools": [{"annotations": "{…}", "description": "社内規程・手続き (組織・職務権限・代理者・経費精算・出張・IT 機器・ソフトウ…(全114字)", "inputSchema": "{…}", "name": "search_regulations", "outputSchema": "{…}", "title": "規程を探す"}, {"annotations": "{…}", "description": "文書番号 (a-01〜a-13) の規程・手続きの全文を返す。番号が分からなけれ…(全67字)", "inputSchema": "{…}", "name": "get_regulation", "outputSchema": "{…}", "title": "規程の全文"}], "ttlMs": 300000, "_meta": {"io.modelcontextprotocol/serverInfo": {"name": "kb", "version": ""}}}}
  → {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "search_regulations", "arguments": {"query": "出張の日当", "top_k": 1}, "_meta": "…(上と同じ _meta)"}}
  ← {"jsonrpc": "2.0", "id": 3, "result": {"content": [{"text": "{⏎  \"doc_id\": \"a-06\",⏎  \"title\": \"出張申請手続…(全467字)", "type": "text"}], "isError": false, "resultType": "complete", "structuredContent": {"result": ["{…}"]}, "_meta": {"io.modelcontextprotocol/serverInfo": {"name": "kb", "version": ""}}}}
  → {"jsonrpc": "2.0", "id": 4, "method": "resources/templates/list", "params": {"_meta": "…(上と同じ _meta)"}}
  ← {"jsonrpc": "2.0", "id": 4, "result": {"cacheScope": "private", "resourceTemplates": [{"description": "規程 1 本の全文 (資料として読む)。", "mimeType": "text/markdown", "name": "regulation", "title": "社内規程", "uriTemplate": "kb://regulations/{doc_id}"}], "resultType": "complete", "ttlMs": 0, "_meta": {"io.modelcontextprotocol/serverInfo": {"name": "kb", "version": ""}}}}
  → {"jsonrpc": "2.0", "id": 5, "method": "resources/read", "params": {"uri": "kb://regulations/a-01", "_meta": "…(上と同じ _meta)"}}
  ← {"jsonrpc": "2.0", "id": 5, "result": {"cacheScope": "private", "contents": [{"mimeType": "text/markdown", "text": "# 組織規程⏎⏎## 第1章 総則⏎⏎**第1条（目的）**⏎この規程は、ソラハ…(全716字)", "uri": "kb://regulations/a-01"}], "resultType": "complete", "ttlMs": 0, "_meta": {"io.modelcontextprotocol/serverInfo": {"name": "kb", "version": ""}}}}
  → {"jsonrpc": "2.0", "id": 6, "method": "prompts/list", "params": {"_meta": "…(上と同じ _meta)"}}
  ← {"jsonrpc": "2.0", "id": 6, "result": {"cacheScope": "private", "prompts": [{"arguments": ["{…}"], "description": "", "name": "answer_with_citation", "title": "規程に基づいて答える"}], "resultType": "complete", "ttlMs": 0, "_meta": {"io.modelcontextprotocol/serverInfo": {"name": "kb", "version": ""}}}}
→ 6 往復。initialize なし・セッション ID なし。tools/list は ttlMs=300000 cacheScope=public (この間は使い回してよい、という目安)

$ python lab02_protocol/run_protocol.py --part legacy
■ 旧来の initialize を送ると (stdio。1 通り目ごとに新しい子プロセス)
[1] つないで最初に initialize (欲しい版 = 2026-07-28 と書いても)
  → {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2026-07-28", "capabilities": {}, "clientInfo": {"name": "old-client", "version": "1"}}}
  ← {"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {"prompts": {"listChanged": false}, "resources": {"listChanged": false, "subscribe": false}, "tools": {"listChanged": false}}, "instructions": "ソラハ電機 (架空) の社内規程・手続きを探して読むサーバ。答えるときは文書番号…(全53字)", "protocolVersion": "2025-11-25", "serverInfo": {"name": "kb", "version": ""}}}
   → 返ってきた版は 2025-11-25 (古い版の握手として扱われる)
   続けて 2026-07-28 の封筒 (_meta) で tools/list を送ると
  → {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {"_meta": "…(上と同じ _meta)"}}
  ← error -32600: this connection serves the handshake protocol era; requests carrying the 2026-07-28 envelope are not accepted on it
[2] 先に 2026-07-28 の要求 (tools/list) → 後から initialize
  → {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": "…(上と同じ _meta)"}}
  ← result (tools 2 個)
  → {"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "old-client", "version": "1"}}}
  ← error -32022: connection is serving the 2026-07-28 protocol; the initialize handshake is not accepted  data={"supported": ["2026-07-28"], "requested": "2025-11-25"}
[3] 2026-07-28 の接続 (先に server/discover を 1 通送ってある) で、_meta を付け忘れた tools/list
  → {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
  ← error -32602: params._meta must be an object carrying the required 'io.modelcontextprotocol/protocolVersion' and 'io.modelcontextprotocol/clientCapabilities' envelope keys
→ 1 本の接続の「時代」は最初の 1 通で決まる。2026-07-28 の接続では initialize は断られ、毎回の _meta が要る

$ python lab02_protocol/run_protocol.py --part http
■ Streamable HTTP: http_kb.py を子プロセスで起動 → http://127.0.0.1:<空きポート>/mcp
[1 tools/list] POST  ヘッダー: MCP-Protocol-Version: 2026-07-28 / Mcp-Method: tools/list
  ← 200  content-type=application/json / mcp-session-id: なし
  ← tools=['search_regulations', 'get_regulation']  ttlMs=300000  cacheScope=public
[2 tools/call] POST  ヘッダー: MCP-Protocol-Version: 2026-07-28 / Mcp-Method: tools/call / Mcp-Name: search_regulations
  ← 200  content-type=application/json / mcp-session-id: なし
  ← structuredContent: a-06 出張申請手続き / 3. 出張申請
[3 名前の食い違い] POST  ヘッダー: MCP-Protocol-Version: 2026-07-28 / Mcp-Method: tools/call / Mcp-Name: get_regulation
  ← 400  content-type=application/json / mcp-session-id: なし
  ← error -32020: mcp-name header does not match the request body's 'name' parameter  (ヘッダーはボディの写し。食い違いは門前で断る)
[4] 旧来の POST initialize (版のヘッダーなし)
  ← 200  content-type=text/event-stream / mcp-session-id: 253120a2…  (古い方式の互換。2026-07-28 では使わない)
■ 同じサーバに mcp の Client(url) でつなぐ (SDK が送った POST を数える)
  protocol=2026-07-28 server=kb  ← つないだ時点の POST: server/discover
  list_tools 1 回目 → POST 1 通  ttl_ms=300000 cache_scope=public
  list_tools 2 回目 → POST 0 通  (ttl のあいだは手元の写しを使う)
  list_tools(cache_mode='bypass') → POST 1 通
  call_tool → POST 1 通 (Mcp-Method=tools/call Mcp-Name=search_regulations)  is_error=False
→ HTTP でも 1 要求 = 1 POST で完結。返事は application/json、mcp-session-id は付かない

$ python lab02_protocol/run_protocol.py --part client
■ 同じことを Client(kb.mcp) で (同じプロセス。子プロセスもポートも無い)
  protocol=2026-07-28  ttl_ms=300000  cache_scope=public
  道具 search_regulations (規程を探す)  引数 ['query', 'top_k']  read_only_hint=True
  道具 get_regulation (規程の全文)  引数 ['doc_id']  read_only_hint=True
  stdio で生で受け取った tools/list と同じ中身か: True
  call_tool → is_error=False  structured_content: a-06 3. 出張申請  (電文の structuredContent / isError が snake_case の属性になる)
→ Client は「封筒を付けて 1 通送り、返事を型に直す」係。中で起きていることは上の生の電文と同じ
```

## 試験

```
$ python -m pytest -q lab02_protocol/tests
....                                                                     [100%]
4 passed
```
