from build_notebooks import C, M, nb

BOOKS = {}

BOOKS["p09_build_skill.ipynb"] = nb("P09 Skill を作る ― 読み込み係・発動の試験・最後まで", "Messages API の上で「段階的に読む」を真似る読み込み係 (load_skill・read_skill_file・run_skill_script) を MCP のホストに足し、スキルが正しく発動するかと、月次レポートの数字が正解と合うかを確かめます。", [
    (M, "## 1. 読み込み係の道具と守り\nモデルに見せる道具と、システムプロンプトのスキル一覧 (段階 1) を見ます。フォルダの外を読む・別のスキルのスクリプトを走らせる、といった呼び方は断ります (Claude を呼びません)。"),
    (C, '''from run_build_skill import amain as build
with safe():
    r = await build(["--part", "loader"])'''),
    (M, "## 2. 発動の試験 (4 問)\n問いごとに、最初に load_skill でどのスキルを読んだかを見ます。T-17 は「レポート」の語があっても月次ではない問いです。"),
    (C, '''with safe():
    r = await build(["--part", "trigger", "--show"])'''),
    (M, "## 3. 説明文を曖昧にすると\n説明文を「レポートを作る。」「文書を確認する。」に替えて同じ問いを流します。mock は説明文を読まないので差は出ません。本物のモデルで差を見ます。"),
    (C, '''with safe():
    r = await build(["--part", "trigger", "--variant", "vague"])'''),
    (M, "## 4. 月次レポートを最後まで (2026-08)\nスキルを読む → report サーバの道具を 3 つ → scripts/build_report.py → 書き方を読む → レポート。最後の文から数字を読み取り、正解と照合します。"),
    (C, '''with safe():
    r = await build(["--month", "2026-08", "--show"])'''),
    (M, "## 5. 2 か月ぶんを照合する\n数字 13 個が正解と合ったか、手順 (最初にスキルを読んだ・道具を 3 つ呼んだ・スクリプトが通った・書き方を読んだ・候補を書いた) が抜けていないかを並べます。"),
    (C, '''with safe():
    r = await build(["--only", "2026-05,2026-09"])'''),
], llm=True)
