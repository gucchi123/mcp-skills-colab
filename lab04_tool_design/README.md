# ラボ 4 道具の設計 ― モデルは正しい道具を選べるか

> データはすべて架空 (ソラハ電機)。

6 サーバ・17 個の道具をモデルに見せ、40 問 (`data/questions/tool_selection.jsonl`。2 問は道具の要らない問い) それぞれで
依頼を **1 回だけ** 送り、応答の **最初の tool_use** が正解の道具か を数えます。道具は実行しません。
道具の欄 (tools) の作り方を 4 通りに変えて比べ、欄の大きさ (字数とトークンの目安) も並べます。

| 通り | 変えるもの | 見たいこと |
|---|---|---|
| `good` | 何も変えない (サーバが出したまま) | 基準 |
| `vague` | 説明を一言にする (「データを取得する」など)。名前はそのまま | 説明がどれだけ効いているか |
| `names` | 名前を `tool01`〜`tool17` にする。説明はそのまま | 名前がどれだけ効いているか |
| `subset` | 問いの分野のサーバの道具だけ (2〜3 個) を見せる | 道具を絞ると選び間違いと入力の量がどう変わるか |

```
python run_tool_design.py --only TS-01,TS-39 --show              # 2 問だけ、1 問ずつ表示
python run_tool_design.py --all --name good                      # 40 問を元の説明で、結果を out/ に残す
python run_tool_design.py --all --variant all --name compare     # 4 通りを比べる
python run_tool_design.py --all --variant vague --show           # あいまいな説明で、外した問いだけ表示
python run_tool_design.py --describe                             # 道具の欄の大きさと、同じ道具の見え方
```

- 数えるもの: 最初の道具の正解数・道具を使わなかった数 (正しく使わなかった / 取りこぼした)・要らないのに使った数・
  取り違え (期待した分野のサーバ → 選んだサーバ)・道具の欄の字数とトークンの目安・応答の `usage.input_tokens` の合計
- トークンの目安は「ASCII 4 字 = 1、それ以外 1 字 = 1」の概算です。本物の数は Claude の応答の usage で見ます
- 道具の要らない問い (TS-39・TS-40) の `subset` には kb の道具を見せます
- `--provider mock` はキーワード照合の筋書き (`tool_variants.KeywordRouter`)。渡された説明と名前だけを見て選ぶので、
  道具の欄を変えると選び方も変わります (配線の確認)。🔴 mock の数字は Claude の性能の証拠になりません
- 試験: `python -m pytest -q lab04_tool_design/tests` (mock だけ・キー不要)
