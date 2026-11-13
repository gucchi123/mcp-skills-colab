# ラボ 8 Agent Skills の仕組み ― 何がいつ文脈に入るか

> データはすべて架空 (ソラハ電機)。このラボは Claude を呼びません (API キー不要)。

講座の 2 つのスキル (`skills/solaha-monthly-report`・`skills/solaha-contract-review`) の SKILL.md を読み、
決まりに照らし、**段階的に読む (progressive disclosure)** の各段階で文脈に入る量を測ります。部品は `skill_mech.py`。

```
python run_mechanics.py                                # 読んで決まりに照らす (--show で全項目)
python run_mechanics.py --part bad                     # わざと壊した見本 3 つを同じ検査に通す
python run_mechanics.py --part levels --show           # 段階 1・2・3 の量。スクリプトは実際に走らせて出力の量を測る
python run_mechanics.py --part compare --n 2,20        # 毎回の依頼に乗る量: Skill / system に全部 / 道具の説明に全部
python run_mechanics.py --part split                   # 何をどこに置くか (Skill・MCP・システムプロンプト)
python run_mechanics.py --all --name base              # 全部。out/summary_base.json に残す
```

- 段階 1 = name + description (いつも文脈にある) / 段階 2 = SKILL.md の本文 (使うときだけ) / 段階 3 = references・scripts (要るときだけ)。
  スクリプトは実行すれば中身は入らず、**出力だけ** が入る
- 決まりの出どころ: agentskills.io/specification (name 1〜64 字・a-z0-9-・フォルダ名と一致、description 1〜1024 字、compatibility 500 字以内、
  metadata は文字列→文字列、allowed-tools は Experimental、本文 500 行以内・5000 トークン未満の推奨、参照は 1 階層まで) と、
  Claude API の追加の決まり (name に anthropic / claude を入れない、XML タグ不可)。(Agent Skills の公式ドキュメント)
- 🔴 トークンは **見積り** (英数字 4 文字 ≈ 1、日本語 1 文字 ≈ 1)。字数は実数。
  実測は `--part levels --count-tokens` (anthropic の `messages.count_tokens`)。キーが無いとき・`LLM_NO_KEY=1` のときは何もしない
- compare の 20 個は、本物の 2 つを名前だけ替えて増やした写し。Claude API の Skills は 1 依頼 20 個まで
- frontmatter は簡易の読み方 (key: value と 1 段の入れ子)。PyYAML は使わない
- 試験: `python -m pytest -q lab08_skills_mechanics/tests` (キー不要)
