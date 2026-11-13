# ラボ 3 最初のサーバ ― 公式 SDK で 1 歩ずつ書く

> データはすべて架空 (ソラハ電機)。Claude は呼びません (API キー不要)。

社内規程 13 本 (`data/kb/regulations/`) を探すサーバを、mcp 2.3.0 の `MCPServer` で 2 段階で書きます。
`servers/kb.py` (講座の本番のサーバ) より素朴な、言葉をそのまま含むかどうかの検索です。

| ファイル | 中身 |
|---|---|
| `step1_server.py` | 道具 1 つ。型ヒントと docstring だけ → SDK が name・description・inputSchema・outputSchema を作る |
| `step2_server.py` | 構造化出力 (pydantic)・引数の説明 (`Annotated[..., Field()]`)・`ToolAnnotations(read_only_hint=True)`・`ToolError`・資料のひな形・定型文 |
| `naive_server.py` | 比べる用の素朴な書き方 (無い番号で KeyError)。🔴 手本にしない |

```
python lab03_first_server/run_first_server.py --step 1              # 型ヒントと docstring から道具の形ができる
python lab03_first_server/run_first_server.py --step 2              # 構造化出力・注釈・ToolError・資料・定型文
python lab03_first_server/run_first_server.py --step 2 --json       # 生成された tools/list をそのまま JSON で
python lab03_first_server/run_first_server.py --errors              # ToolError と想定外の例外の違い
python lab03_first_server/run_first_server.py --step 2 --stdio      # 子プロセス (stdio) で立ててつなぐ
python lab03_first_server/step2_server.py                           # サーバ単体を stdio で起動 (Claude Desktop などから)
```

- つなぎ方は `Client` 1 つ。`Client(step2_server.mcp)` = 同じプロセス (試験向け)、`Client(StdioServerParameters(...))` = 子プロセス
- 🔴 docstring の `Args:` は description に丸ごと入るだけ。引数の説明は `Annotated[str, Field(description=...)]` に書く
- 🔴 `ToolError` の文は頭に `Error executing tool <名前>: ` が付いてモデルに届く。想定外の例外は `Error executing tool <名前>` だけ (中身は隠れ、traceback はサーバのログにだけ出る)
- 🔴 `read_only_hint` はヒント。権限の代わりにはならない (第 6 部)
- 資料 (resource) の失敗は、道具と違って `is_error` の結果ではなく例外 (`MCPError`) でクライアントに届く
- 試験: `python -m pytest -q lab03_first_server/tests` (キットの根で。`test_step_servers.py` が Client(サーバ) で試験を書く見本)
