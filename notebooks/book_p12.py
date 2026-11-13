from build_notebooks import C, M, nb

BOOKS = {}

BOOKS["p12_usecases.ipynb"] = nb("P12 業務に入れる ― 5 つの場面を正解と照合する", "架空のソラハ電機の 5 つの業務 (規程の問い合わせ・経費と発注の登録・顧客台帳の照会・月次レポート・契約書の一次レビュー) を最後まで流し、根拠・登録された記録・監査ログ・レポートの数字・総合の判定を、正解と機械で照合します。", [
    (M, "## 1. 5 つの場面と正解を見る\n場面ごとに、何を正解として照合するかが違います。規程の問い合わせの正解 7 問は、規程を読んで作りました。"),
    (C, '''from usecases import UC_TITLE, all_cases
what = {1: "根拠の文書番号と節", 2: "登録された記録 (state/*.jsonl)", 3: "見えた項目・隠れた項目・監査ログ",
        4: "レポートの数字 13 個", 5: "総合の判定と当たる項目"}
for uc, title in UC_TITLE.items():
    cs = all_cases(uc)
    print(f"UC{uc} {title}: {len(cs)} 件 ({cs[0]['id']} ほか) / 照合するもの: {what[uc]}")
k = all_cases(1)[3]
print(f"例 {k['id']} {k['q']} → 正解 {k['doc']} {k['sections'][0]}")'''),
    (M, "## 2. 規程の問い合わせ (kb)\n答えの最後の「根拠: 文書番号 節」が正解の節か、その節を道具で実際に見ていたか、を照合します。K-4 は検索の 1 位が改定履歴になる問いです。"),
    (C, '''from run_usecases import amain as usecases
with safe():
    r = await usecases(["--uc", "1", "--only", "K-1,K-4", "--show"])'''),
    (M, "## 3. 経費・発注の登録 (expense・inventory)\n登録の前に確認の画面が出ます。人の代わりの承認役は、画面の金額を依頼の伝票と見比べて決めます (PO-5 は予算を超えるので断る)。"),
    (C, '''with safe():
    r = await usecases(["--uc", "2", "--only", "EX-2,EX-3,PO-5"])'''),
    (M, "## 4. 顧客台帳の照会と権限 (crm)\n同じ問いを、担当営業 (U-01)・経理 (U-06)・情報システム (U-09) が聞きます。隠れた項目と監査ログを正解 (access_gold.json) と照合します。"),
    (C, '''with safe():
    r = await usecases(["--uc", "3", "--only", "U-01/C-001,U-06/C-001,U-09/C-001"])'''),
    (M, "## 5. 月次レポート (report + Skill)\nSkill の手順どおり、数字は道具から取り、計算は Skill のスクリプトで行います。レポートの数字 13 個を正解と照合します。"),
    (C, '''with safe():
    r = await usecases(["--uc", "4", "--only", "2026-08", "--show"])'''),
    (M, "## 6. 契約書の一次レビュー (contract + Skill)\n総合の判定は Skill のスクリプト (overall.py) が出します。判定と当たる項目を正解と照合します。"),
    (C, '''with safe():
    r = await usecases(["--uc", "5", "--only", "LC-05,LC-07"])'''),
    (M, "## 7. 手を抜く筋書きで、採点が間違いを拾うか\n検索の 1 位をそのまま引く・判定を確かめずに申請する・スクリプトを使わない、の 3 つ。採点の働きを見るため、ここだけ mock の筋書きで動かします (数字は Claude の性能の証拠にしない)。"),
    (C, '''with safe():
    r = await usecases(["--uc", "1,2,5", "--only", "K-4,EX-3,LC-05", "--provider", "mock", "--plan", "sloppy"])'''),
    (M, "## 8. 監査ログを読む\n顧客台帳の照会は、サーバの側で監査ログに残ります。だれが・どの顧客を・何を隠されたかを見ます。"),
    (C, '''import json, os
with safe():
    r = await usecases(["--uc", "3", "--only", "U-05/C-001,U-04/IND-002"])
    p = os.path.join(r["state_dir"], "audit.jsonl")
    for e in [json.loads(l) for l in open(p, encoding="utf-8")]:
        print(e["at"], e["user"], e["tool"], e.get("customer"), "隠した:", e.get("hidden"))'''),
])
