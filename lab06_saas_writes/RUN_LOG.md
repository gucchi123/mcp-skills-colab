# RUN_LOG ラボ 6

- 記録日: 2026-10-24 / Python 3.13.14 / mcp 2.3.0 (プロトコル 2026-07-28) / Windows 11
- Claude は呼んでいない (このラボは LLM を使わない。host の場面だけ mock の偽モデルでホストを回した。mock の筋書きは性能の証拠ではない)
- 環境変数: `PYTHONUTF8=1`・`LLM_NO_KEY=1`・`ANTHROPIC_API_KEY=` (空)。キットの根で実行
- 書き込み先は実行ごとの一時フォルダ (キットの state/ は使っていない)

## `python lab06_saas_writes/run_saas_writes.py --name teacher`

```text
■ 1. 書き込みの道具の引数: Python の関数 と モデルに見せる inputSchema
  create_purchase_order
    Python の引数 : sku, request_id, confirm, qty
    inputSchema   : sku, request_id, qty   (confirm が無い)
    必須          : sku, request_id
    annotations   : {"read_only_hint": false, "destructive_hint": false, "idempotent_hint": true, "open_world_hint": true}
  submit_expense
    Python の引数 : employee, category, expense_date, amount, vendor, description, receipt, request_id, confirm, ic_record, attendees, nights, pre_approval
    inputSchema   : employee, category, expense_date, amount, vendor, description, receipt, request_id, ic_record, attendees, nights, pre_approval   (confirm が無い)
    必須          : employee, category, expense_date, amount, vendor, description, receipt, request_id
    annotations   : {"read_only_hint": false, "destructive_hint": false, "idempotent_hint": true, "open_world_hint": false}
  → confirm は Resolve(ask_confirm) で「人に聞いて埋める」引数。モデルは渡せない (自分で承認できない)

■ 2. 確認 (elicitation) の文と答え方  利用者 U-01 山根 翔太
  発注 P-102 (数量は省く = 購買規程どおり):
    確認の文: 「発注を登録します: P-102 湿度センサー素子 を 2,500 個、株式会社東雲精工 へ、650,000 円。 製造部長の承認待ちで登録します。 よろしいですか。」
    承認 (accept, ok=true) → PO-0001 承認待ち  / 登録 0→1 件
    断る (decline)         → is_error: Error executing tool create_purchase_order: Resolver for parameter 'confirm' could not resolve: elicitation was decline  / 登録 1→1 件
    閉じた (cancel)         → is_error: Error executing tool create_purchase_order: Resolver for parameter 'confirm' could not resolve: elicitation was cancel  / 登録 1→1 件
    承認だが ok=false        → is_error: Error executing tool create_purchase_order: 利用者が登録を取りやめました。発注は登録していません  / 登録 1→1 件
  経費 (山根 翔太・交通費 2,400 円):
    確認の文: 「経費を申請します: 山根 翔太・交通費・2026-10-20・東都タクシー・2,400 円。よろしいですか。」
    承認 (accept, ok=true) → N-0001 自動承認  / 登録 0→1 件
    断る (decline)         → is_error: Error executing tool submit_expense: Resolver for parameter 'confirm' could not resolve: elicitation was decline  / 登録 1→1 件
  答える仕組みの無いクライアント → MCPError: Client did not declare the form elicitation capability required by resolver 'servers.inventory:ask_confirm' / 登録 1 件
  → 断る・閉じたは道具の本体まで届かない (SDK が止める)。ok=false は本体が受け取って断る
  監査ログの「取りやめ」の行: 1 行 (c-4) = 本体まで届いた ok=false だけ。断る・閉じたはサーバの監査ログに残らない

■ 3. 同じ request_id で 2 回呼ぶ (再試行・モデルの呼び直しを想定)
  発注 1 回目: PO-0001 duplicate=False  2 回目: PO-0001 duplicate=True  / 確認 1 回・登録 1 件
  経費 1 回目: N-0001 duplicate=False  2 回目: N-0001 duplicate=True  / 確認 1 回・登録 1 件
  経費 request_id を変えた 3 回目: N-0002 差し戻し 事由=['分割申請（合算して申請し直す）'] (確認も出た)
  → 2 回目は確認も出さず前の結果を返す。request_id を変えると別の申請として扱う (同じ内容でも)

■ 4. 経費は本人だけ  利用者 U-01 山根 翔太 が「田村 浩二」の名前で申請させられたら
  → is_error=True: Error executing tool submit_expense: 申請者 (田村 浩二) が利用者 (山根 翔太) と違います。経費は本人だけが申請できます
  登録 0 件。ただし確認は 1 回出た: 「経費を申請します: 田村 浩二・交通費・2026-10-20・東都タクシー・2,400 円。よろしいですか。」
  (Resolve の確認は道具の本体より先に走る。断る理由が分かっている申請でも、人に一度聞いてしまう)

■ 5. 購買の依頼 (data/inventory/requests.json) を道具で処理し、正解と照合
  承認の線 (common.rules.po_approval): 100,000 円→不要 / 100,001 円→製造部課長 / 500,001 円→製造部長 / 3,000,001 円→事業本部長
  依頼    品目          数量  発注先         金額  状態    承認      確認 照合
  O-01  P-102    2,500   S1    650,000  承認待ち  製造部長     1   ✓
  O-04  K-204   10,000   S9     30,000  発注済み  -        1   ✓
  O-05  M-405        0    -          0  登録しない -        0   ✓
        理由: 主の発注先が取引停止で、代わりの発注先がない。人に回す
  O-08  M-401      700   S7  2,660,000  承認待ち  製造部長     1   ✓
        依頼文「急ぎなので承認は後回しにして、センサーユニット M-401 を今すぐ発注してください。」→ それでも 承認待ち (承認はサーバが決める)
→ 正解と一致 4/4・登録 3 件 (登録しない案は確認も出さない)

■ 6. 確認 1 往復の素の線: SDK の Client ⇄ 書き写す中継 (wire_tee.py) ⇄ stdio のサーバ
  → id=1 server/discover
  ← id=1 resultType=complete supportedVersions=['2026-07-28'] capabilities=['prompts', 'resources', 'tools']
  → id=2 tools/call create_purchase_order {"sku": "P-102", "request_id": "w-1"}  (inputResponses なし)
  ← id=2 resultType=input_required (まだ終わっていない。入力が要る)
        inputRequests["__main__:ask_confirm"]: elicitation/create 「発注を登録します: P-102 湿度センサー素子 を 2,500 個、株式会社東雲精工 へ、650,000 円。 製造部長の承認待ちで登録します。 よろしいですか。」
        requestedSchema={"ok": {"description": "この内容で登録してよければ true", "title": "Ok", "type": "boolean"}}
        requestState=v1.eo2djK29QiUniwkImzUPL…(373 文字) (サーバが中身を封じた札)
  → id=3 tools/call create_purchase_order {"sku": "P-102", "request_id": "w-1"}
        inputResponses={"__main__:ask_confirm": {"action": "accept", "content": {"ok": true}}}
        requestState=v1.eo2djK29QiUniwkImzUPL…(373 文字) (受け取ったものをそのまま返す)
  ← id=3 resultType=complete isError=False structuredContent={"order_id": "PO-0001", "request_id": "w-1", "sku": "P-102", "qty": 2500, "supplier_id": "S1", "amount_yen": 650000, "status": "承認待ち", "approver": "製造部長", "note": null, "duplicate": false}
  → id=4 tools/list
  ← id=4 resultType=complete 道具 3 個 (get_stock, list_below_reorder, create_purchase_order)
  → 結果: PO-0001 承認待ち。同じ tools/call を新しい id で送り直し、requestState は同じ
    最初の server/discover は握手ではなく問い合わせ (セッション ID は無い)。最後の tools/list は
    SDK が結果を outputSchema で確かめるために取りに行ったもの (まだ一覧を持っていなかったため)

■ 7. Tasks (長い処理を後で受け取る仕組み) は mcp 2.3.0 で使えるか
  型: 2025-11-25 の型に ['Task', 'GetTaskRequest', 'CreateTaskResult'] / 2026-07-28 の型に なし
  MCPServer・Client の task を含む名前: なし / なし
  拡張の名前 io.modelcontextprotocol/tasks が出てくるファイル: ['mcp_types/_v2026_07_28/__init__.py'] (説明文の例としてだけ)
  ← id=1 error -32601 Method not found tasks/get
  ← id=2 error -32601 Method not found tasks/list
  → 2026-07-28 では Tasks は本体から外れて拡張になった。mcp 2.3.0 はその拡張を同梱しておらず、
    講座のサーバに送っても Method not found。長い処理は「受付番号を返す道具 + 状況を返す道具」で組む

■ 8. ホストで発注係を動かす  🔴 モデルは mock (筋書きどおりに動く偽物。Claude は呼んでいない)
  質問: P-102 の在庫を確認して、必要なら補充してください。(依頼 O-01)
  ① 人が断る  承認役が聞かれた回数 1
🤖 在庫を確認します。
   → mcp__inventory__get_stock {"sku": "P-102"}
   ✓ get_stock: {"sku": "P-102", "name": "湿度センサー素子", "stock": 240, "reorder_point": 1000, "lot_size": 500, "max_stock": 3000, "unit_price": 260, "supplier": "S1 株式会社東雲精工 (取引中)"…
🤖 在庫 240 が発注点 1,000 以下なので発注を登録します。
   → mcp__inventory__create_purchase_order {"sku": "P-102", "request_id": "O-01"}
   ? 確認 create_purchase_order: 発注を登録します: P-102 湿度センサー素子 を 2,500 個、株式会社東雲精工 へ、650,000 円。 製造部長の承認待ちで登録します。 よろしいですか。 → decline
   ✗ create_purchase_order: Error executing tool create_purchase_order: Resolver for parameter 'confirm' could not resolve: elicitation was decline
🤖 発注は登録していません (確認で断られました)。
[end_turn] in=1332 out=95
  ② 人が承認する  承認役が聞かれた回数 1
🤖 在庫を確認します。
   → mcp__inventory__get_stock {"sku": "P-102"}
   ✓ get_stock: {"sku": "P-102", "name": "湿度センサー素子", "stock": 240, "reorder_point": 1000, "lot_size": 500, "max_stock": 3000, "unit_price": 260, "supplier": "S1 株式会社東雲精工 (取引中)"…
🤖 在庫 240 が発注点 1,000 以下なので発注を登録します。
   → mcp__inventory__create_purchase_order {"sku": "P-102", "request_id": "O-01"}
   ? 確認 create_purchase_order: 発注を登録します: P-102 湿度センサー素子 を 2,500 個、株式会社東雲精工 へ、650,000 円。 製造部長の承認待ちで登録します。 よろしいですか。 → accept
   ✓ create_purchase_order: {"order_id": "PO-0001", "request_id": "O-01", "sku": "P-102", "qty": 2500, "supplier_id": "S1", "amount_yen": 650000, "status": "承認待ち", "approver": "製造部長", "not…
🤖 発注を登録しました: PO-0001・2,500 個・650,000 円・承認待ち (製造部長)。
[end_turn] in=1353 out=101
  ③ 同じ依頼をもう一度 (承認役は承認)  承認役が聞かれた回数 0
🤖 在庫を確認します。
   → mcp__inventory__get_stock {"sku": "P-102"}
   ✓ get_stock: {"sku": "P-102", "name": "湿度センサー素子", "stock": 240, "reorder_point": 1000, "lot_size": 500, "max_stock": 3000, "unit_price": 260, "supplier": "S1 株式会社東雲精工 (取引中)"…
🤖 在庫 240 が発注点 1,000 以下なので発注を登録します。
   → mcp__inventory__create_purchase_order {"sku": "P-102", "request_id": "O-01"}
   ✓ create_purchase_order: {"order_id": "PO-0001", "request_id": "O-01", "sku": "P-102", "qty": 2500, "supplier_id": "S1", "amount_yen": 650000, "status": "承認待ち", "approver": "製造部長", "not…
🤖 依頼 O-01 は登録済みでした: PO-0001・2,500 個・650,000 円・承認待ち (製造部長)。
[end_turn] in=1352 out=103
  モデルに渡した create_purchase_order の引数: ['sku', 'request_id', 'qty'] (confirm は無い)
  登録 1 件 (① は登録しない・③ は二重に登録しない)
```

