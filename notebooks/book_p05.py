from build_notebooks import C, M, nb

BOOKS = {}

BOOKS["p05_internal_data.ipynb"] = nb("P05 社内データをつなぐ ― 安全に読む", "顧客台帳・規程・在庫・月次の数字のサーバに MCP の Client で直接つなぎ、資料と道具の違い・利用者ごとの出し分け・監査ログ・キャッシュの目安・数字の照合を確かめます。", [
    (M, "## 1. 資料 (resource) と道具 (tool)\n4 つのサーバの資料・資料のひな形・道具を並べ、`crm://policy` と `kb://regulations/a-05` を読みます。どちらにするかの使い分けも最後に出します。"),
    (C, '''from run_internal_data import amain as internal
with safe():
    r = await internal(["--only", "resources"])'''),
    (M, "## 2. 利用者ごとの出し分け\n同じ `get_customer` を 9 人の名前で呼びます。法人 C-002 と個人 IND-001 で、だれにどの項目が見えるかを表にします。隠すのはサーバの側 (`common/policy.py`) です。"),
    (C, '''with safe():
    r = await internal(["--only", "visibility", "--customer", "C-002,IND-001"])'''),
    (M, "## 3. 21 社すべてを規程の正解と照合\n9 人 × 21 社 = 189 組を、規程から作った正解 (`data/crm/access_gold.json`) と突き合わせます。"),
    (C, '''with safe():
    r = await internal(["--only", "visibility", "--all"])'''),
    (M, "## 4. 監査ログ\n照会はサーバの側で `audit.jsonl` に 1 行ずつ残ります。だれが・どの顧客の・どの項目を隠されたか。書き込み先は実行ごとの一時フォルダです。"),
    (C, '''with safe():
    r = await internal(["--only", "audit"])'''),
    (M, "## 5. 一覧のキャッシュの目安\n`tools/list` などの結果に付く `ttl_ms` と `cache_scope` を、サーバごとに見ます。読むだけの印 (read_only_hint) の数も並べます。"),
    (C, '''with safe():
    r = await internal(["--only", "cache"])'''),
    (M, "## 6. 読むだけの数字を正解と照合\n月次の売上・問い合わせ・在庫割れを report サーバから取り、正解 (`data/report/gold_numbers.json`) と照合します。"),
    (C, '''with safe():
    r = await internal(["--only", "report"])'''),
])
