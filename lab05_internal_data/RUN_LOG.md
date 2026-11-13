# RUN_LOG ラボ 5

- 記録日: 2026-10-24 / Python 3.13.14 / mcp 2.3.0 (プロトコル 2026-07-28) / Windows 11
- Claude は呼んでいない (このラボは LLM を使わない。サーバに MCP の Client で同じプロセスのまま直接つないだ)
- 環境変数: `PYTHONUTF8=1`・`LLM_NO_KEY=1`・`ANTHROPIC_API_KEY=` (空)。キットの根で実行
- 書き込み先は実行ごとの一時フォルダ (キットの state/ は使っていない)

## `python lab05_internal_data/run_internal_data.py --name teacher`

```text
■ 1. 資料 (resource) と資料のひな形 (resource template)
  crm       資料: crm://policy (顧客情報取扱規程)
            道具: find_customer, get_customer, list_customers_by_product
  kb        資料: kb://regulations/{doc_id} (社内規程・ひな形)
            道具: search_regulations, get_regulation
  inventory 資料: inventory://purchase_policy (購買規程)
            道具: get_stock, list_below_reorder, create_purchase_order
  report    資料: report://template (月次レポートの型)
            道具: get_monthly_sales, get_inquiry_counts, get_inventory_snapshot

■ crm://policy を読む (text/markdown・33 行)
  # 顧客情報取扱規程（ソラハ電機株式会社・架空）
  ## 第3条 法人の顧客
  3. 先方担当者は、その顧客の担当営業と、営業部の課長以上が見てよい。お客様窓口の社員は、先方担当者の氏名と電話だけを見てよい（メールは見ない）。

■ kb://regulations/a-05 を読む (ひな形の {doc_id} に a-05 を入れた URI・41 行)
  # 経費精算手続き
  ## 1. 目的
  ## 2. 対象
  ## 3. 申請期限
  ## 4. 手続きの流れ
  無い番号 kb://regulations/zz → MCPError: Error creating resource from template kb://regulations/zz
    (サーバの ToolError の文「文書 zz はありません」は、資料の読み出しでは利用者に届かない)

  資料を 3 回読んだあとの監査ログの行: 0 → 0 (資料の読み出しはサーバが記録していない)

■ 使い分け
  資料: アプリや人が選んで文脈に入れる・URI で指す・だれが読んでも同じ中身 (規程・型・方針)
  道具: モデルが判断して呼ぶ・引数で探す/計算する・利用者で中身が変わる・監査が要る (顧客 1 件・数字)
  このキットの Host はモデルに道具だけを渡す。だから kb は同じ規程を道具 get_regulation でも出している

■ 2. get_customer C-002 (法人・担当営業 U-02) を 9 人の名前で呼ぶ  〇=見える －=（非表示）
  利用者                会社名 ランク 与信枠 担当者 電話 メール 隠した数
  U-01 山根(営業一般)   〇     －     －     －     －   －     5
  U-02 石黒(営業課長)   〇     〇     〇     〇     〇   〇     0
  U-03 矢野(営業副部長) 〇     〇     〇     〇     〇   〇     0
  U-04 田村(営業部長)   〇     〇     〇     〇     〇   〇     0
  U-05 坂口(窓口)       〇     －     －     〇     〇   －     3
  U-06 中西(経理一般)   〇     〇     〇     －     －   －     3
  U-07 早瀬(経理課長)   〇     〇     〇     －     －   －     3
  U-08 槙野(法務室長)   〇     －     －     －     －   －     5
  U-09 西村(情報一般)   〇     －     －     －     －   －     5
  例) U-01 に返った hidden: ['rank', 'credit_limit_yen', 'contact.name', 'contact.phone', 'contact.email']
      U-01 に返った contact: {"name": "（非表示）", "phone": "（非表示）", "email": "（非表示）"}
■ 2. get_customer IND-001 (個人・担当営業 なし) を 9 人の名前で呼ぶ  〇=見える －=（非表示）
  利用者                氏名 連絡先氏名 電話 メール 住所 隠した数
  U-01 山根(営業一般)   －   －         －   －     －   5
  U-02 石黒(営業課長)   －   －         －   －     －   5
  U-03 矢野(営業副部長) －   －         －   －     －   5
  U-04 田村(営業部長)   －   －         －   －     －   5
  U-05 坂口(窓口)       〇   〇         〇   〇     〇   0
  U-06 中西(経理一般)   －   －         －   －     －   5
  U-07 早瀬(経理課長)   －   －         －   －     －   5
  U-08 槙野(法務室長)   －   －         －   －     －   5
  U-09 西村(情報一般)   －   －         －   －     －   5
  例) U-01 に返った hidden: ['name', 'contact.name', 'contact.phone', 'contact.email', 'contact.address']
      U-01 に返った contact: {"name": "（非表示）", "phone": "（非表示）", "email": "（非表示）", "address": "（非表示）"}
→ 規程の正解 (data/crm/access_gold.json) と一致: 18/18 組

■ 3. 監査ログ lab05_state_mrnk07a6/audit.jsonl に足された行 (4 行)
  19:14:53 U-01 crm.get_customer {"customer": "C-002", "hidden": ["rank", "credit_limit_yen", "contact.name", "contact.phone", "contact.email"]}
  19:14:53 U-05 crm.get_customer {"customer": "IND-001", "hidden": []}
  19:14:53 U-09 crm.get_customer {"customer": "C-002", "hidden": ["rank", "credit_limit_yen", "contact.name", "contact.phone", "contact.email"]}
  19:14:53 U-02 crm.find_customer {"query": "フーズ", "returned": ["C-002"]}
  利用者なしの呼び出し → is_error=True: Error executing tool get_customer: 利用者が決まっていません (SOLAHA_USER が空) (顧客を読む前に止まり、ログにも残らない)
  ログに残るのは「だれが・どの顧客を・どの項目を隠されたか」。値そのもの (メールなど) は書かない

■ 4. 一覧のキャッシュの目安 (結果に付く ttl_ms / cache_scope) と、読むだけの印
  サーバ       tools/list          resources/list      読むだけの道具
  crm       300,000 public      0 private           3/3
  kb        300,000 public      300,000 public      2/2
  inventory 0 private           0 private           2/3
  report    300,000 public      0 private           3/3
  expense   0 private           0 private           2/3
  ttl_ms=300,000 は「5 分は一覧を取り直さなくてよい」。public は利用者をまたいで使い回してよい
  cache_hints を書かないサーバ (inventory・expense) は 0 private = 使い回さない (SDK の既定)
  読むだけの印 (read_only_hint) はヒント。守りは道具の中 (出し分け・確認) で行う

■ 5. report サーバの数字を正解 (data/report/gold_numbers.json) と照合
  月                売上合計     前月比  1位         問合せ  在庫割れ                照合
  2026-05    28,120,000    4.2%  TL-200      86  M-401,P-102,P-107       ✓
  2026-06    28,903,000    2.8%  TL-200      81  M-401,P-104             ✓
  2026-07    29,096,000    0.7%  TL-200      73  P-104,P-107             ✓
  2026-08    29,269,000    0.6%  TL-200     110  P-107                   ✓
  2026-09    30,784,000    5.2%  TL-200      80  M-401,M-403,P-102,P-104 ✓
  無い月 2025-01 → is_error=True: Error executing tool get_monthly_sales: 2025-01 の数字はありません。ある月: 2026-04〜2026-09
→ 5/5 か月が一致。足し算・前月比はサーバが計算して返す (モデルにさせない)
```

