from build_notebooks import C, M, nb

BOOKS = {}

BOOKS["p04_tool_design.ipynb"] = nb("P04 道具の設計 ― モデルは正しい道具を選べるか", "6 サーバ・17 個の道具を見せて、40 問それぞれで「最初に呼ぶ道具」を 1 回だけ選ばせ、正解と照合します。説明をあいまいにする・名前を番号にする・分野の道具だけ見せる、で何が変わるかを比べます。", [
    (M, "## 1. 問いを見る\n40 問のうち 38 問は「最初に呼ぶべき道具」が決まっていて、2 問は道具が要らない問いです。どれも架空の会社の問いです。"),
    (C, '''from collections import Counter
from tool_variants import load_questions, domain
qs = load_questions()
print("分野ごとの問いの数:", dict(Counter(domain(q) if q["first_tool"] else "道具なし" for q in qs)))
for q in qs[:2] + qs[12:13] + qs[-1:]:
    print(f"{q['id']} {q['question']}  → 最初の道具: {q['first_tool'] or '道具なし'}")'''),
    (M, "## 2. 道具の欄の大きさを見る\n道具の欄 (tools) は毎回の依頼に入るので、そのまま入力の量になります。4 通りの字数と、トークンの目安を比べます (本物の数は応答の usage で見ます)。"),
    (C, '''from run_tool_design import amain as tool_design
with safe():
    r = await tool_design(["--describe"])'''),
    (M, "## 3. 2 問だけ選ばせる\n1 問につき依頼を 1 回送り、応答の最初の tool_use だけを読みます。道具は実行しません。"),
    (C, '''with safe():
    r = await tool_design(["--only", "TS-01,TS-39", "--show"])'''),
    (M, "## 4. 40 問を元の説明で\n「最初の道具」が正解と同じ数・道具を使わなかった数・どの分野をどこと取り違えたか、を出します。外れた問いは 1 問ずつ表示します (△ = 期待とは違うが、データに理由つきで書いた別解)。"),
    (C, '''with safe():
    r = await tool_design(["--all", "--show"])'''),
    (M, "## 5. 4 通りを比べる\nあいまいな説明 (vague)・番号の名前 (names)・分野の道具だけ (subset) を、元の説明 (good) と並べます。mock の数字は性能の証拠になりません。"),
    (C, '''with safe():
    r = await tool_design(["--all", "--variant", "all"])'''),
    (M, "## 6. 同じ問いを 3 通りの見せ方で\n在庫・申請の状況・契約の一覧の問いを、元の説明・あいまいな説明・番号の名前で 1 問ずつ見ます。"),
    (C, '''with safe():
    r = await tool_design(["--only", "TS-13,TS-20,TS-27", "--variant", "good,vague,names", "--show"])'''),
    (M, "## 7. 講師の記録を読む\n本物の Claude で 4 通りを回した結果は `out/summary_compare.json` と `out/runs_compare.jsonl` に残します (まだ無ければ、その旨を表示します)。"),
    (C, '''import json, os
p = os.path.join("lab04_tool_design", "out", "summary_compare.json")
if not os.path.exists(p):
    print("講師の記録はまだありません (本物で回したらここに出ます)")
else:
    s = json.load(open(p, encoding="utf-8"))
    print("model:", s["model"], "/ 問い:", s["n_questions"])
    for v, x in s["variants"].items():
        print(f"  {v:<6} 最初の道具 {x['first_ok']}/{x['n']} (別解も正解なら {x.get('first_ok_also', x['first_ok'])}/{x['n']})"
              f"  道具なし {x['no_tool']}  入力トークン計 {x['usage_in_total']:,}")
    # 外れた問いと、別解とした理由 (データの why)
    qs = {}
    for ln in open(os.path.join("data", "questions", "tool_selection.jsonl"), encoding="utf-8"):
        q = json.loads(ln)
        qs[q["id"]] = q
    print("元の説明 (good) で外れた問い:")
    for ln in open(os.path.join("lab04_tool_design", "out", "runs_compare.jsonl"), encoding="utf-8"):
        r = json.loads(ln)
        if r["variant"] == "good" and not r["ok"]:
            q = qs[r["id"]]
            print(f"  {r['id']} {q['question'][:22]:<22} 期待 {r['expected']} → {r['pred'] or '道具なし (聞き返した)'}")
            print(f"       理由: {q.get('why', '(別解なし)')}")'''),
])
