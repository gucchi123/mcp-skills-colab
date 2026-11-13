from build_notebooks import C, M, nb

BOOKS = {}

BOOKS["p03_first_server.ipynb"] = nb("P03 最初のサーバ ― 公式 SDK で 1 歩ずつ書く", "社内規程 13 本を探すサーバを mcp 2.3.0 の `MCPServer` で書き、`Client` でつないで確かめます。ステップ 1 は道具 1 つ、ステップ 2 で実務の形 (構造化出力・注釈・ToolError・資料・定型文) に育てます。", [
    (M, "## 1. ステップ 1: 型ヒントと docstring から道具の形ができる\n`step1_server.py` は関数 1 つに `@mcp.tool()` を付けただけです。関数名・docstring・型ヒント・既定値から、SDK が tools/list の中身を作ります。"),
    (C, '''from run_first_server import amain as first
with safe():
    r = await first(["--step", "1"])'''),
    (M, "## 2. 生成された tools/list をそのまま見る\nモデルが受け取るのはこの JSON です。docstring の `Args:` が description に入っただけで、引数の説明は空のままなことを確かめます。"),
    (C, '''with safe():
    r = await first(["--step", "1", "--json"])'''),
    (M, "## 3. ステップ 2: 構造化出力・注釈・ToolError・資料・定型文\n戻り値を pydantic のモデルにすると `structured_content` が付きます。無い番号は `ToolError` で断り、直し方 (ある番号) を添えます。"),
    (C, '''with safe():
    r = await first(["--step", "2"])'''),
    (M, "## 4. ToolError と想定外の例外の違い\n同じ「無い番号」でも、`ToolError` で断ると文が届き、素朴に `KeyError` を起こすと「Error executing tool …」しか届きません。どれも例外ではなく `is_error=True` の結果です。"),
    (C, '''with safe():
    r = await first(["--errors"])'''),
    (M, "## 5. 同じサーバを子プロセス (stdio) で立ててつなぐ\nClaude Desktop・Claude Code と同じつなぎ方です。サーバのコードは変えず、`Client` に渡すものだけが変わります。"),
    (C, '''with safe():
    r = await first(["--step", "2", "--stdio"])'''),
], llm=False)
