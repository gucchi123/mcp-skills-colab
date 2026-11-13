# ラボ 9 Skill を作る ― 読み込み係・発動の試験・最後まで

> データはすべて架空 (ソラハ電機)。

Messages API の上で「段階的に読む」を真似る **スキルの読み込み係** (`skill_host.py`) を、MCP のホスト (`common.host.Host`) に継ぎ足します。

| 段階 | 読み込み係でのやり方 |
|---|---|
| 1 | システムプロンプトにスキルの name と description の一覧だけを入れる |
| 2 | 道具 `load_skill(name)` → SKILL.md の本文 |
| 3 | 道具 `read_skill_file(name, path)` → references/ など。道具 `run_skill_script(name, script, input_json)` → scripts/ の .py をホストの側で実行し、出力だけを返す |

MCP の report サーバの道具 (`mcp__report__…`) と同じ並びでモデルに見せます。

```
python run_build_skill.py --part loader                       # 道具と守り (Claude を呼ばない)
python run_build_skill.py --part trigger --show               # 発動の試験 4 問、やりとりも表示
python run_build_skill.py --part trigger --all --name std     # 20 問 (月次 10・契約 5・どれでもない 5)
python run_build_skill.py --part trigger --all --variant vague --name vague   # 説明文を曖昧にした版
python run_build_skill.py --month 2026-08 --show              # 月次レポートを最後まで、数字を正解と照合
python run_build_skill.py --all --name e2e                    # 5 か月ぶん
```

- **発動の試験**: 最初のモデルの番で、最初に呼んだ道具が `load_skill(正しい name)` かを見る (どれでもない問いは、load_skill を呼ばなければ正しい)。
  スキルごとに適合率 (読んだうち正しかった割合) と再現率 (読むべきうち読んだ割合)。問いは `trigger_set.py`
- **説明文の実験**: `--variant vague` は説明文を「レポートを作る。」「文書を確認する。」に差し替える (skills/ は書き換えない)。
  発動は description で決まるので、本物のモデルで差が出るはず
- **最後まで**: スキルを読む → 道具 3 つ → `scripts/build_report.py` → 書き方を読む → レポート。
  照合は **モデルが最後に書いた文** から数字 13 個を読み取り、`data/report/gold_numbers.json` と比べる (手順の抜けも並べる)
- 守り: name は一覧にあるものだけ・path と script はそのスキルのフォルダの中だけ・スクリプトは scripts/ の .py だけ・シェルを通さない・
  入力ファイルは使い捨てのフォルダ・30 秒で打ち切り。`--part loader` で、外へ出る呼び方が断られるのを見る
- `--provider mock` の筋書き: `--plan keyword` (問いの語でスキルを選ぶ) / `--plan follow` (月次レポートを手順どおり)。
  🔴 mock は説明文を読まないので vague でも結果は同じ。mock の適合率・再現率は配線の確認で、性能の証拠ではない

## 本物の Claude でのスキル

この読み込み係は **仕組みを目で見るため** のものです。本番では次を使います (Claude API の Skills と、Claude Code の Skills)。

- Claude API: Skills API (GA・beta ヘッダー不要) でスキルを上げ、`container={"skills": [...]}` と コード実行ツール
  (`code_execution_20250825`) を付けて Messages API を呼ぶ。スクリプトはコンテナの中で動く (ネットワーク不可)。1 依頼 20 スキルまで
- Claude Code・Claude Agent SDK: `.claude/skills/<name>/SKILL.md` のフォルダから読む (SDK は `setting_sources` と `skills`)

試験: `python -m pytest -q lab09_build_skill/tests` (mock だけ・キー不要)
