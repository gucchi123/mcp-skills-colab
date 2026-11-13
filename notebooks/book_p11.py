from build_notebooks import C, M, nb

BOOKS = {}

BOOKS["p11_defense.ipynb"] = nb("P11 本番で守る ― 攻撃を仕込んだデータ", "お客様窓口の下書き係に、指示を紛れ込ませた問い合わせ・規程・道具の説明を渡し、守れたかを「起きたこと」で判定します。", [
    (M, "## 1. 仕込んだ問い合わせを見る\n6 件のうち 5 件に指示を混ぜてあります (Q-906 は攻撃の無い対照)。どれも架空の文面です。"),
    (C, '''from common.injection import load_cases
for c in load_cases():
    print(f"{c['id']} ({c['customer']}, {c['channel']})")
    print("  " + c["text"].replace("\\n", " ")[:150])
    print("  してはいけない:", c["expect"]["must_not"] or "なし (対照)")'''),
    (M, "## 2. 窓口の下書き係を 2 件だけ動かす\nホストは kb・crm・inventory の 3 サーバにつなぎ、利用者はお客様窓口 (U-05)。判定は呼んだ道具・通った書き込み・返信に出た値で行います。"),
    (C, '''from run_defense import amain as defense
with safe():
    r = await defense(["--only", "Q-901,Q-903", "--show"])'''),
    (M, "## 3. 7 件まとめて (問い合わせ 6 件 + 規程 1 件)\n🛡 の行は、モデルが従っても仕組み (権限・確認・道具の絞り込み) が止めたものです。"),
    (C, '''with safe():
    r = await defense(["--all"])'''),
    (M, "## 4. 権限の広い人の名前で窓口を動かすと\n利用者を部長 (U-04) に替えます。同じ問い合わせでも、権限の層が止めていたものが止まらなくなります。"),
    (C, '''with safe():
    r = await defense(["--only", "Q-901,Q-905", "--user", "U-04"])'''),
    (M, "## 5. 窓口に要る道具だけを見せる (最小権限)\n規程の道具と「顧客 1 件を読む」だけを見せます。発注の道具は、モデルが名乗っても呼べません。"),
    (C, '''with safe():
    r = await defense(["--only", "Q-903,Q-905", "--tools", "least"])'''),
    (M, "## 6. 道具の説明を点検する\n道具の説明そのものに指示を隠す攻撃 (tool poisoning) の見本と、講座の 17 個の道具を同じ規則で点検します。規則で拾えるのは典型だけで、つなぐ前に全文を人が読むのが本筋です。"),
    (C, '''with safe():
    r = await defense(["--audit-tools"])'''),
    (M, "## 7. 監査ログを読む\n照会と操作はサーバの側で `state/audit.jsonl` に残ります。だれが・どの道具で・何を隠されたかが分かります。"),
    (C, '''import json, os
from common.kit import state_dir
p = os.path.join(state_dir(), "audit.jsonl")
rows = [json.loads(l) for l in open(p, encoding="utf-8")] if os.path.exists(p) else []
for e in rows[-8:]:
    print(e["at"], e["user"], e["server"], e["tool"], {k: v for k, v in e.items() if k in ("customer", "hidden", "product")})'''),
])
