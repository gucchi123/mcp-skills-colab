---
name: solaha-monthly-report
description: ソラハ電機の月次レポート (売上・問い合わせ・在庫) を社内の型どおりに作る。ユーザーが「月次レポート」「今月の数字のまとめ」「◯月の振り返り」を頼んだときに使う。数字は report MCP サーバから取り、計算はスクリプトで行う。
license: MIT
compatibility: report MCP サーバ (get_monthly_sales / get_inquiry_counts / get_inventory_snapshot) と Python 3.10 以上が必要
metadata:
  owner: solaha-planning (架空)
  version: "1.0"
allowed-tools: Read Write Bash(python:*) mcp__report__get_monthly_sales mcp__report__get_inquiry_counts mcp__report__get_inventory_snapshot
---

# 月次レポート

## 手順

1. 対象の月を決める (YYYY-MM。2026-05〜2026-09。言われなければ最新の 2026-09)
2. report サーバの道具を 3 つ呼び、**返ってきた JSON をそのまま** ファイルに保存する (手で書き写さない・丸めない)
   - `get_monthly_sales(month)` → `sales.json`
   - `get_inquiry_counts(month)` → `inquiries.json`
   - `get_inventory_snapshot(month)` → `inventory.json`
3. スクリプトでレポートの 1〜3 節を作る。前月比や「いちばん伸びた製品」はスクリプトが計算する (自分で計算しない)
   ```
   python scripts/build_report.py sales.json inquiries.json inventory.json > report.md
   ```
   スクリプトが「🔴」で止まったら、数字の取り違え (月が違う・道具の返事が欠けている) なので、道具を呼び直す
4. 4 節「次の一手」は **人が書く節**。ここには数字から言えることの **候補** を 2〜3 個、「候補:」と付けて書く。断定しない
   - 書き方は `references/style.md` を読む

## してはいけないこと

- 道具が返していない数字を書かない (推測・記憶で埋めない)
- 1〜3 節の数字を言い換えたり丸め直したりしない
- 4 節を「結論」として書かない (判断するのは人)
