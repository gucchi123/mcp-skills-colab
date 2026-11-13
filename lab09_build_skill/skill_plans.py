"""ラボ 9 の偽モデル (mock) の筋書き。API キーが無くても、読み込み係・発動の試験・最後までの流れを動かせる。

  keyword : 問いの語でスキルを選ぶだけの筋書き (発動の試験用)。🔴 説明文は読まない → vague にしても結果は変わらない
  follow  : keyword で選んだあと、月次レポートの手順どおりに進む筋書き (最後までの流れ用)
🔴 筋書きは講師が書いた決まった動き。適合率・再現率などの数字は性能の証拠にならない (配線の確認だけ)。
"""
from __future__ import annotations

import json
import re

from common.llm import last_user_text, say, tool_results, use
from trigger_set import CONTRACT, MONTHLY

KEYWORDS = {MONTHLY: re.compile(r"月次|レポート|振り返り|数字のまとめ"), CONTRACT: re.compile(r"契約|LC-\d|法務")}
REPORT_TOOLS = [("mcp__report__get_monthly_sales", "sales.json"), ("mcp__report__get_inquiry_counts", "inquiries.json"),
                ("mcp__report__get_inventory_snapshot", "inventory.json")]


def pick(q: str) -> str | None:
    for name, pat in KEYWORDS.items():
        if pat.search(q):
            return name
    return None


def month_of(q: str) -> str:
    m = re.search(r"(20\d\d)-(\d\d)", q)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = re.search(r"(\d{1,2}) ?月", q)
    return f"2026-{int(m.group(1)):02d}" if m else "2026-09"


def keyword(msgs, tools):
    q, done = last_user_text(msgs), tool_results(msgs)
    name = pick(q)
    if not done and name:
        return [use("load_skill", {"name": name}, "ls")]
    return [say("(mock) スキルを使わずに答えます。")]


def follow(msgs, tools):
    q, done = last_user_text(msgs), tool_results(msgs)
    name = pick(q)
    seen = {d["name"]: d for d in done}
    if not done:
        return [use("load_skill", {"name": name}, "ls")] if name else [say("(mock) スキルを使わずに答えます。")]
    if name != MONTHLY:
        return [say("(mock) この筋書きは月次レポートだけを最後まで進めます。")]
    if any(d["is_error"] for d in done):
        return [say("(mock) 道具が失敗したので止めます: " + next(d["text"] for d in done if d["is_error"])[:120])]
    m = month_of(q)
    if not all(t in seen for t, _ in REPORT_TOOLS):                     # 手順 2: 道具を 3 つ呼ぶ
        return [use(t, {"month": m}, f"r{i}") for i, (t, _) in enumerate(REPORT_TOOLS)]
    if "run_skill_script" not in seen:                                  # 手順 3: 返ってきた JSON をそのままファイルに
        files = {fn: json.loads(seen[t]["text"]) for t, fn in REPORT_TOOLS}
        return [use("run_skill_script", {"name": MONTHLY, "script": "scripts/build_report.py",
                                         "input_json": {"args": [fn for _, fn in REPORT_TOOLS], "files": files}}, "rs")]
    if "read_skill_file" not in seen:                                   # 手順 4: 書き方を読む
        return [use("read_skill_file", {"name": MONTHLY, "path": "references/style.md"}, "rf")]
    report = seen["run_skill_script"]["text"].rstrip()
    return [say(report + "\n- 候補: (mock の決まり文句) 数字の組み合わせから言えることを、人が確かめて書く。\n")]


PLANS = {"keyword": keyword, "follow": follow}
