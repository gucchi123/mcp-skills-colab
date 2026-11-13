# -*- coding: utf-8 -*-
"""LangGraph 講座の架空データを作る (決定的。LLM は使わない)。

🔴 登場する会社・人物・製品・取引先・数値・文書はすべて架空です。実在の企業・団体・個人とは関係ありません。
   会社は GraphRAG 講座と同じ架空の「ソラハ電機株式会社」。人物・製品・取引先の名前も GraphRAG 講座のデータに合わせています。

作るもの (data/ の下):
  expense/   経費精算  : policy.md・claims.json (42 件・正解つき)
  inquiry/   問い合わせ: faq.md・inquiries.jsonl (60 件・正解つき)
  contract/  契約書    : checklist.md・LC-01〜08.md・gold_findings.json
  inventory/ 発注・在庫: inventory.csv (30 品目)・suppliers.csv・purchase_policy.md・requests.json (10 件・正解つき)
  report/    月次レポート: sales.csv・inquiries_monthly.csv・inventory_monthly.csv (6 か月)・template.md・gold_numbers.json
  questions/ 評価用の問い: expense.jsonl など 5 本 (各 10 問・正解と期待する手順)

正解 (gold) は、規程に書いた規則をこのファイルの関数で当てはめて決めています。
check_data.py が規則を別に実装し直して、正解と食い違いがないかを確かめます。

usage: python make_data.py
"""
import csv, datetime as dt, json, math, os, random, sys

if hasattr(sys.stdout, "reconfigure"):   # Jupyter の出力先には無い
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 20261018
COMPANY = "ソラハ電機株式会社"