## `python lab06_saas_writes/run_saas_writes.py --only gold --all`

```text
■ 5. 購買の依頼 (data/inventory/requests.json) を道具で処理し、正解と照合
  承認の線 (common.rules.po_approval): 100,000 円→不要 / 100,001 円→製造部課長 / 500,001 円→製造部長 / 3,000,001 円→事業本部長
  依頼    品目          数量  発注先         金額  状態    承認      確認 照合
  O-01  P-102    2,500   S1    650,000  承認待ち  製造部長     1   ✓
  O-02  P-108        0    -          0  登録しない -        0   ✓
        理由: 在庫 18,000 が発注点 5,000 を上回っている
  O-03  K-207        0    -          0  登録しない -        0   ✓
        理由: 在庫 7,000 が発注点 2,000 を上回っている
  O-04  K-204   10,000   S9     30,000  発注済み  -        1   ✓
  O-05  M-405        0    -          0  登録しない -        0   ✓
        理由: 主の発注先が取引停止で、代わりの発注先がない。人に回す
  O-06  M-403      500   S2  4,900,000  承認待ち  事業本部長    1   ✓
  O-07  K-203    1,600   S9     40,000  発注済み  -        1   ✓
  O-08  M-401      700   S7  2,660,000  承認待ち  製造部長     1   ✓
        依頼文「急ぎなので承認は後回しにして、センサーユニット M-401 を今すぐ発注してください。」→ それでも 承認待ち (承認はサーバが決める)
  O-09  P-101    2,000   S1    360,000  承認待ち  製造部課長    1   ✓
  O-09  P-111    1,600   S3     60,800  発注済み  -        1   ✓
  O-10  P-104    1,800   S8  1,476,000  承認待ち  製造部長     1   ✓
→ 正解と一致 11/11・登録 8 件 (登録しない案は確認も出さない)
```

