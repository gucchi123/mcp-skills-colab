# RUN_LOG ラボ 10

## 2026-10-24 つないで見るだけ (モデルを呼ばない・費用 0)

環境: Windows 11 (ARM64) / Python 3.13.14 / mcp 2.3.0 / claude-agent-sdk 0.2.174 / anthropic 2.3.0

```
$ python run_agent.py --probe
■ Claude Code (Agent SDK 同梱) 2.1.310 / 作業フォルダ lab10_mcp_x_skills/workspace
■ MCP サーバ
  report    connected  get_monthly_sales (読むだけ), get_inquiry_counts (読むだけ), get_inventory_snapshot (読むだけ)
  contract  connected  list_contracts (読むだけ), get_contract (読むだけ), get_contract_checklist (読むだけ)
  kb        connected  search_regulations (読むだけ), get_regulation (読むだけ)
  inventory connected  get_stock (読むだけ), list_below_reorder (読むだけ), create_purchase_order (書き込みあり)
■ Skill: 読み込んだ 2 本 / 常に文脈に載るのは名前と説明だけ = 111 トークン
  solaha-contract-review     64 トークン
  solaha-monthly-report      47 トークン
■ MCP の道具: 11 個・1669 トークン分は「必要になってから読む」(deferred)
  mcp__inventory__create_purchase_order     302 トークン
  mcp__kb__search_regulations               195 トークン
  mcp__report__get_monthly_sales            195 トークン
  mcp__kb__get_regulation                   139 トークン
```

読み取れること:
- Agent SDK (同梱の Claude Code) は mcp_servers に書いた 4 本の stdio サーバを起動してつないだ。道具の注釈 (読むだけ) も見えている
- Skill は名前と説明だけが常に文脈に載る (2 本で 111 トークン)。本文は使うときに読む = 段階的な読み込み
- MCP の道具 11 個 (1,669 トークン) は「必要になってから読む」(deferred) 扱い。道具が増えても毎回の文脈が膨らみにくい
- create_purchase_order は書き込みありなので allowed_tools に入れていない → 呼ぼうとすると can_use_tool に来る (本番の実行で確かめる)

```
$ python run_api.py --dry   (先頭だけ)
■ 1. Skills (GA) ― Skill はコード実行の箱の中で動く
{
 "model": "claude-opus-5-5",
 "max_tokens": 16000,
 "output_config": {
  "effort": "high"
 },
 "betas": [
  "code-execution-2025-08-25"
 ],
 "container": {
  "skills": [
```

## 本物のモデルで回した (2026-10-25・Claude のプランのログイン `--auth login`)

API クレジットが切れていたので、Agent SDK にキーを渡さず、同梱の CLI のログインで回した (このラボは中で Claude Code を
動かすので、キーでもログインでも中身は同じ。違うのは費用の欄が「API に換算した目安」になることだけ)。記録は `out/agent_<名前>.json`。

```
$ python run_agent.py --task report --month 2026-09 --run --auth login --name opus
■ report / model=claude-opus-5-5 / 利用者=U-02 / 15 ターン / 79.1 秒 / API 換算の目安 0.1541 USD (プランのログインで実行)
   → Skill {"skill": "solaha-monthly-report", "args": "2026-09"}
   → ToolSearch / mcp__report__get_monthly_sales / get_inquiry_counts / get_inventory_snapshot (2026-09)
   → Write sales.json / inquiries.json / inventory.json (道具の返事をそのまま保存)
   → PowerShell $env:PYTHONIOENCODING='utf-8'; python .claude/skills/solaha-monthly-report/scripts/build_report.py …
   ✅ 通した (Skill のスクリプトだけ) / ⛔ 断った: PowerShell のヒアドキュメントで 4 節を書き足す命令 (スクリプトではない)
   ✅ 通した (作業フォルダの中のファイル): Edit report.md  ← 4 節は Edit で書き足した
■ 答え合わせ (report.md): 数字の行 12/12 がスクリプトの出力と一致

$ python run_agent.py --task report --month 2026-09 --run --auth login --model claude-sonnet-5-5 --name sonnet
■ report / model=claude-sonnet-5-5 / 利用者=U-02 / 17 ターン / 69.2 秒 / API 換算の目安 0.0925 USD
   ⛔ 断った: 変数への代入から始まる命令 / ✅ 通した: スクリプトだけの命令 / ✅ 通した: Edit report_2026-09\report.md
■ 答え合わせ (report_2026-09\report.md): 数字の行 12/12 がスクリプトの出力と一致

$ python run_agent.py --task order --run --auth login --name order
■ order / model=claude-opus-5-5 / 利用者=U-02 / 3 ターン / 40.8 秒 / API 換算の目安 0.0985 USD
   → mcp__inventory__list_below_reorder {}
🤖 発注点以下は 15 件 (データと一致)。発注は登録の前に確認が要るので、まだ 1 件も登録していない。14 件の発注案 (合計
   12,162,400 円) と、発注先が取引停止で代わりも無い M-405 は発注できない、を示して確認を求めた
■ 書き込みの道具 (create_purchase_order) は一度も呼ばなかった → can_use_tool まで来ていない
```

### 本物で回して分かったこと (ラボを直した点)

1. **Windows の Claude Code はシェルに PowerShell を使う**。SKILL.md の `allowed-tools: Bash(python:*)` は当たらず、スクリプトの
   実行が can_use_tool に回ってきて断られた (最初の実行 `out/agent_opus_blocked.json`: 0/12。モデルは止まった理由を説明し、
   人に手順を渡した = 振る舞いとしては正しい)。
2. 最初に入れた判定 (コマンドの形を正規表現で見る) は、`| Out-File -Encoding utf8 report.md`・`cd サブフォルダ`・`.\` 付きの
   パスなど、まっとうな書き方を断った。→ **`check_shell`**: `;` と `|` で区切って一つずつ読み、`cd` も追いながら **パスを実際に
   解決して** 作業フォルダの中かを見る形に変えた。命令の合成 (`&` `$(` など) は通さない。試験は `test_shell_allows_only_skill_scripts`
   (本物で誤って断ったコマンドを含む)。
3. 断るときの文言が「書き込みは人が行う」だけだと、モデルは「ファイルに残すのも禁止」と受け取り、レポートを返答に貼るだけで
   終わった (その回は返答の言い回しが変わり 9/12)。→ 断る理由と「何なら通るか」を返す文言にした。
4. 作業フォルダの中のファイルの編集 (Edit) が断られ、4 節を書き足せなかった。→ **`check_file_edit`**: 作業フォルダの中
   (`.claude/` を除く) だけ通す。
5. 在庫を読む道具 (`get_stock`・`list_below_reorder`) が許可のリストに無く、発注の作業で読むことすらできなかった。→ `READ_ONLY_TOOLS`
   に足した (書き込みの `create_purchase_order` は入れない)。

### まだ

- `run_api.py --run --name opus` (Skills API) は API キーとクレジットが要る (ログインでは呼べない)。クレジットの補充後
