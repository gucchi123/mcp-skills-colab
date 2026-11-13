# ラボ 2 MCP の仕組み ― 電文を自分の手で送る

> データはすべて架空 (ソラハ電機)。Claude は呼びません (API キー不要)。

社内規程のサーバ (`servers/kb.py`) に、ホストが送るのと同じ JSON-RPC を自分で書いて送り、返事をそのまま見ます。
版は **2026-07-28**。initialize の握手もセッション ID もありません。どの要求も `params._meta` に
「版 (protocolVersion)・名乗り (clientInfo)・できること (clientCapabilities)」を持ちます。

```
python lab02_protocol/run_protocol.py                       # stdio: 1 行 1 通の JSON (discover → tools/list → tools/call → 資料 → 定型文)
python lab02_protocol/run_protocol.py --part legacy         # 旧来の initialize を送ると何が返るか
python lab02_protocol/run_protocol.py --part http           # Streamable HTTP: ヘッダー・ttlMs/cacheScope・Client のキャッシュ
python lab02_protocol/run_protocol.py --part client         # 同じことを Client(kb.mcp) で (同じプロセス)
python lab02_protocol/run_protocol.py --part all --show     # 全部。要求を毎回全文で、返事を長めに出す
```

- stdio: `python -m servers.kb` を子プロセスで立てます。利用者は起動した人 (`SOLAHA_USER=U-05`)。監査ログは一時フォルダに書きます
- HTTP: `http_kb.py` が空きポートの `127.0.0.1` だけで待ちます。終わったら止めます。🔴 認可を付けていないので外に出さない (第 7 部)
- 返事は画面用に縮めています (`…(全467字)`・`{…}`)。全部見るときは `--show`
- 🔴 1 本の接続の「時代」は最初の 1 通で決まります。initialize で始めると古い版 (2025-11-25) になり、2026-07-28 の要求は断られます
- 試験: `python -m pytest -q lab02_protocol/tests` (キットの根で。キー不要)

部品: `wire.py` (子プロセスとの読み書き・`_meta`・縮め方)、`http_kb.py` (HTTP で立てる)。