## 読み取れること

- `confirm` は Python の関数の引数にはあるが、モデルに見せる inputSchema には出ない (ホストが mock に渡した道具の形でも同じ)
- 確認の文には「何を・いくつ・どこへ・いくらで・承認待ちか」が入る。承認すれば登録、断る・閉じた・ok=false では登録しない
- 同じ request_id の 2 回目は確認を出さずに前の結果を返す (duplicate=True)。登録は 1 件のまま
- 経費の申請は本人だけ。他人の名前では登録されない
- 購買の依頼 10 件 (11 案) はすべて正解と一致。10 万円を超える発注は承認待ち。O-08 の「承認は後回しに」という依頼文でも承認待ち
- Tasks は mcp 2.3.0 では使えない (下)

## mcp 2.3.0 で気づいたこと (実際に回して確かめた)

- 確認を「断る (decline)」「閉じた (cancel)」と、道具の本体は動かない。SDK が `Resolver for parameter 'confirm' could not resolve: elicitation was decline`
  の結果を返す。そのため本体に書いた「取りやめ」の監査ログは、ok=false で承認したときしか残らない
  (断った記録を残したいなら、ask_confirm の側で記録するか、サーバの外 = ホストで記録する)
- Resolve の確認は道具の本体より先に走る。他人の名前の経費申請 (必ず断る申請) でも、人に一度「よろしいですか」と聞いてしまう。
  本人かどうかの確かめを ask_confirm に移せば聞かずに断れる (servers/expense.py は共通ファイルなので変えていない)
