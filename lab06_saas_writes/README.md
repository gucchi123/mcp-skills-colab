# ラボ 6 SaaS を操作する ― 書き込みを安全に

> データはすべて架空 (ソラハ電機)。Claude は呼びません (API キー不要)。host の場面だけ mock の偽モデルを使います。

発注 (`inventory.create_purchase_order`) と経費の申請 (`expense.submit_expense`) を、サーバの側の 4 つの守りで動かします。

1. **確認**: 登録の前に「何を・いくつ・どこへ・いくらで」を人に見せる (elicitation。2026-07-28 では MRTR = 入力要求 → 送り直し)
2. **二重登録の防止**: 同じ `request_id` の 2 回目は前の結果を返すだけ (確認も出さない)
3. **本人だけ**: 経費は利用者本人の名前でしか申請できない
4. **金額の承認**: 10 万円を超える発注は「承認待ち」で登録する (依頼文で頼まれても飛ばさない)

```
python run_saas_writes.py                               # 場面を全部
python run_saas_writes.py --only schema,confirm         # モデルに見せる引数の形・確認の文と答え方
python run_saas_writes.py --only idem,self              # 同じ request_id の 2 回目・他人の名前の申請
python run_saas_writes.py --only gold --all             # 購買の依頼 10 件 (11 案) を正解と照合
python run_saas_writes.py --only wire --show            # 確認 1 往復の素の JSON-RPC
python run_saas_writes.py --only tasks,host             # Tasks の有無・mock のホストで確認を出す
```

| 場面 | 見ること |
|---|---|
| schema | Python の関数には `confirm` があるが、モデルに見せる inputSchema には無い (モデルは自分で承認できない) |
| confirm | 確認の文。承認 / 断る / 閉じた / 承認だが ok=false の違い。答える仕組みの無いクライアント |
| idem | 同じ request_id の 2 回目は duplicate=True・確認なし。request_id を変えた同じ内容の経費は分割申請で差し戻し |
| self | 他人の名前の経費申請はエラー。確認は出ない (Resolve が本体より先に走るので、断る条件を Resolve の中でも見ている) |
| gold | `data/inventory/requests.json` の正解と照合。承認の線は `common.rules.po_approval` |
| wire | SDK の Client ⇄ `wire_tee.py` (行を書き写す中継) ⇄ stdio のサーバ。`input_required` → `inputResponses` 付きで送り直し |
| tasks | mcp 2.3.0 に Tasks (長い処理) があるかを型・クラス・素の `tasks/get` で確かめる → 無い (Method not found) |
| host | 🔴 mock のモデルで Host を回し、承認役が断る → 承認 → 同じ依頼をもう一度、で確認の出方を見る |

## 素の線を見る仕組み

`wire_tee.py` は stdio の中継です。Host と同じ SDK の `Client` から、本物のサーバの代わりに中継を起動し、
中継が本物のサーバ (`python -m servers.inventory`) を起動します。行は 1 文字も変えずに素通しし、同じ行を記録に書きます。
SDK が実際に送った JSON-RPC が、そのまま見えます。

## Tasks について

2026-07-28 の仕様では Tasks は本体から外れて拡張 (`io.modelcontextprotocol/tasks`) になりました。
mcp 2.3.0 はその拡張を同梱していません (型は 2025-11-25 のものだけ・サーバに送ると `-32601 Method not found`)。
時間のかかる処理は、講座では「受付番号を返す道具 + 状況を返す道具」(例: `submit_expense` → `get_expense_status`) で組みます。

## 注意

- 書き込み先 (`SOLAHA_STATE_DIR`) は場面ごとに一時フォルダを作ります (発注番号が PO-0001 から始まる)。キットの `state/` は使いません。
- 🔴 mock の筋書きは決め打ちです。host の場面の in/out の数 (トークン数) も mock の概算で、性能の証拠になりません。
- 経費の例の日付は 2026-10-20、申請日は実行した日です。翌月 10 日を過ぎて回すと「経理部の確認」に変わることがあります (規程の第 1 条)。
- 試験: `python -m pytest -q lab06_saas_writes/tests` (キットの根で・`PYTHONUTF8=1`)
- 実際の出力と、mcp 2.3.0 で気づいたことは `RUN_LOG.md`。
