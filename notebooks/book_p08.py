from build_notebooks import C, M, nb

BOOKS = {}

BOOKS["p08_skills_mechanics.ipynb"] = nb("P08 Agent Skills の仕組み ― 何がいつ文脈に入るか", "講座の 2 つのスキル (月次レポート・契約書の一次レビュー) の SKILL.md を読み、決まりに照らし、段階 1・2・3 で文脈に入る量を測ります。", [
    (M, "## 1. SKILL.md を読んで決まりに照らす\nfrontmatter (name・description・allowed-tools…) を読み、Agent Skills の決まり (name の文字・フォルダ名との一致・description の長さなど) を 1 つずつ確かめます。"),
    (C, '''from run_mechanics import amain as mech
with safe():
    r = await mech(["--only", "solaha-monthly-report", "--show"])'''),
    (M, "## 2. わざと壊した見本を同じ検査に通す\n大文字と _ の入った name、長すぎる description、frontmatter の無いファイル。どこで止まるかを見ます。"),
    (C, '''with safe():
    r = await mech(["--part", "bad"])'''),
    (M, "## 3. 段階ごとに文脈に入る量\n段階 1 (name と description) はいつも、段階 2 (本文) は使うときだけ、段階 3 (references・scripts) は要るときだけ。スクリプトは実際に走らせ、文脈に入るのは出力だけであることを確かめます。トークンは見積りです。"),
    (C, '''with safe():
    r = await mech(["--part", "levels", "--show"])'''),
    (M, "## 4. スキルが 2 個のときと 20 個のとき\n同じ中身を、Skill にする / システムプロンプトに全部書く / 道具の説明に全部書く、の 3 通りで、毎回の依頼に乗る量を比べます (20 個は名前だけ替えた写し)。"),
    (C, '''with safe():
    r = await mech(["--part", "compare", "--n", "2,20"])'''),
    (M, "## 5. 何をどこに置くか\n手順と型は Skill、データと操作は MCP、どの仕事にも効く方針はシステムプロンプト。2 つのスキルで分けてみます (allowed-tools の道具がサーバに在るかも確かめます)。"),
    (C, '''with safe():
    r = await mech(["--part", "split"])'''),
], llm=False)