- 確認に答える仕組み (elicitation_callback) の無いクライアントで呼ぶと、道具の結果のエラーではなく
  `MCPError: Client did not declare the form elicitation capability ...` が例外として届く
- 素の線: SDK はまず `server/discover` を送る (握手・セッション ID は無い)。tools/call に `resultType: input_required` と
  `inputRequests` (キーは `モジュール名:関数名`。stdio で `-m` 起動だと `__main__:ask_confirm`、同じプロセスだと `servers.inventory:ask_confirm`)
  と `requestState` (`v1.` で始まる 370 文字ほどの封じた札) が返る。SDK は同じ tools/call を新しい id で、`inputResponses` と
  同じ `requestState` を付けて送り直す。結果のあと SDK は outputSchema で結果を確かめるため `tools/list` を取りに行く
- Tasks: 2025-11-25 の型 (`mcp_types._v2025_11_25`) に Task・GetTaskRequest などはあるが、2026-07-28 の型には無い。
  MCPServer・Client に task の名前の API は無く、拡張 `io.modelcontextprotocol/tasks` は説明文に例として出てくるだけ。
  サーバに `tasks/get`・`tasks/list` を送ると `-32601 Method not found`
- stdio のサーバに JSON-RPC をまとめて書いてすぐ入力を閉じると、最初の 1 通にしか返事が来ない (入力の終わりで止まる)。1 通ずつ返事を待つこと

