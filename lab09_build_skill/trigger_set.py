"""ラボ 9 の「発動の試験」の問い 20 個と、説明文を曖昧にした版 (vague)。

expect: 最初に load_skill で読むべきスキル (None = どのスキルも読まないのが正しい)
note  : 境界の問い (人が見ても迷う所) の理由。🔴 問いも会社もすべて架空
"""
from __future__ import annotations

MONTHLY, CONTRACT = "solaha-monthly-report", "solaha-contract-review"

QUESTIONS = [
    # 月次レポートを使うべき 10 個
    {"id": "T-01", "q": "2026-09 の月次レポートを作ってください。", "expect": MONTHLY},
    {"id": "T-02", "q": "8 月の振り返りを社内の型でまとめて。", "expect": MONTHLY},
    {"id": "T-03", "q": "今月の数字のまとめをお願いします。", "expect": MONTHLY},
    {"id": "T-04", "q": "7 月分の月次レポート、部長に出す版を作って。", "expect": MONTHLY},
    {"id": "T-05", "q": "2026-06 の売上・問い合わせ・在庫をレポートの型で出して。", "expect": MONTHLY},
    {"id": "T-06", "q": "先月 (2026-08) の振り返り資料を作りたい。", "expect": MONTHLY},
    {"id": "T-07", "q": "5 月の月次の報告書を下書きして。", "expect": MONTHLY},
    {"id": "T-08", "q": "9 月はどうだった？売上と問い合わせと在庫を一通り見たい。", "expect": MONTHLY,
     "note": "「月次」「レポート」の語が無い言い方"},
    {"id": "T-09", "q": "経営会議用に 2026-07 の数字を型どおりに整理して。", "expect": MONTHLY,
     "note": "「月次」「レポート」の語が無い言い方"},
    {"id": "T-10", "q": "6 月の月次をまとめて、次の一手の候補も付けて。", "expect": MONTHLY},
    # 契約書の一次レビューを使うべき 5 個
    {"id": "T-11", "q": "LC-03 をレビューしてください。", "expect": CONTRACT},
    {"id": "T-12", "q": "この部品供給の契約書、法務に回すべき？", "expect": CONTRACT},
    {"id": "T-13", "q": "LC-07 のリスクを洗い出して。", "expect": CONTRACT},
    {"id": "T-14", "q": "新しい保守契約の一次レビューをお願いします。", "expect": CONTRACT},
    {"id": "T-15", "q": "取引先から届いた NDA に問題がないか見て。", "expect": CONTRACT,
     "note": "「契約」の語が無い (NDA = 秘密保持契約)"},
    # どのスキルも使わないのが正しい 5 個
    {"id": "T-16", "q": "9 月の売上でいちばん売れた製品は？", "expect": None,
     "note": "数字 1 つなら report の道具だけで足りる (レポートの型は要らない)"},
    {"id": "T-17", "q": "週報レポートの提出期限はいつ？", "expect": None, "note": "「レポート」の語があるが月次ではない"},
    {"id": "T-18", "q": "経費精算の上限はいくら？", "expect": None},
    {"id": "T-19", "q": "TL-200 の電池の交換時期は？", "expect": None},
    {"id": "T-20", "q": "契約社員の有給は何日？", "expect": None, "note": "「契約」の語があるが契約書ではない"},
]

# 説明文を曖昧にした版。「何をするか」も「いつ使うか」も削った (本物のモデルで、発動がどう変わるかを見る)
VAGUE = {
    MONTHLY: "レポートを作る。",
    CONTRACT: "文書を確認する。",
}
VARIANTS = {"standard": None, "vague": VAGUE}
