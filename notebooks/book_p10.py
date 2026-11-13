from build_notebooks import C, M, nb

BOOKS = {}

BOOKS["p10_mcp_x_skills.ipynb"] = nb("P10 MCP×Skills を組み合わせる ― Agent SDK と Claude API", "ラボ 9 で自分で書いた「Skill の読み込み」と「道具の繋ぎ込み」を、Claude Agent SDK と Claude API に任せます。", [
    (M, "## 1. Agent SDK にサーバと Skill を読ませる (モデルは呼びません)\n作業フォルダの `.claude/skills/` に Skill を 2 本置き、MCP サーバ 4 本を stdio で起動させます。つないだだけで、何が文脈に載るかが分かります。"),
    (C, '''from run_agent import amain as agent
with safe():
    r = await agent(["--probe"])'''),
    (M, "## 2. 設定を読む\n利用者はサーバの起動時に環境変数で渡し、書き込みの道具は `allowed_tools` に入れません。"),
    (C, '''import inspect, agent_setup
print(inspect.getsource(agent_setup.options))'''),
    (M, "## 3. 月次レポートを作らせる (講師の実行記録)\nSkill が呼ばれ、report サーバの道具で数字を取り、スクリプトで 1〜3 節を作ります。数字の行がスクリプトの出力と一字一句同じかで答え合わせをします。"),
    (C, '''with safe():
    r = await agent(["--show-saved", "opus"])'''),
    (M, "## 4. Sonnet 5.5 で同じことをすると (講師の実行記録)"),
    (C, '''with safe():
    r = await agent(["--show-saved", "sonnet"])'''),
    (M, "## 5. 書き込みを頼むと (講師の実行記録)\n発注の道具は許可していないので、`can_use_tool` に来て断られます。"),
    (C, '''with safe():
    r = await agent(["--show-saved", "order"])'''),
    (M, "## 6. Claude API に送る形\nSkill は Anthropic 側のコード実行の箱で動きます。MCP コネクタはインターネットに出た HTTPS のサーバにだけつなげます。"),
    (C, '''from run_api import amain as api
with safe():
    r = await api(["--dry"])'''),
])