## `python lab05_internal_data/run_internal_data.py --only visibility --all`

```text
→ 規程の正解 (data/crm/access_gold.json) と一致: 189/189 組
```

## 読み取れること

- 規程の出し分けは 9 人 × 21 社 = 189 組すべてで正解 (access_gold.json) と一致。表示の 18 組 (C-002・IND-001) も一致
- 個人のお客様 (IND-001) の氏名・連絡先は窓口 (U-05) だけ。部長 (U-04) でも見えない。情報システム部 (U-09) は会社名だけ
- 監査ログには利用者・道具・顧客番号・隠した項目の名前が残り、値そのもの (メール・電話) は書かれない
- 利用者が決まらない呼び出しは道具の結果がエラーになり、監査ログにも残らない
- 資料 (crm://policy・kb://regulations/a-05) を読んでも監査ログは増えない (サーバが資料の読み出しを記録していない)
- 月次の数字は 5 か月とも正解 (gold_numbers.json) と一致

## mcp 2.3.0 で気づいたこと (実際に回して確かめた)

- 資料のひな形の関数が `ToolError` を投げても、利用者に届くのは `MCPError: Error creating resource from template kb://regulations/zz` だけ。
  サーバの文 (「文書 zz はありません」) は消え、サーバのログにはトレースバックが出る (このラボではログを黙らせている)
- `cache_hints` を書かないサーバの一覧は `ttl_ms=0`・`cache_scope=private` (SDK の既定)。
  crm は `tools/list` だけに付けているので、`resources/list` は 0 private のまま
- 同じプロセスの Client では、`set_user` を Client を開いた後に変えても次の呼び出しに効いた (ラボでは利用者ごとに Client を開き直している)
