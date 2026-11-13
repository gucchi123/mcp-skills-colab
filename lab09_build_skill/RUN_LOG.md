# RUN_LOG ラボ 9

🔴 このラボの記録は mock と、Claude を呼ばない読み込み係だけです。本物のモデルでは回していません。

予定するコマンド (provider=anthropic → 同じものを replay で回して出力が同じことを確かめる):
- `--part trigger --all --name std` / `--part trigger --all --variant vague --name vague` (説明文で発動がどう変わるか)
- `--all --name e2e` (5 か月。数字 13 個 × 5 と手順の抜け)
- 見どころ: 境界の問い (T-08・T-09・T-15 は語が無い、T-16・T-17・T-20 は語があるが使わない) で本物がどう振る舞うか

---

以下は **mock の出力** (配線の確認)。記録日 2026-10-24、Python 3.13.14 / mcp 2.3.0、`PYTHONUTF8=1 LLM_NO_KEY=1 ANTHROPIC_API_KEY=`。
🔴 mock は講師が書いた筋書き (問いの語で選ぶ・手順どおり進む)。適合率・再現率・一致の数は性能の証拠ではない。

## 読み込み係 (Claude を呼ばない。これは本物の動き)

```
$ python lab09_build_skill/run_build_skill.py --part loader
■ モデルに見せる道具: MCP 3 個 + 読み込み係 load_skill, read_skill_file, run_skill_script
■ システムプロンプト 444 字 (スキルの一覧は name と description だけ = 段階 1)
■ 道具を直接呼んでみる (9 回。✓ 通った / ✗ 断った)
  ✓ load_skill {'name': 'solaha-monthly-report'}
      → # 月次レポート
  ✓ read_skill_file {'path': 'references/style.md'}
      → # 月次レポートの書き方 (ソラハ電機・架空)
  ✓ run_skill_script {'script': 'overall.py', 'input_json': {'args': ['[{"rule"
      → 法務室レビュー必須
  ✗ load_skill {'name': 'hr-leave-request'}
      → スキル 'hr-leave-request' はありません。ある名前: solaha-contract-review, solaha-monthly-r
  ✗ read_skill_file {'path': '../../common/llm.py'}
      → スキルのフォルダの外は読めません: ../../common/llm.py
  ✗ read_skill_file {'path': '../solaha-contract-review/SKILL.md'}
      → スキルのフォルダの外は読めません: ../solaha-contract-review/SKILL.md
  ✗ run_skill_script {'script': '../../../common/llm.py'}
      → スキルのフォルダの外は読めません: ../../../common/llm.py
  ✗ run_skill_script {'script': 'overall.py', 'input_json': {'args': ['[]; del 
      → スクリプトが終了コード 1 で止まった: json.decoder.JSONDecodeError: Extra data: line 1 column
  ✗ run_skill_script {'script': 'overall.py', 'input_json': {'args': [], 'files
      → ファイル名は英数字と ._- だけ: '../escape.json'
→ 思ったとおり 9/9
```

## 発動の試験 20 問 (mock・筋書き keyword)

```
$ python lab09_build_skill/run_build_skill.py --part trigger --all --provider mock
■ 発動の試験 / provider=mock (筋書き keyword) / 説明文=standard / 20 問
  🔴 mock は問いの語だけで選び、説明文を読まない。数字は配線の確認で、性能の証拠ではない
  ✓ T-01 2026-09 の月次レポートを作ってください。           期待 monthly-report  → monthly-report
  ✓ T-02 8 月の振り返りを社内の型でまとめて。               期待 monthly-report  → monthly-report
  ✓ T-03 今月の数字のまとめをお願いします。                 期待 monthly-report  → monthly-report
  ✓ T-04 7 月分の月次レポート、部長に出す版を作って。       期待 monthly-report  → monthly-report
  ✓ T-05 2026-06 の売上・問い合わせ・在庫をレポー           期待 monthly-report  → monthly-report
  ✓ T-06 先月 (2026-08) の振り返り資料を作りた              期待 monthly-report  → monthly-report
  ✓ T-07 5 月の月次の報告書を下書きして。                   期待 monthly-report  → monthly-report
  ✗ T-08 9 月はどうだった？売上と問い合わせと在庫を一通     期待 monthly-report  → なし
  ✗ T-09 経営会議用に 2026-07 の数字を型どおりに            期待 monthly-report  → なし
  ✓ T-10 6 月の月次をまとめて、次の一手の候補も付けて。     期待 monthly-report  → monthly-report
  ✓ T-11 LC-03 をレビューしてください。                     期待 contract-review → contract-review
  ✓ T-12 この部品供給の契約書、法務に回すべき？             期待 contract-review → contract-review
  ✓ T-13 LC-07 のリスクを洗い出して。                       期待 contract-review → contract-review
  ✓ T-14 新しい保守契約の一次レビューをお願いします。       期待 contract-review → contract-review
  ✗ T-15 取引先から届いた NDA に問題がないか見て。          期待 contract-review → なし
  ✓ T-16 9 月の売上でいちばん売れた製品は？                 期待 なし            → なし
  ✗ T-17 週報レポートの提出期限はいつ？                     期待 なし            → monthly-report
  ✓ T-18 経費精算の上限はいくら？                           期待 なし            → なし
  ✓ T-19 TL-200 の電池の交換時期は？                        期待 なし            → なし
  ✗ T-20 契約社員の有給は何日？                             期待 なし            → contract-review
→ monthly-report: 適合率 8/9・再現率 8/10
→ contract-review: 適合率 4/5・再現率 4/5
→ スキル無しが正しい問い: 3/5 で読まなかった
```

## 月次レポートを最後まで 5 か月 (mock・筋書き follow)

```
$ python lab09_build_skill/run_build_skill.py --all --provider mock
■ 月次レポートを最後まで / provider=mock (筋書き follow) / 5 か月
  2026-05: 数字 13/13 が正解と一致 / 手順 ✓load_skill_first ✓report_tools_3 ✓script_ok ✓style_read ✓candidates
  2026-06: 数字 13/13 が正解と一致 / 手順 ✓load_skill_first ✓report_tools_3 ✓script_ok ✓style_read ✓candidates
  2026-07: 数字 13/13 が正解と一致 / 手順 ✓load_skill_first ✓report_tools_3 ✓script_ok ✓style_read ✓candidates
  2026-08: 数字 13/13 が正解と一致 / 手順 ✓load_skill_first ✓report_tools_3 ✓script_ok ✓style_read ✓candidates
  2026-09: 数字 13/13 が正解と一致 / 手順 ✓load_skill_first ✓report_tools_3 ✓script_ok ✓style_read ✓candidates
→ 数字が全部合った 5/5 か月・手順の抜け なし
```

照合が本物であることは試験で確かめている (`tests/test_run_build_skill.py` の test_check_catches_changed_numbers: レポートの売上合計を 1,000 円書き換えると revenue_total が「違う」と出る)。