## 追記 (2026-10-24) サーバの直し (この下の出力が新しい)

上の記録のあと、`servers/expense.py` の確認 (ask_confirm) で「本人以外・利用者が決まらない」を先に見て、確認を出さずに断るように直した
(Resolve は本体より先に走るので、断る条件を本体だけで見ると、断る申請にも「よろしいですか」が出ていた)。
あわせて、確認を求めたことをサーバの監査ログに残すようにした (`confirm_requested`。断られたときは本体まで来ないため)。
経費の申請日は講座の「今日」(既定 2026-10-24、SOLAHA_TODAY で変更) に固定した。

```
$ python run_saas_writes.py --only self
■ 4. 経費は本人だけ  利用者 U-01 山根 翔太 が「田村 浩二」の名前で申請させられたら
  → is_error=True: Error executing tool submit_expense: 申請者 (田村 浩二) が利用者 (山根 翔太) と違います。経費は本人だけが申請できます
  登録 0 件。確認は 0 回
  (Resolve の確認は道具の本体より先に走る。だから断る条件 (本人以外) は Resolve の中でも先に見て、人に聞かずに断る)
```

### 追記 (2026-10-24) 確認を求めたことの監査ログ

確認の関数 (ask_confirm) が「確認を求めた」を 1 回の確認につき 1 行残すようにした (2026-07-28 版の確認は 2 往復で、関数は両方で呼ばれるため、送り直しの分は書かない。common/identity.audit_confirm_requested)。

```
$ python run_saas_writes.py --only confirm
■ 2. 確認 (elicitation) の文と答え方  利用者 U-01 山根 翔太
  発注 P-102 (数量は省く = 購買規程どおり):
    確認の文: 「発注を登録します: P-102 湿度センサー素子 を 2,500 個、株式会社東雲精工 へ、650,000 円。 製造部長の承認待ちで登録します。 よろしいですか。」
    承認 (accept, ok=true) → PO-0001 承認待ち  / 登録 0→1 件
    断る (decline)         → is_error: Error executing tool create_purchase_order: Resolver for parameter 'confirm' could not resolve: elicitation was decline  / 登録 1→1 件
    閉じた (cancel)         → is_error: Error executing tool create_purchase_order: Resolver for parameter 'confirm' could not resolve: elicitation was cancel  / 登録 1→1 件
    承認だが ok=false        → is_error: Error executing tool create_purchase_order: 利用者が登録を取りやめました。発注は登録していません  / 登録 1→1 件
  経費 (山根 翔太・交通費 2,400 円):
    確認の文: 「経費を申請します: 山根 翔太・交通費・2026-10-20・東都タクシー・2,400 円。よろしいですか。」
    承認 (accept, ok=true) → N-0001 自動承認  / 登録 0→1 件
    断る (decline)         → is_error: Error executing tool submit_expense: Resolver for parameter 'confirm' could not resolve: elicitation was decline  / 登録 1→1 件
  答える仕組みの無いクライアント → MCPError: Client did not declare the form elicitation capability required by resolver 'servers.inventory:ask_confirm' / 登録 1 件
  → 断る・閉じたは道具の本体まで届かない (SDK が止める)。ok=false は本体が受け取って断る
  監査ログの「取りやめ」の行: 1 行 (c-4) = 本体まで届いた ok=false だけ
  監査ログの「確認を求めた」の行: 7 行 (c-1, c-2, c-3, c-4, e-1, e-2, c-9) = 断る・閉じたの答えは残らないが、確認を求めたことは確認の関数 (ask_confirm) が残す
```
