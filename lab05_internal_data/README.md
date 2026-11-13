# ラボ 5 社内データをつなぐ ― 安全に読む

> データはすべて架空 (ソラハ電機)。Claude は呼びません (API キー不要)。

顧客台帳 (crm)・社内規程 (kb)・在庫 (inventory)・月次の数字 (report) のサーバに MCP の `Client` で直接つなぎ、
読むだけのデータを安全に出すための 5 つの仕組みを、実際に呼んで確かめます。

```
python run_internal_data.py                                       # 5 つの場面を全部
python run_internal_data.py --only resources --show               # 資料の一覧と全文
python run_internal_data.py --only visibility --customer C-002,IND-001   # 9 人 × 2 社の出し分けの表
python run_internal_data.py --only visibility --all               # 189 組を規程の正解と照合
python run_internal_data.py --only audit                          # 監査ログ (audit.jsonl) の行
python run_internal_data.py --only cache,report --name teacher    # キャッシュの目安・数字の照合 → out/summary_teacher.json
```

| 場面 | 見ること |
|---|---|
| resources | 資料 (`crm://policy`)・資料のひな形 (`kb://regulations/{doc_id}`)・道具の並び。資料を読んでも監査ログは増えない |
| visibility | 同じ `get_customer` を U-01〜U-09 の名前で呼ぶと、見える項目が変わる (`common/policy.py`) |
| audit | だれが・どの顧客の・どの項目を隠されたか。値そのものは書かない。利用者が決まらない呼び出しは止まる |
| cache | `tools/list`・`resources/list` の結果に付く `ttl_ms` / `cache_scope` と、読むだけの印 |
| report | 月次の売上・問い合わせ・在庫割れを正解 (`data/report/gold_numbers.json`) と照合 |

## 資料 (resource) にするか、道具 (tool) にするか

- **資料**: アプリや人が選んで文脈に入れるもの。URI で指す。だれが読んでも同じ中身 (規程・型・方針)。
- **道具**: モデルが判断して呼ぶもの。引数で探す・計算する。利用者で中身が変わる・監査が要るもの (顧客 1 件・月次の数字)。
- このキットの Host はモデルに道具だけを渡します。だから kb は同じ規程を道具 `get_regulation` でも出しています。
- 利用者で中身が変わるもの (顧客台帳) を資料にしない。資料の読み出しは道具ほど細かく記録・制御していない (このラボで確かめる)。

## 注意

- 利用者はホスト (ここではラボの入口) が `common.identity.set_user` で決めます。モデルの引数では決めません。
- 書き込み先 (`SOLAHA_STATE_DIR`) は実行ごとに一時フォルダを作ります。キットの `state/` は使いません。
- 試験: `python -m pytest -q lab05_internal_data/tests` (キットの根で・`PYTHONUTF8=1`)
- 実際の出力と、mcp 2.3.0 で気づいたことは `RUN_LOG.md`。