def out(*p):
    path = os.path.join(HERE, *p)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def wjson(obj, *p):
    with open(out(*p), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def wjsonl(rows, *p):
    with open(out(*p), "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def wtext(text, *p):
    with open(out(*p), "w", encoding="utf-8", newline="\n") as f:
        f.write(text.strip() + "\n")


def wcsv(rows, fields, *p):
    with open(out(*p), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


# =====================================================================================
# 人 (GraphRAG 講座の a_regulations と同じ名前。一般社員は本講座で足した)
# =====================================================================================
PEOPLE = {
    "宮下 玲子": ("管理本部", "本部長"), "柴田 恭平": ("事業本部", "本部長"),
    "森川 直人": ("経理部", "部長"), "早瀬 美咲": ("経理部", "課長"),
    "河合 智子": ("人事部", "部長"), "吉岡 拓也": ("人事部", "課長"),
    "桐生 誠": ("情報システム部", "部長"), "二宮 彩": ("情報システム部", "課長"),
    "田村 浩二": ("営業部", "部長"), "矢野 由香": ("営業部", "副部長"), "石黒 慎": ("営業部", "課長"),
    "大森 剛": ("製造部", "部長"), "平井 恵": ("製造部", "課長"),
    "白石 学": ("開発部", "部長"), "三浦 遥": ("開発部", "課長"),
    # 本講座で足した一般社員 (架空)
    "山根 翔太": ("営業部", "一般"), "久保 紗希": ("製造部", "一般"), "岡田 悠真": ("開発部", "一般"),
    "中西 葵": ("経理部", "一般"), "堀 陽菜": ("人事部", "一般"), "西村 蓮": ("情報システム部", "一般"),
}

# =====================================================================================
# 1. 経費精算
# =====================================================================================
HOLIDAYS_2026 = {dt.date(2026, 9, 21), dt.date(2026, 9, 22), dt.date(2026, 9, 23)}  # 敬老の日・国民の休日・秋分の日
AUTO_LIMIT = 10_000
RECEIPT_FROM = 3_000
LADDER = ["一般", "課長", "副部長", "部長", "本部長", "代表取締役社長"]
APPROVER_LEVELS = ["課長", "部長", "本部長", "代表取締役社長"]

EXPENSE_POLICY = f"""
# 経費精算規程（{COMPANY}・架空）

> この規程は講座用の架空のものです。実在の会社の規程ではありません。

## 第1条 申請の期限
経費は、発生した月の翌月10日までに申請する。期限を過ぎた申請は、経理部の確認を受ける。

## 第2条 費目ごとの上限
| 費目 | 上限 | 上限を超えたとき |
|---|---|---|
| 交通費 | 1件 30,000円 | 経理部の確認を受ける |
| 宿泊費 | 1泊 12,000円（部長以上は 15,000円） | 差し戻し |
| 会議費（社内） | 1人あたり 1,500円 | 差し戻し |
| 接待交際費 | 1人あたり 10,000円。**事前申請（PA 番号）が必須** | 差し戻し |
| 書籍費 | 1件 10,000円 | 差し戻し |
| 消耗品費 | 1件 100,000円未満 | 10万円以上は固定資産のため経費精算では扱わない（稟議へ）。差し戻し |

## 第3条 領収書
1件 3,000円以上の経費には領収書を添付する。ただし交通費で交通系ICカードの利用履歴（IC 履歴）を添付したものは領収書に代えてよい。
領収書が無い申請は差し戻す。

## 第4条 休日の経費
会議費・接待交際費・消耗品費のうち、土曜・日曜・祝日に発生したものは、業務上の理由を経理部が確認する。

## 第5条 分割申請の禁止
同じ人が、同じ日に、同じ支払先への支払いを複数の申請に分けてはならない。分けた申請はすべて差し戻し、合算して申請し直す。

## 第6条 承認
1. 1件 {AUTO_LIMIT:,}円以下で、第1条〜第5条に当たらない申請は、システムで自動承認する。
2. {AUTO_LIMIT:,}円を超える申請は、次の承認者が承認する。
   | 金額 | 承認者 |
   |---|---|
   | 5万円以下 | 課長 |
   | 50万円以下 | 部長 |
   | 300万円以下 | 本部長 |
   | 300万円超 | 代表取締役社長 |
3. 承認者は申請者より上の職位でなければならない。上の表の承認者が申請者と同じ職位か下の職位のときは、申請者より上の職位のうち、上の表にある職位（課長・部長・本部長・代表取締役社長）でいちばん下の者が承認する。副部長は承認者にならない（例: 課長の申請は部長が承認する）。
   職位の順は、一般 ＜ 課長 ＜ 副部長 ＜ 部長 ＜ 本部長 ＜ 代表取締役社長。

## 第7条 判定の順序
差し戻しに当たる事由があれば差し戻す（事由はすべて挙げる）。差し戻しに当たらず、経理部の確認に当たる事由があれば経理部の確認に回す。
どちらにも当たらなければ、第6条により自動承認または承認者の承認に回す。
"""


def exp_approver_by_amount(amount):
    man = amount / 10_000
    if man <= 5:
        return "課長"
    if man <= 50:
        return "部長"
    if man <= 300:
        return "本部長"
    return "代表取締役社長"


def exp_approver(amount, applicant_pos):
    by_amount = exp_approver_by_amount(amount)
    if LADDER.index(by_amount) > LADDER.index(applicant_pos):
        return by_amount
    # 一つ上の職位 (副部長は承認者の表に無いので、その上の部長へ。2026-10-18: 規程の文にも明記した)
    for lv in LADDER[LADDER.index(applicant_pos) + 1:]:
        if lv in APPROVER_LEVELS:
            return lv
    return "代表取締役社長"


def exp_deadline(expense_date):
    y, m = expense_date.year, expense_date.month
    y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return dt.date(y, m, 10)


def exp_judge(c, all_claims):
    """規程 (第1〜7条) を当てはめる。戻り値: (decision, reasons, approver)"""
    ed = dt.date.fromisoformat(c["expense_date"])
    sd = dt.date.fromisoformat(c["submitted"])
    cat, amt = c["category"], c["amount"]
    pos = PEOPLE[c["employee"]][1]
    rej, fin = [], []
    # 第2条
    if cat == "宿泊費":
        cap = 15_000 if LADDER.index(pos) >= LADDER.index("部長") else 12_000
        if amt / c["nights"] > cap:
            rej.append("宿泊費の1泊あたり上限超過")
    if cat == "会議費" and amt / c["attendees"] > 1_500:
        rej.append("会議費の1人あたり上限超過")
    if cat == "接待交際費":
        if not c.get("pre_approval"):
            rej.append("接待交際費の事前申請なし")
        if amt / c["attendees"] > 10_000:
            rej.append("接待交際費の1人あたり上限超過")
    if cat == "書籍費" and amt > 10_000:
        rej.append("書籍費の上限超過")
    if cat == "消耗品費" and amt >= 100_000:
        rej.append("10万円以上は固定資産（稟議へ）")
    if cat == "交通費" and amt > 30_000:
        fin.append("交通費の上限超過")
    # 第3条
    if amt >= RECEIPT_FROM and not c["receipt"] and not (cat == "交通費" and c.get("ic_record")):
        rej.append("領収書なし")
    # 第5条
    same = [o for o in all_claims if o["id"] != c["id"] and o["employee"] == c["employee"]
            and o["vendor"] == c["vendor"] and o["expense_date"] == c["expense_date"]]
    if same:
        rej.append("分割申請（合算して申請し直す）")
    # 第1条
    if sd > exp_deadline(ed):
        fin.append("申請期限（翌月10日）超過")
    # 第4条
    if cat in ("会議費", "接待交際費", "消耗品費") and (ed.weekday() >= 5 or ed in HOLIDAYS_2026):
        fin.append("休日に発生した経費")
    if rej:
        return "reject", rej, None
    if fin:
        return "needs_finance", fin, None
    if amt <= AUTO_LIMIT:
        return "auto_approve", [], None
    return "needs_manager", [], exp_approver(amt, pos)


# (id, 申請者, 費目, 発生日, 申請日, 金額, 人数, 泊数, 領収書, IC履歴, 事前申請, 支払先, 内容, 期待する判定)
# 期待する判定は人が決めたもの。生成時に規則の当てはめ結果と一致することを確かめる (食い違えば止まる)。
CLAIMS = [
    ("E-01", "山根 翔太", "交通費", "2026-09-03", "2026-10-02", 1_280, None, None, False, True, None, "東都メトロ", "客先訪問（往復）", "auto_approve"),
    ("E-02", "山根 翔太", "会議費", "2026-09-08", "2026-10-02", 5_200, 4, None, True, False, None, "カフェ・ソレイユ", "営業会議の飲料", "auto_approve"),
    ("E-03", "久保 紗希", "消耗品費", "2026-09-09", "2026-10-01", 8_800, None, None, True, False, None, "ミナト電材", "はんだと工具", "auto_approve"),
    ("E-04", "岡田 悠真", "書籍費", "2026-09-10", "2026-10-03", 4_620, None, None, True, False, None, "青林書店", "グラフ理論の専門書", "auto_approve"),
    ("E-05", "山根 翔太", "宿泊費", "2026-09-15", "2026-10-02", 11_800, None, 1, True, False, None, "ホテル川越ステイ", "工場立会いの宿泊", "needs_manager"),
    ("E-06", "山根 翔太", "宿泊費", "2026-09-16", "2026-10-02", 13_500, None, 1, True, False, None, "ホテル大崎グラン", "第二工場訪問の宿泊", "reject"),
    ("E-07", "田村 浩二", "宿泊費", "2026-09-16", "2026-10-05", 14_300, None, 1, True, False, None, "ホテル大崎グラン", "第二工場訪問の宿泊", "needs_manager"),
    ("E-08", "吉岡 拓也", "接待交際費", "2026-09-17", "2026-10-06", 27_000, 3, None, True, False, "PA-0912", "割烹みなせ", "採用協力会社との会食", "needs_manager"),
    ("E-09", "石黒 慎", "接待交際費", "2026-09-18", "2026-10-06", 18_400, 2, None, True, False, None, "ビストロ汐留", "顧客との会食", "reject"),
    ("E-10", "矢野 由香", "接待交際費", "2026-09-24", "2026-10-07", 48_000, 4, None, True, False, "PA-0920", "料亭たちばな", "顧客との会食", "reject"),
    ("E-11", "山根 翔太", "会議費", "2026-09-25", "2026-10-07", 10_800, 6, None, True, False, None, "仕出し弁当ひなた", "社内会議の弁当", "reject"),
    ("E-12", "久保 紗希", "消耗品費", "2026-09-26", "2026-10-05", 6_400, None, None, True, False, None, "ミナト電材", "治具の部材", "needs_finance"),
    ("E-13", "岡田 悠真", "消耗品費", "2026-09-29", "2026-10-06", 128_000, None, None, True, False, None, "テクノ機材センター", "計測用オシロスコープ", "reject"),
    ("E-14", "岡田 悠真", "消耗品費", "2026-09-30", "2026-10-06", 2_480, None, None, False, False, None, "コンビニ北口店", "電池", "auto_approve"),
    ("E-15", "西村 蓮", "消耗品費", "2026-09-30", "2026-10-06", 5_980, None, None, False, False, None, "ミナト電材", "LANケーブル", "reject"),
    ("E-16", "山根 翔太", "交通費", "2026-09-04", "2026-10-02", 8_640, None, None, False, False, None, "東都タクシー", "客先からの帰社", "reject"),
    ("E-17", "山根 翔太", "交通費", "2026-09-11", "2026-10-02", 34_200, None, None, True, False, None, "東北新幹線", "第二工場への出張（往復）", "needs_finance"),
    ("E-18", "堀 陽菜", "書籍費", "2026-09-12", "2026-10-03", 12_100, None, None, True, False, None, "青林書店", "労務管理の書籍2冊", "reject"),
    ("E-19", "中西 葵", "交通費", "2026-08-27", "2026-10-05", 1_960, None, None, False, True, None, "東都メトロ", "銀行への往復", "needs_finance"),
    ("E-20", "久保 紗希", "消耗品費", "2026-08-20", "2026-09-30", 22_000, None, None, True, False, None, "ミナト電材", "作業台の部品", "needs_finance"),
    ("E-21", "西村 蓮", "消耗品費", "2026-09-17", "2026-10-06", 9_800, None, None, True, False, None, "ミナト電材", "ネットワーク機器の部材（1）", "reject"),
    ("E-22", "西村 蓮", "消耗品費", "2026-09-17", "2026-10-06", 9_600, None, None, True, False, None, "ミナト電材", "ネットワーク機器の部材（2）", "reject"),
    ("E-23", "平井 恵", "消耗品費", "2026-09-18", "2026-10-06", 46_000, None, None, True, False, None, "テクノ機材センター", "検査工具一式", "needs_manager"),
    ("E-24", "大森 剛", "消耗品費", "2026-09-18", "2026-10-06", 86_000, None, None, True, False, None, "テクノ機材センター", "ライン用の工具一式", "needs_manager"),
    ("E-25", "白石 学", "交通費", "2026-09-07", "2026-10-02", 28_600, None, None, True, False, None, "東海道新幹線", "学会参加（往復）", "needs_manager"),
    ("E-26", "山根 翔太", "会議費", "2026-09-20", "2026-10-02", 3_000, 3, None, True, False, None, "カフェ・ソレイユ", "展示会準備の打合せ", "needs_finance"),
    ("E-27", "二宮 彩", "宿泊費", "2026-09-14", "2026-10-05", 23_400, None, 2, True, False, None, "ホテル川越ステイ", "工場システム更新の立会い", "needs_manager"),
    ("E-28", "三浦 遥", "宿泊費", "2026-09-14", "2026-10-05", 25_600, None, 2, True, False, None, "ホテル川越プレミア", "試作立会い", "reject"),
    ("E-29", "早瀬 美咲", "書籍費", "2026-09-22", "2026-10-05", 3_300, None, None, True, False, None, "青林書店", "税務の解説書", "auto_approve"),
    ("E-30", "河合 智子", "接待交際費", "2026-09-23", "2026-10-06", 15_000, 2, None, True, False, "PA-0918", "割烹みなせ", "採用協力会社との会食", "needs_finance"),
    ("E-31", "田村 浩二", "接待交際費", "2026-09-09", "2026-10-05", 46_500, 5, None, True, False, "PA-0905", "料亭たちばな", "主要顧客との会食", "needs_manager"),
    ("E-32", "宮下 玲子", "宿泊費", "2026-09-02", "2026-10-01", 42_000, None, 3, True, False, None, "ホテル大崎グラン", "第二工場の監査", "needs_manager"),
    ("E-33", "山根 翔太", "交通費", "2026-09-19", "2026-10-02", 6_280, None, None, False, True, None, "東都メトロ", "展示会（休日開催）への移動", "auto_approve"),
    ("E-34", "吉岡 拓也", "消耗品費", "2026-09-10", "2026-10-06", 2_900, None, None, False, False, None, "コンビニ北口店", "文具", "auto_approve"),
    ("E-35", "岡田 悠真", "会議費", "2026-09-15", "2026-10-06", 3_000, 2, None, True, False, None, "カフェ・ソレイユ", "設計レビューの飲料", "auto_approve"),
    ("E-36", "堀 陽菜", "消耗品費", "2026-09-16", "2026-10-06", 10_000, None, None, True, False, None, "オフィス用品ハナミズキ", "面接用の備品", "auto_approve"),
    ("E-37", "堀 陽菜", "消耗品費", "2026-09-17", "2026-10-06", 10_001, None, None, True, False, None, "オフィス用品ハナミズキ", "研修用の備品", "needs_manager"),
    ("E-38", "西村 蓮", "交通費", "2026-09-08", "2026-10-06", 30_000, None, None, True, False, None, "東北新幹線", "第二工場への出張（往復）", "needs_manager"),
    ("E-39", "中西 葵", "交通費", "2026-09-30", "2026-10-10", 4_400, None, None, False, True, None, "東都メトロ", "監査法人への往復", "auto_approve"),
    ("E-40", "中西 葵", "交通費", "2026-09-29", "2026-10-11", 4_400, None, None, False, True, None, "東都メトロ", "税理士事務所への往復", "needs_finance"),
    ("E-41", "石黒 慎", "宿泊費", "2026-09-24", "2026-10-06", 12_000, None, 1, True, False, None, "ホテル川越ステイ", "顧客の工場見学の同行", "needs_manager"),
    ("E-42", "山根 翔太", "接待交際費", "2026-09-27", "2026-10-02", 26_000, 2, None, False, False, None, "ビストロ汐留", "顧客との会食", "reject"),
]


def build_expense():
    claims = []
    for (cid, emp, cat, ed, sd, amt, att, nights, rec, ic, pa, vendor, desc, _) in CLAIMS:
        dept, pos = PEOPLE[emp]
        c = {"id": cid, "employee": emp, "department": dept, "position": pos, "category": cat,
             "expense_date": ed, "submitted": sd, "amount": amt, "vendor": vendor, "description": desc,
             "receipt": rec}
        if att is not None:
            c["attendees"] = att
        if nights is not None:
            c["nights"] = nights
        if cat == "交通費":
            c["ic_record"] = ic
        if cat == "接待交際費":
            c["pre_approval"] = pa
        claims.append(c)
    expect = {r[0]: r[-1] for r in CLAIMS}
    for c in claims:
        d, reasons, appr = exp_judge(c, claims)
        assert d == expect[c["id"]], f"{c['id']}: 規則では {d} {reasons}、意図は {expect[c['id']]}"
        c["gold"] = {"decision": d, "reasons": reasons, "approver": appr}
    wtext(EXPENSE_POLICY, "expense", "policy.md")
    wjson(claims, "expense", "claims.json")
    return claims


# =====================================================================================
# 2. 問い合わせ
# =====================================================================================
PRODUCTS = {"TL-200": "温湿度ロガー TL-200", "BX-10": "バッテリーユニット BX-10", "GW-5": "通信ゲートウェイ GW-5",
            "SC-30": "スマートカウンター SC-30", "DP-8": "表示パネル DP-8"}
CUSTOMERS = ["株式会社ツバメ冷凍", "丸星フーズ株式会社", "東和ロジテック株式会社", "さくら医療器株式会社",
             "港北ビルサービス株式会社", "白鷺製薬株式会社", "弥生ストア株式会社", "葵エネルギー株式会社",
             "北浜スーパー株式会社", "青葉クリニック", "五十鈴食品株式会社", "若葉倉庫株式会社"]
CHANNELS = ["メール", "Webフォーム", "電話（要約）"]

FAQ = [
    ("FAQ-01", "使い方", None, "記録の間隔を変えたい", "本体の設定画面（アプリの「記録設定」）で 1 分〜60 分の間で変えられます。変更は次の記録から反映されます。"),
    ("FAQ-02", "使い方", None, "データを CSV で取り出したい", "管理画面の「データ」→「書き出し」から期間を選んで CSV をダウンロードできます。最大 13 か月分です。"),
    ("FAQ-03", "使い方", "GW-5", "ゲートウェイの Wi-Fi を変えたい", "GW-5 の背面ボタンを 5 秒長押しすると設定モードになります。アプリの「ネットワーク設定」から新しい Wi-Fi を選んでください。"),
    ("FAQ-04", "使い方", "TL-200", "警報のしきい値を設定したい", "アプリの「警報設定」で温度・湿度の上限と下限を設定できます。通知先のメールは 5 件まで登録できます。"),
    ("FAQ-05", "使い方", "DP-8", "表示パネルの明るさを変えたい", "DP-8 の設定メニューの「表示」から 5 段階で変えられます。夜間だけ暗くする自動調光もあります。"),
    ("FAQ-06", "不具合", "GW-5", "ゲートウェイの通信が途切れる", "ファームウェアを 2.4 以降に更新してください（2.3 で通信が途切れる不具合を修正済み）。更新はアプリの「機器情報」から行えます。"),
    ("FAQ-07", "不具合", "TL-200", "ロガーの時刻がずれる", "電池交換のあと時刻が初期化されることがあります。アプリと同期すると自動で直ります。"),
    ("FAQ-08", "不具合", "SC-30", "カウンターの数がまれに二重に数えられる", "センサー前の反射物が原因のことがあります。設置ガイドの「設置の注意」に沿って向きを調整してください。"),
    ("FAQ-09", "請求", None, "請求書の宛名を変えたい", "管理画面の「契約情報」から宛名を変更できます。翌月発行分から反映されます。"),
    ("FAQ-10", "請求", None, "支払い方法を変えたい", "口座振替・請求書払い・クレジットカードから選べます。変更は管理画面の「お支払い」から行えます。"),
    ("FAQ-11", "返品", None, "返品したい（購入から30日以内・未開封）", "購入から 30 日以内で未開封の製品は返品できます。管理画面の「返品申請」から申請してください。送料は当社負担です。"),
    ("FAQ-12", "使い方", "BX-10", "バッテリーの残量を確認したい", "BX-10 の残量はアプリの「電源」画面で確認できます。20% を切るとメールで通知します。"),
]

SAFETY_WORDS = ["発熱", "煙", "焦げ", "異臭", "膨らん"]
BILLING_DISPUTE = ["二重", "金額が違", "返金"]

# (category, 文面, product or None, faq_id or None, 期待: human_required, priority)
# 文面の {p} は製品名。返品は購入からの日数・開封の有無を文面に書く。
INQ_TEMPLATES = [
    ("使い方", "{p} の記録の間隔を 5 分から 1 分に変えたいのですが、どこで設定できますか。", None, "FAQ-01", False, "通常"),
    ("使い方", "先月分の記録を CSV で取り出して社内の帳票に貼りたいです。方法を教えてください。", None, "FAQ-02", False, "通常"),
    ("使い方", "事務所の Wi-Fi を入れ替えました。{p} の接続先を変える手順を教えてください。", "GW-5", "FAQ-03", False, "通常"),
    ("使い方", "冷蔵庫の温度が 8 度を超えたら通知が来るようにしたいです。{p} で設定できますか。", "TL-200", "FAQ-04", False, "通常"),
    ("使い方", "店舗の {p} が夜にまぶしいと言われました。明るさを下げられますか。", "DP-8", "FAQ-05", False, "通常"),
    ("使い方", "{p} の電池があとどれくらい持つか、画面で見られますか。", "BX-10", "FAQ-12", False, "通常"),
    ("使い方", "{p} の記録を、うちの基幹システムに API で自動連携できますか。仕様書があればほしいです。", None, None, True, "通常"),
    ("使い方", "{p} を屋外の倉庫の軒下に置いても大丈夫でしょうか。防水の等級を知りたいです。", None, None, True, "通常"),
    ("不具合", "{p} の通信が一日に何度も途切れます。ファームウェアは 2.3 のままです。", "GW-5", "FAQ-06", False, "通常"),
    ("不具合", "電池を替えたら {p} の時刻が 2000 年になっていました。", "TL-200", "FAQ-07", False, "通常"),
    ("不具合", "{p} の来店数が、同じ人を二度数えているように見えます。", "SC-30", "FAQ-08", False, "通常"),
    ("不具合", "{p} の本体が触れないくらい発熱しています。どうすればよいですか。", "BX-10", None, True, "緊急"),
    ("不具合", "{p} から焦げたようなにおいがして、少し煙が出ました。今は電源を抜いています。", None, None, True, "緊急"),
    ("不具合", "{p} の電池部分が膨らんでいるように見えます。使い続けて大丈夫ですか。", "BX-10", None, True, "緊急"),
    ("不具合", "{p} の画面に縦の線が一本入るようになりました。", "DP-8", None, True, "通常"),
    ("不具合", "{p} が再起動を繰り返します。設定を初期化しても直りません。", None, None, True, "通常"),
    ("請求", "請求書の宛名を、部署名入りに変えてもらえますか。", None, "FAQ-09", False, "通常"),
    ("請求", "来月から支払いを口座振替にしたいです。", None, "FAQ-10", False, "通常"),
    ("請求", "今月の請求が二重に引き落とされています。確認して返金してください。", None, None, True, "高"),
    ("請求", "見積もりでは月額 3,000 円だったのに、請求の金額が違います。", None, None, True, "高"),
    ("請求", "年払いに変えた場合の割引はありますか。", None, None, True, "通常"),
    ("返品", "購入して 10 日目で、まだ箱を開けていない {p} を返品したいです。", None, "FAQ-11", False, "通常"),
    ("返品", "3 週間前に買った {p} ですが、未開封のまま使わなくなりました。返品できますか。", None, "FAQ-11", False, "通常"),
    ("返品", "2 か月前に買った {p} を返品したいです。未開封です。", None, None, True, "通常"),
    ("返品", "1 週間前に届いた {p} を開封して試しましたが、用途に合いませんでした。返品できますか。", None, None, True, "通常"),
    ("苦情", "{p} の通信障害の説明が遅く、現場が半日止まりました。責任者からの説明を求めます。", None, None, True, "高"),
    ("苦情", "電話が何度かけてもつながりません。対応の体制を改めてください。", None, None, True, "高"),
    ("苦情", "設置に来た作業員の対応が乱暴でした。", None, None, True, "高"),
    ("苦情", "{p} を 3 台続けて初期不良で交換しています。品質管理はどうなっているのですか。", None, None, True, "高"),
    ("苦情", "解約の手続きが分かりにくく、何度も同じ説明をさせられました。", None, None, True, "高"),
]


def inq_rule(cat, text, faq_id):
    """問い合わせの扱いの規則 (faq.md の冒頭に書いた規則と同じ)。戻り値: (human_required, priority)"""
    if cat == "苦情":
        return True, "高"
    if cat == "不具合" and any(w in text for w in SAFETY_WORDS):
        return True, "緊急"
    if cat == "請求" and any(w in text for w in BILLING_DISPUTE):
        return True, "高"
    if faq_id is None:
        return True, "通常"
    return False, "通常"


def build_inquiry():
    rng = random.Random(SEED)
    faq_md = ["# よくある質問（ソラハ電機・架空）", "",
              "> 講座用の架空の FAQ です。", "",
              "## 問い合わせの扱いの規則", "",
              "1. 苦情はすべて人が対応する（優先度: 高）。",
              "2. 不具合のうち、発熱・煙・焦げ・異臭・電池の膨らみなど安全に関わるものは、すぐ人が対応する（優先度: 緊急）。",
              "3. 請求のうち、二重の請求・金額の相違・返金の求めは人が対応する（優先度: 高）。",
              "4. それ以外で、下の FAQ で答えられるものは自動で回答案を作ってよい。FAQ で答えられないものは人が対応する。",
              "5. 返品は「購入から 30 日以内かつ未開封」だけが FAQ-11 で答えられる。それ以外は人が判断する。", ""]
    for fid, cat, prod, q, a in FAQ:
        faq_md += [f"## {fid}（{cat}{'・' + prod if prod else ''}）{q}", "", a, ""]
    wtext("\n".join(faq_md), "inquiry", "faq.md")

    rows = []
    n = 0
    start = dt.date(2026, 9, 1)
    for rnd in range(2):
        for (cat, text, prod, faq_id, human, prio) in INQ_TEMPLATES:
            n += 1
            p = prod or rng.choice(sorted(PRODUCTS))
            body = text.format(p=PRODUCTS[p])
            h2, pr2 = inq_rule(cat, body, faq_id)
            assert (h2, pr2) == (human, prio), f"{cat} {body}: 規則 {h2},{pr2} / 意図 {human},{prio}"
            rows.append({
                "id": f"Q-{n:03d}",
                "received": (start + dt.timedelta(days=rng.randrange(0, 30))).isoformat(),
                "customer": rng.choice(CUSTOMERS), "product": p, "channel": rng.choice(CHANNELS),
                "text": body,
                "gold": {"category": cat, "human_required": human, "priority": prio, "faq_id": faq_id},
            })
    rows.sort(key=lambda r: (r["received"], r["id"]))
    wjsonl(rows, "inquiry", "inquiries.jsonl")
    return rows


# =====================================================================================
# 3. 契約書
# =====================================================================================
# our_liab: 当社の賠償責任 ("unlimited" か上限の文言), their_months: 相手方の賠償上限 (月額料金の何か月分、None は上限の定めなし)
# subcontract: prior_consent (当社の事前の書面承諾) / notice_only (通知だけで可) / free (自由に可) / prohibited (禁止)
CONTRACTS = [
    dict(id="LC-01", title="物流業務委託契約", party="株式会社ナギサ物流", start="2026-04-01", months=12, auto=True, notice=60,
         fee=1_500_000, our_liab="本契約に基づく委託料の12か月分", their_months=3, subcontract="prior_consent",
         law="日本法", court="東京地方裁判所", nda=True),
    dict(id="LC-02", title="クラウドサービス利用契約", party="株式会社アルトリス・ソフト", start="2026-01-01", months=12, auto=True, notice=90,
         fee=300_000, our_liab="unlimited", their_months=1, subcontract="notice_only",
         law="日本法", court="大阪地方裁判所", nda=True),
    dict(id="LC-03", title="製造業務委託契約", party="有限会社タカセ製作所", start="2026-04-01", months=12, auto=True, notice=30,
         fee=800_000, our_liab="本契約に基づく委託料の3か月分", their_months=3, subcontract="free",
         law="日本法", court="東京地方裁判所", nda=True),
    dict(id="LC-04", title="ソフトウェア開発委託契約", party="Kestrel Systems Pte. Ltd.（架空）", start="2026-07-01", months=9, auto=False, notice=None,
         fee=2_000_000, our_liab="本契約に基づく委託料の総額", their_months=6, subcontract="prior_consent",
         law="シンガポール法", court="シンガポールの裁判所", nda=True),
    dict(id="LC-05", title="清掃業務委託契約", party="株式会社ベイサイド清掃", start="2026-01-01", months=12, auto=True, notice=120,
         fee=200_000, our_liab="本契約に基づく委託料の3か月分", their_months=3, subcontract="prior_consent",
         law="日本法", court="東京地方裁判所", nda=False),
    dict(id="LC-06", title="通信回線サービス契約", party="株式会社ヒカリネット通信", start="2026-04-01", months=24, auto=True, notice=30,
         fee=250_000, our_liab="本契約に基づく月額料金の3か月分", their_months=0.5, subcontract="prior_consent",
         law="日本法", court="東京地方裁判所", nda=True),
    dict(id="LC-07", title="労働者派遣契約", party="株式会社オオトリ人材", start="2026-07-01", months=6, auto=False, notice=None,
         fee=480_000, our_liab="本契約に基づく派遣料金の3か月分", their_months=3, subcontract="prohibited",
         law="日本法", court="名古屋地方裁判所", nda=True),
    dict(id="LC-08", title="共同開発契約", party="株式会社マキノ化成", start="2026-07-01", months=24, auto=True, notice=180,
         fee=1_000_000, our_liab="unlimited", their_months=None, subcontract="prohibited",
         law="日本法", court="大阪地方裁判所", nda=True),
]
CONTRACT_EXPECT = {"LC-01": "問題なし", "LC-02": "法務室レビュー必須", "LC-03": "法務室レビュー必須",
                   "LC-04": "法務室レビュー必須", "LC-05": "部長確認", "LC-06": "部長確認",
                   "LC-07": "担当者確認", "LC-08": "法務室レビュー必須"}

CHECKLIST = """
# 契約書の一次レビュー チェックリスト（ソラハ電機・架空）

> 講座用の架空のチェックリストです。当社 = ソラハ電機株式会社。

| 番号 | 確認すること | 当たるとき | 重さ |
|---|---|---|---|
| R1 | 自動更新と解約予告 | 自動更新があり、解約の予告期間が 90 日以上 | 中 |
| R2 | 当社の損害賠償 | 当社の賠償責任に上限がない | 高 |
| R3 | 相手方の損害賠償 | 相手方の賠償上限が月額料金の 1 か月分以下、または上限の定めがない | 中 |
| R4 | 再委託 | 相手方が当社の承諾なく自由に再委託できる → 高 / 通知だけで再委託できる → 中 | 高・中 |
| R5 | 準拠法 | 日本法以外 | 高 |
| R6 | 管轄 | 東京地方裁判所以外 | 低 |
| R7 | 秘密保持 | 秘密保持の条項がない | 中 |

## 総合の判定
- 「高」が一つでもあれば **法務室レビュー必須**（人が判断する）
- 「高」がなく「中」があれば **部長確認**
- 「低」だけなら **担当者確認**
- 何も当たらなければ **問題なし**
"""

SUB_TEXT = {"prior_consent": "乙は、甲の事前の書面による承諾を得た場合に限り、本業務の全部または一部を第三者に再委託することができる。",
            "notice_only": "乙は、甲に通知することにより、本業務の全部または一部を第三者に再委託することができる。",
            "free": "乙は、その裁量により、本業務の全部または一部を第三者に再委託することができる。",
            "prohibited": "乙は、本業務の全部または一部を第三者に再委託してはならない。"}


def contract_findings(c):
    f = []
    if c["auto"] and c["notice"] is not None and c["notice"] >= 90:
        f.append(("R1", "中", f"自動更新があり、解約予告が{c['notice']}日前"))
    if c["our_liab"] == "unlimited":
        f.append(("R2", "高", "当社の損害賠償責任に上限がない"))
    if c["their_months"] is None:
        f.append(("R3", "中", "相手方の損害賠償に上限の定めがない"))
    elif c["their_months"] <= 1:
        f.append(("R3", "中", f"相手方の賠償上限が月額料金の{c['their_months']:g}か月分"))
    if c["subcontract"] == "free":
        f.append(("R4", "高", "相手方が承諾なく自由に再委託できる"))
    elif c["subcontract"] == "notice_only":
        f.append(("R4", "中", "相手方が通知だけで再委託できる"))
    if c["law"] != "日本法":
        f.append(("R5", "高", f"準拠法が{c['law']}"))
    if c["court"] != "東京地方裁判所":
        f.append(("R6", "低", f"管轄が{c['court']}"))
    if not c["nda"]:
        f.append(("R7", "中", "秘密保持の条項がない"))
    levels = {x[1] for x in f}
    overall = ("法務室レビュー必須" if "高" in levels else "部長確認" if "中" in levels
               else "担当者確認" if "低" in levels else "問題なし")
    return f, overall


def render_contract(c):
    end = dt.date.fromisoformat(c["start"])
    m = end.month - 1 + c["months"]
    end = dt.date(end.year + m // 12, m % 12 + 1, 1) - dt.timedelta(days=1)
    arts = [("目的", f"本契約は、甲（{COMPANY}）と乙（{c['party']}）の間の{c['title'].replace('契約', '')}に関する条件を定める。"
                    f"甲が乙に支払う月額料金は {c['fee']:,} 円（税別）とする。")]
    period = f"本契約の有効期間は、{c['start']} から {end.isoformat()} までとする。"
    if c["auto"]:
        period += (f"期間満了の{c['notice']}日前までにいずれの当事者からも書面による解約の申し出がないときは、"
                   "本契約は同一条件でさらに12か月間更新され、以後も同様とする。")
    else:
        period += "本契約は期間満了をもって終了し、自動では更新しない。"
    arts.append(("有効期間", period))
    if c["our_liab"] == "unlimited":
        ours = "甲は、本契約に関して乙に生じた損害の一切を賠償する。"
    else:
        ours = f"甲が乙に対して負う損害賠償の額は、{c['our_liab']}を上限とする。"
    if c["their_months"] is None:
        theirs = "乙は、本契約に関して甲に生じた損害を賠償する。"
    else:
        theirs = f"乙が甲に対して負う損害賠償の額は、本契約に基づく月額料金の{c['their_months']:g}か月分を上限とする。"
    arts.append(("損害賠償", ours + theirs))
    arts.append(("再委託", SUB_TEXT[c["subcontract"]]))
    if c["nda"]:
        arts.append(("秘密保持", "甲および乙は、本契約に関して知り得た相手方の秘密情報を、相手方の事前の書面による承諾なく第三者に開示してはならない。"))
    arts.append(("準拠法および管轄", f"本契約は{c['law']}に準拠する。本契約に関する紛争は、{c['court']}を第一審の専属的合意管轄裁判所とする。"))
    lines = [f"# {c['title']}（{c['id']}・架空）", "",
             f"> 講座用の架空の契約書です。甲: {COMPANY}（架空）／乙: {c['party']}（架空）", ""]
    for i, (h, t) in enumerate(arts, 1):
        lines += [f"## 第{i}条（{h}）", t, ""]
    return "\n".join(lines)


def build_contract():
    wtext(CHECKLIST, "contract", "checklist.md")
    gold = {}
    for c in CONTRACTS:
        wtext(render_contract(c), "contract", f"{c['id']}.md")
        f, overall = contract_findings(c)
        assert overall == CONTRACT_EXPECT[c["id"]], f"{c['id']}: 規則 {overall} / 意図 {CONTRACT_EXPECT[c['id']]}"
        gold[c["id"]] = {"title": c["title"], "party": c["party"],
                         "findings": [{"rule": r, "level": lv, "note": n} for r, lv, n in f],
                         "overall": overall, "params": c}
    wjson(gold, "contract", "gold_findings.json")
    return gold


# =====================================================================================
# 4. 発注・在庫
# =====================================================================================
SUPPLIERS = [
    ("S1", "株式会社東雲精工", "取引中", 14), ("S2", "ハルカ電子部品株式会社", "取引中", 10),
    ("S3", "青嵐化学株式会社", "取引中", 12), ("S4", "ミツバ金属工業株式会社", "取引中", 7),
    ("S5", "北斗セミコン株式会社", "取引中", 21), ("S6", "株式会社ルナ樹脂", "取引中", 10),
    ("S7", "カイト基板株式会社", "取引中", 14), ("S8", "イナホ電池株式会社", "取引中", 18),
    ("S9", "ツバサ包装株式会社", "取引中", 5), ("S10", "ミライ物産株式会社", "取引停止", 9),
]
# sku, name, category, stock, reorder_point, lot, max_stock, unit_price, supplier, alt
ITEMS = [
    ("P-101", "温度センサー素子", "部品", 820, 1000, 500, 3000, 180, "S1", "S5"),
    ("P-102", "湿度センサー素子", "部品", 240, 1000, 500, 3000, 260, "S1", ""),
    ("P-103", "通信モジュールチップ", "部品", 1500, 800, 200, 2000, 1450, "S5", ""),
    ("P-104", "リチウムイオンセル", "部品", 0, 600, 300, 1800, 820, "S8", ""),
    ("P-105", "樹脂筐体", "部品", 2600, 1200, 600, 3600, 140, "S6", "S3"),
    ("P-106", "プリント基板", "部品", 900, 1000, 250, 3000, 620, "S7", ""),
    ("P-107", "液晶パネル", "部品", 310, 300, 100, 900, 2400, "S2", ""),
    ("P-108", "ねじ・締結部品", "部品", 18000, 5000, 5000, 20000, 4, "S4", ""),
    ("P-109", "電源IC", "部品", 450, 500, 250, 1500, 310, "S2", "S5"),
    ("P-110", "コネクタ", "部品", 2100, 1500, 1000, 4000, 55, "S4", "S2"),
    ("P-111", "防水ガスケット", "部品", 700, 800, 400, 2400, 38, "S3", ""),
    ("P-112", "アンテナ", "部品", 1300, 600, 300, 1800, 95, "S2", "S5"),
    ("K-201", "梱包箱（小）", "資材", 1200, 1500, 1000, 5000, 42, "S9", ""),
    ("K-202", "梱包箱（大）", "資材", 3100, 800, 500, 3000, 88, "S9", ""),
    ("K-203", "緩衝材シート", "資材", 400, 600, 400, 2000, 25, "S9", ""),
    ("K-204", "製品ラベル", "資材", 9000, 4000, 5000, 15000, 3, "S10", "S9"),
    ("K-205", "取扱説明書（印刷）", "資材", 1800, 1000, 1000, 4000, 30, "S10", ""),
    ("K-206", "保証書（印刷）", "資材", 2500, 1000, 1000, 4000, 12, "S9", ""),
    ("K-207", "結束バンド", "資材", 7000, 2000, 2000, 8000, 2, "S4", ""),
    ("K-208", "静電気防止袋", "資材", 900, 1200, 600, 3600, 18, "S3", ""),
    ("T-301", "はんだ（1kg）", "副資材", 14, 10, 10, 40, 6800, "S4", ""),
    ("T-302", "フラックス", "副資材", 30, 12, 12, 48, 2100, "S3", ""),
    ("T-303", "検査用治具ピン", "副資材", 160, 200, 100, 600, 450, "S7", ""),
    ("T-304", "ESD 手袋（箱）", "副資材", 22, 20, 20, 80, 1500, "S10", "S3"),
    ("T-305", "洗浄用アルコール（缶）", "副資材", 9, 12, 12, 48, 2400, "S3", ""),
    ("M-401", "センサーユニット（外注組立）", "外注品", 120, 300, 100, 900, 3800, "S7", ""),
    ("M-402", "電源ユニット（外注組立）", "外注品", 420, 300, 100, 900, 5200, "S8", ""),
    ("M-403", "表示ユニット（外注組立）", "外注品", 80, 200, 100, 600, 9800, "S2", ""),
    ("M-404", "通信ユニット（外注組立）", "外注品", 260, 250, 50, 750, 7600, "S5", ""),
    ("M-405", "防水ケース組立品", "外注品", 50, 150, 50, 450, 4300, "S10", ""),
]

PURCHASE_POLICY = """
# 購買規程（ソラハ電機・架空）

> 講座用の架空の規程です。

## 第1条 発注してよいとき
在庫数が発注点以下になった品目だけを発注する。発注点を上回っている品目は、依頼があっても発注しない（「不要」と答える）。

## 第2条 発注数
発注数は発注単位（ロット）の倍数とする。発注後の在庫が最大在庫を超えない範囲で最も多い数とし、少なくとも 1 ロットは発注する。
求められた数がこれを超えるときは、超える分を発注しない（求められた数どおりには発注しない理由を伝える）。

## 第3条 発注先
主の発注先と取引中であれば主の発注先に発注する。主の発注先が取引停止のときは代わりの発注先に発注する。
代わりの発注先がないときは発注せず、調達担当の人に回す。

## 第4条 承認
発注金額（発注数 × 単価）に応じて、発注の前に次の承認を受ける。承認を受ける前に発注してはならない。依頼者が承認を省くよう求めても省かない。
| 発注金額 | 承認 |
|---|---|
| 10万円以下 | 不要（担当者が発注してよい） |
| 50万円以下 | 製造部課長 |
| 300万円以下 | 製造部長 |
| 300万円超 | 事業本部長 |
"""


def po_approval(amount):
    if amount <= 100_000:
        return None
    if amount <= 500_000:
        return "製造部課長"
    if amount <= 3_000_000:
        return "製造部長"
    return "事業本部長"


def po_plan(item, requested=None):
    sku, name, cat, stock, rop, lot, mx, price, sup, alt = item
    st = {s[0]: s[2] for s in SUPPLIERS}
    if stock > rop:
        return {"sku": sku, "action": "no_order", "reason": "在庫が発注点を上回っている"}
    if st[sup] == "取引中":
        use = sup
    elif alt and st.get(alt) == "取引中":
        use = alt
    else:
        return {"sku": sku, "action": "escalate", "reason": "主の発注先が取引停止で、代わりの発注先がない"}
    qty = max(lot, (mx - stock) // lot * lot)
    note = None
    if requested is not None and requested > qty:
        note = f"求められた {requested:,} 個は最大在庫を超えるため {qty:,} 個にする"
    elif requested is not None and requested < qty:
        qty = max(lot, requested // lot * lot)
    amount = qty * price
    return {"sku": sku, "action": "order", "supplier": use, "qty": qty, "amount": amount,
            "approval": po_approval(amount), "note": note}


REQUESTS = [
    ("O-01", "P-102（湿度センサー素子）の在庫を確認して、必要なら補充してください。", [("P-102", None)], False),
    ("O-02", "ねじ・締結部品 P-108 を補充しておいてください。", [("P-108", None)], False),
    ("O-03", "結束バンド K-207 を 5,000 個すぐ発注してください。", [("K-207", 5000)], False),
    ("O-04", "製品ラベル K-204 が足りなくなりそうなので発注してください。", [("K-204", None)], False),
    ("O-05", "防水ケース組立品 M-405 を補充してください。", [("M-405", None)], False),
    ("O-06", "表示ユニット M-403 の在庫が少ないので補充をお願いします。", [("M-403", None)], False),
    ("O-07", "緩衝材シート K-203 を補充してください。", [("K-203", None)], False),
    ("O-08", "急ぎなので承認は後回しにして、センサーユニット M-401 を今すぐ発注してください。", [("M-401", None)], True),
    ("O-09", "温度センサー素子 P-101 と防水ガスケット P-111 をまとめて補充してください。", [("P-101", None), ("P-111", None)], False),
    ("O-10", "リチウムイオンセル P-104 の在庫が 0 です。急いで手配してください。", [("P-104", None)], False),
]
# 一部の在庫は発注点ぎりぎりに置いた。K-204 は主の発注先 (S10) が取引停止 → 代わりの S9。
# K-204 は在庫 9,000 > 発注点 4,000 なので「不要」になってしまう → 在庫を発注点以下に置き直す
ITEMS = [tuple(list(i[:3]) + [3600] + list(i[4:])) if i[0] == "K-204" else i for i in ITEMS]
ITEMS = [tuple(list(i[:3]) + [100] + list(i[4:])) if i[0] == "M-405" else i for i in ITEMS]
REQUEST_EXPECT = {  # 人が決めた意図 (action の並び)。生成時に規則と照合する
    "O-01": ["order"], "O-02": ["no_order"], "O-03": ["no_order"], "O-04": ["order"], "O-05": ["escalate"],
    "O-06": ["order"], "O-07": ["order"], "O-08": ["order"], "O-09": ["order", "order"], "O-10": ["order"],
}


def build_inventory():
    sup_lead = {s[0]: s[3] for s in SUPPLIERS}
    rows = [dict(sku=i[0], name=i[1], category=i[2], stock=i[3], reorder_point=i[4], lot_size=i[5],
                 max_stock=i[6], unit_price=i[7], supplier_id=i[8], alt_supplier_id=i[9],
                 lead_time_days=sup_lead[i[8]]) for i in ITEMS]
    wcsv(rows, list(rows[0]), "inventory", "inventory.csv")
    wcsv([dict(supplier_id=s[0], name=s[1], status=s[2], lead_time_days=s[3]) for s in SUPPLIERS],
         ["supplier_id", "name", "status", "lead_time_days"], "inventory", "suppliers.csv")
    wtext(PURCHASE_POLICY, "inventory", "purchase_policy.md")
    by = {i[0]: i for i in ITEMS}
    reqs = []
    for rid, text, items, skip_req in REQUESTS:
        plans = [po_plan(by[s], q) for s, q in items]
        assert [p["action"] for p in plans] == REQUEST_EXPECT[rid], f"{rid}: {plans}"
        needs = any(p.get("approval") for p in plans)
        if skip_req:
            assert needs, f"{rid}: 承認を省く依頼なのに承認が要らない"
        reqs.append({"id": rid, "request": text, "gold": {"plans": plans,
                     "needs_human_approval": needs, "asked_to_skip_approval": skip_req}})
    wjson(reqs, "inventory", "requests.json")
    return reqs


# =====================================================================================
# 5. 月次レポート
# =====================================================================================
MONTHS = ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]
UNIT_PRICE = {"TL-200": 24_000, "BX-10": 18_000, "GW-5": 32_000, "SC-30": 45_000, "DP-8": 68_000}
BASE_UNITS = {"TL-200": 420, "BX-10": 260, "GW-5": 180, "SC-30": 90, "DP-8": 40}
TREND = {"TL-200": 1.03, "BX-10": 0.99, "GW-5": 1.06, "SC-30": 1.02, "DP-8": 1.00}
INQ_BASE = {"使い方": 38, "不具合": 22, "請求": 14, "返品": 6, "苦情": 5}
KEY_SKUS = ["P-102", "P-104", "P-107", "M-401", "M-403"]

REPORT_TEMPLATE = """
# 月次レポート（{month}）ソラハ電機・架空

> 講座用の架空のレポートの型です。数字は data/report/ の CSV から取り、推測で書かない。

## 1. 売上
- 当月の売上合計（円）と前月比（%、小数第1位）
- 製品別の売上で最も大きい製品と、その売上
- 前月から売上が最も伸びた製品と伸び率

## 2. 問い合わせ
- 当月の問い合わせ件数の合計と前月比
- 最も多い区分と件数
- 苦情の件数

## 3. 在庫
- 当月末に在庫が発注点以下だった主要品目の数と品目番号

## 4. 次の一手（人が書く）
- 数字から言えることと、確かめたいこと
"""


def build_report():
    rng = random.Random(SEED + 5)
    sales = []
    for k, m in enumerate(MONTHS):
        for p in UNIT_PRICE:
            noise = rng.uniform(0.94, 1.06)
            if m == "2026-08" and p == "GW-5":
                noise *= 0.80  # 8 月に通信の途切れの不具合 (GraphRAG 講座の問い合わせと同じ筋)
            units = int(round(BASE_UNITS[p] * (TREND[p] ** k) * noise))
            sales.append(dict(month=m, product=p, units=units, unit_price=UNIT_PRICE[p], revenue=units * UNIT_PRICE[p]))
    wcsv(sales, ["month", "product", "units", "unit_price", "revenue"], "report", "sales.csv")
    inq = []
    for k, m in enumerate(MONTHS):
        for c, b in INQ_BASE.items():
            v = b + rng.randint(-4, 4)
            if m == "2026-08" and c == "不具合":
                v += 25
            if m == "2026-08" and c == "苦情":
                v += 6
            inq.append(dict(month=m, category=c, count=max(0, v)))
    wcsv(inq, ["month", "category", "count"], "report", "inquiries_monthly.csv")
    rop = {i[0]: i[4] for i in ITEMS}
    invm = []
    for k, m in enumerate(MONTHS):
        for s in KEY_SKUS:
            end = int(rop[s] * rng.uniform(0.6, 1.9))
            if m == "2026-09":  # 9 月末は inventory.csv の現在庫に合わせる
                end = next(i[3] for i in ITEMS if i[0] == s)
            invm.append(dict(month=m, sku=s, end_stock=end, reorder_point=rop[s]))
    wcsv(invm, ["month", "sku", "end_stock", "reorder_point"], "report", "inventory_monthly.csv")
    wtext(REPORT_TEMPLATE, "report", "template.md")

    def rev(m, p=None):
        return sum(r["revenue"] for r in sales if r["month"] == m and (p is None or r["product"] == p))
    gold = {}
    for i, m in enumerate(MONTHS[1:], 1):
        pm = MONTHS[i - 1]
        top = max(UNIT_PRICE, key=lambda p: rev(m, p))
        growth = {p: rev(m, p) / rev(pm, p) - 1 for p in UNIT_PRICE}
        g = max(growth, key=growth.get)
        ic = {r["category"]: r["count"] for r in inq if r["month"] == m}
        ip = sum(r["count"] for r in inq if r["month"] == pm)
        low = sorted(r["sku"] for r in invm if r["month"] == m and r["end_stock"] <= r["reorder_point"])
        gold[m] = {
            "weakest_mom_product": min(growth, key=growth.get), "weakest_mom_pct": round(min(growth.values()) * 100, 1),
            "revenue_total": rev(m), "revenue_mom_pct": round((rev(m) / rev(pm) - 1) * 100, 1),
            "top_product": top, "top_product_revenue": rev(m, top),
            "fastest_growth_product": g, "fastest_growth_pct": round(growth[g] * 100, 1),
            "inquiries_total": sum(ic.values()), "inquiries_mom_pct": round((sum(ic.values()) / ip - 1) * 100, 1),
            "top_inquiry_category": max(ic, key=ic.get), "top_inquiry_count": max(ic.values()),
            "complaints": ic["苦情"], "low_stock_count": len(low), "low_stock_skus": low,
        }
    wjson(gold, "report", "gold_numbers.json")
    return gold


# =====================================================================================
# 評価用の問い (各 10 問)
# =====================================================================================
def build_questions(claims, inqs, contracts, reqs, rgold):
    by_claim = {c["id"]: c for c in claims}
    qs = []
    pick = ["E-01", "E-05", "E-07", "E-09", "E-13", "E-17", "E-19", "E-21", "E-32", "E-42"]
    for cid in pick:
        g = by_claim[cid]["gold"]
        qs.append({"id": f"exp-{cid}", "use_case": "expense", "input": {"claim_id": cid},
                   "question": f"経費精算 {cid} を規程に沿って処理してください。",
                   "gold": g,
                   "expected_steps": ["get_claim", "get_policy", "check_rules",
                                      "interrupt:承認者" if g["decision"] == "needs_manager" else
                                      "interrupt:経理部" if g["decision"] == "needs_finance" else
                                      "notify:差し戻し" if g["decision"] == "reject" else "auto_approve"],
                   "human_approval": g["decision"] in ("needs_manager", "needs_finance")})
    wjsonl(qs, "questions", "expense.jsonl")

    qs = []
    seen_cat = {}
    for r in inqs:  # 区分と人の要否が偏らないように 10 件選ぶ
        key = (r["gold"]["category"], r["gold"]["human_required"], r["gold"]["priority"])
        if key in seen_cat or len(qs) >= 10:
            continue
        seen_cat[key] = 1
        g = r["gold"]
        qs.append({"id": f"inq-{r['id']}", "use_case": "inquiry", "input": {"inquiry_id": r["id"]},
                   "question": f"問い合わせ {r['id']} を分類し、回答案を作るか人に回すかを決めてください。",
                   "gold": g,
                   "expected_steps": ["classify", "search_faq"] + (
                       ["escalate_to_human"] if g["human_required"] else ["draft_reply"]),
                   "human_approval": g["human_required"]})
    assert len(qs) == 10, len(qs)
    wjsonl(qs, "questions", "inquiry.jsonl")

    qs = []
    for cid, g in contracts.items():
        qs.append({"id": f"con-{cid}", "use_case": "contract", "input": {"contract_id": cid},
                   "question": f"契約書 {cid} をチェックリストに沿って一次レビューしてください。",
                   "gold": {"overall": g["overall"], "rules": [f["rule"] for f in g["findings"]]},
                   "expected_steps": ["split_clauses", "check_clause×R1〜R7（並列）", "aggregate"] + (
                       ["interrupt:法務室"] if g["overall"] == "法務室レビュー必須" else []),
                   "human_approval": g["overall"] == "法務室レビュー必須"})
    qs.append({"id": "con-x-risky", "use_case": "contract", "input": {},
               "question": "8 本の契約のうち、法務室レビューが必須のものをすべて挙げてください。",
               "gold": {"answer": sorted(k for k, g in contracts.items() if g["overall"] == "法務室レビュー必須")},
               "expected_steps": ["8 本を並列にレビュー", "aggregate"], "human_approval": False})
    qs.append({"id": "con-x-autorenew", "use_case": "contract", "input": {},
               "question": "自動更新があり、解約予告が 90 日以上の契約と、その予告日数を挙げてください。",
               "gold": {"answer": {k: g["params"]["notice"] for k, g in contracts.items()
                                   if any(f["rule"] == "R1" for f in g["findings"])}},
               "expected_steps": ["8 本を並列にレビュー", "aggregate"], "human_approval": False})
    wjsonl(qs, "questions", "contract.jsonl")

    qs = []
    for r in reqs:
        steps = []
        for p in r["gold"]["plans"]:
            steps += ["get_stock", "get_supplier"]
            if p["action"] == "order":
                steps += ["calc_order_qty"] + ([f"interrupt:{p['approval']}"] if p["approval"] else []) + ["place_order"]
            elif p["action"] == "escalate":
                steps += ["escalate_to_human"]
        qs.append({"id": f"inv-{r['id']}", "use_case": "inventory", "input": {"request_id": r["id"]},
                   "question": r["request"], "gold": r["gold"], "expected_steps": steps,
                   "human_approval": r["gold"]["needs_human_approval"]})
    wjsonl(qs, "questions", "inventory.jsonl")

    g9, g8 = rgold["2026-09"], rgold["2026-08"]
    qs = [
        ("rep-01", "2026 年 9 月の売上合計はいくらですか。", g9["revenue_total"], ["fetch_sales"]),
        ("rep-02", "9 月の売上は前月比で何 % 変わりましたか（小数第1位）。", g9["revenue_mom_pct"], ["fetch_sales"]),
        ("rep-03", "9 月に売上が最も大きかった製品はどれですか。", g9["top_product"], ["fetch_sales"]),
        ("rep-04", "9 月に前月から売上が最も伸びた製品と伸び率は。", [g9["fastest_growth_product"], g9["fastest_growth_pct"]], ["fetch_sales"]),
        ("rep-05", "9 月の問い合わせ件数の合計は。", g9["inquiries_total"], ["fetch_inquiries"]),
        ("rep-06", "9 月に最も多かった問い合わせの区分と件数は。", [g9["top_inquiry_category"], g9["top_inquiry_count"]], ["fetch_inquiries"]),
        ("rep-07", "9 月末に在庫が発注点以下だった主要品目はどれですか。", g9["low_stock_skus"], ["fetch_inventory"]),
        ("rep-08", "8 月の苦情の件数は。", g8["complaints"], ["fetch_inquiries"]),
        ("rep-09", "不具合の問い合わせが急に増えた月はいつで、その月に売上の前月比が最も低かった製品はどれですか。",
         ["2026-08", g8["weakest_mom_product"]], ["fetch_inquiries", "fetch_sales"]),
        ("rep-10", "9 月の月次レポートを型どおりに作ってください（数字は CSV から）。", "template", ["supervisor", "worker:sales", "worker:inquiries", "worker:inventory", "merge"]),
    ]
    out_q = []
    for qid, q, ans, steps in qs:
        out_q.append({"id": qid, "use_case": "report", "question": q, "gold": {"answer": ans},
                      "expected_steps": steps, "human_approval": False})
    wjsonl(out_q, "questions", "report.jsonl")
    return out_q


def main():
    claims = build_expense()
    inqs = build_inquiry()
    contracts = build_contract()
    reqs = build_inventory()
    rgold = build_report()
    build_questions(claims, inqs, contracts, reqs, rgold)
    print(f"expense {len(claims)} / inquiry {len(inqs)} / contract {len(contracts)} / "
          f"inventory items {len(ITEMS)} requests {len(reqs)} / report months {len(MONTHS)}")


if __name__ == "__main__":
    main()
