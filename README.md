# MCP×Agent Skills の業務実装 ― ラボ一式

> **この教材に登場する会社・人物・製品・数値・文書はすべて架空のものです。実在の企業・団体・個人とは関係ありません。**

講座「MCP×Agent Skills の業務実装 ― 社内データ・SaaS・権限を本番でつなぐ」で使うラボです。
架空の会社「ソラハ電機」の社内データ (規程・顧客・在庫・経費・月次・契約) を、業務の MCP サーバ 6 本と Skill 2 本でつなぎ、
権限・監査・書き込みの確認・攻撃への守りまでを手元で確かめます。

## 最初に読むもの

| ファイル | 中身 |
|---|---|
| `notebooks/` | 講義の部ごとのノートブック (p02〜p12)。Colab でも手元の Jupyter でも動きます |
| `lab*/README.md` | ラボごとの目的・コマンド・読み方 |
| `lab*/RUN_LOG.md` | 講師が回したときのコマンドと出力・読み取れること (外れた結果も残しています) |
| `data/README.md` | 架空データの作り方と照合のしかた |

## 動かす

- Python 3.11 以上
- `python -m pip install -r requirements.txt`
- テスト (API キー不要): `python -m pytest`
- ラボのコマンドはこのフォルダ (リポジトリの一番上) から実行します。例: `python lab03_first_server/run_first_server.py --step 1`

### Colab で開く

ノートブックの最初のセルが、Colab のときだけこのリポジトリを取得し、必要なものを入れます。手元の Jupyter ではそのまま動きます。

## AI の呼び先

Claude を呼ぶ部分は `common/llm.py` にまとめてあります。ノートブックは次の順で自動的に選びます。

| 呼び先 | 必要なもの | 中身 |
|---|---|---|
| `anthropic` | ご自身の `ANTHROPIC_API_KEY` | 本物のモデルを呼びます。同じ依頼の記録が `.cache/llm.sqlite` にあれば再生します (費用 0) |
| `replay` | なし (`.cache/llm.sqlite` を同梱) | 講師が本物のモデルで回した応答を再生します。費用 0。入力を変えるとエラーで止まります |
| `mock` | なし | 配線の確認用の決まった答えです。🔴 数字はモデルの性能の証拠になりません |

🔴 API キーは画面やノートブックの出力に出さないでください。Colab では「シークレット」に登録して使います。

## フォルダ

| 場所 | 中身 |
|---|---|
| `servers/` | 業務の MCP サーバ (kb・crm・inventory・expense・report・contract、HTTP 版の crm) |
| `skills/` | Skill 2 本 (`solaha-monthly-report`・`solaha-contract-review`) |
| `common/` | 利用者と監査ログ・規程・規則・AI の呼び先などの共通部品 |
| `data/` | 架空のデータと、その作り方 |
| `lab02_protocol` 〜 `lab12_usecases` | 講義の第 2〜12 部のラボ |
| `tests/` | サーバ・Skill・データの試験 |

`lab10_mcp_x_skills/out/` の実行記録では、講師の手元のフォルダの場所を `<kit>` に置き換えています。

## ライセンス

MIT License (`LICENSE`)。
