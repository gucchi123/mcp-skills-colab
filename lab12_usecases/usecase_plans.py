"""ラボ 12 の偽モデル (mock) の筋書き。5 つの場面それぞれで「正しい手順」を踏む (right)。
対照として、ありがちな手抜きを 1 つずつ入れた筋書き (sloppy) も持つ (採点が間違いを拾えるかを見る)。

API キーが無くても、ホスト → MCP サーバ → 確認 → 登録 → 監査ログ → 採点 の流れを最後まで動かすためのもの。
道具の結果 (在庫・判定・台帳・数字・スクリプトの出力) は本物のサーバとスクリプトが返す。筋書きが決めているのは
「どの道具をどの順に呼ぶか」と「最後の文の書き方」だけ。
🔴 筋書きは講師が書いた決まった動き。数字 (合格の数) は Claude の性能の証拠にならない。本物は RUN_LOG.md の記録で見る。
"""
from __future__ import annotations

import json
import re

from common.llm import say, tool_results, use
from usecases import first_text

# UC1: 答えの文 (講師が規程を読んで書いた)。根拠の文書番号と節は、検索の結果から筋書きが選んで付ける
KB_ANSWERS = {
    "K-1": "国内出張は、出発日の7日前までに申請します (海外出張は14日前まで)。",
    "K-2": "課長が部長の代理者となる場合、100万円を超える案件は代理承認できません。その案件は本部長が承認します。",
    "K-3": "法務室長が不在のときは、管理本部長が代わりに承認します。",
    "K-4": "月8日を超えるので、所属部署の部長の承認が要ります (月8日までなら課長)。",
    "K-5": "決裁者が承認する前に、経理部長の合議 (同意) を得る必要があります。",
    "K-6": "締結した契約書の原本は法務室が保管します。",
    "K-7": "50万円超300万円以下なので、所属本部の本部長が承認します。",
}
# UC5: 講師がチェックリストと読み方の注意 (reading_notes.md) に沿って契約書を読んだ結果 (筋書きの台本)
CONTRACT_READING = {
    "LC-01": [],
    "LC-02": [("R1", "中", "第2条"), ("R2", "高", "第3条"), ("R3", "中", "第3条"), ("R4", "中", "第4条"), ("R6", "低", "第6条")],
    "LC-03": [("R4", "高", "第4条")],
    "LC-04": [("R5", "高", "第6条"), ("R6", "低", "第6条")],
    "LC-05": [("R1", "中", "第2条"), ("R7", "中", "-")],
    "LC-06": [("R3", "中", "第3条")],
    "LC-07": [("R6", "低", "第6条")],
    "LC-08": [("R1", "中", "第2条"), ("R2", "高", "第3条"), ("R3", "中", "第3条"), ("R6", "低", "第6条")],
}


def _json(d: dict) -> dict:
    return json.loads(d["text"])


def _str(d: dict) -> str:
    """文字列を返す道具の結果。MCP は構造化して {"result": "..."} で返すので、中身を取り出す。"""
    t = d["text"]
    if t.startswith('{"result"'):
        return json.loads(t)["result"]
    return t


def _grams(s: str) -> set[str]:
    s = re.sub(r"\s+", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def kb_plan(case):
    def plan(msgs, tools):
        done = tool_results(msgs)
        if not done:
            return [use("mcp__kb__search_regulations", {"query": case["q"], "top_k": 3}, "s")]
        hits = _json(done[0])["result"] if not done[0]["is_error"] else []
        if not hits:
            return [say("規程に記載がありません。")]
        # 検索の 1 位をそのまま根拠にしない: 改定履歴 (a-13) は「何が変わったか」の記録なので外し、
        # 残りから、文書の題と節の見出しが問いといちばん重なるものを選ぶ (同じなら検索の順)
        body = [x for x in hits if x["doc_id"] != "a-13"] or hits
        q = _grams(case["q"])
        h = max(body, key=lambda x: (len(q & _grams(x["title"] + x["section"])), -body.index(x)))
        return [say(f"{KB_ANSWERS[case['id']]}\n根拠: {h['doc_id']} {h['section']}")]
    return plan


def reg_plan(case):
    def expense(msgs, tools):
        done = tool_results(msgs)
        args = {"employee": "山根 翔太", **case["slip"]}
        if not done:
            return [use("mcp__expense__check_expense", args, "c")]
        if len(done) == 1:
            j = _json(done[0])
            if j["decision"] == "差し戻し":
                return [say(f"この申請は規程では差し戻しになるため、申請していません。理由: {'、'.join(j['reasons'])}。")]
            return [use("mcp__expense__submit_expense", {**args, "request_id": f"uc2-{case['id']}-{args['expense_date']}"}, "s")]
        last = done[-1]
        if last["is_error"]:
            return [say(f"申請していません: {last['text'][:80]}")]
        s = _json(last)
        return [say(f"申請しました ({s['claim_id']})。判定は「{s['decision']}」"
                    + (f"、承認者は{s['approver']}です。" if s["approver"] else "です。"))]

    def order(msgs, tools):
        done = tool_results(msgs)
        if not done:
            return [use("mcp__inventory__get_stock", {"sku": case["sku"]}, "g")]
        if len(done) == 1:
            st = _json(done[0])
            if not st["needs_order"]:
                return [say(f"{st['sku']} は在庫 {st['stock']:,} が発注点 {st['reorder_point']:,} を上回っているので、発注は不要です。")]
            usable = [x for x in (st["supplier"], st["alt_supplier"]) if x and "取引中" in x]
            if not usable:
                return [say(f"{st['sku']} は主の発注先が取引停止で、代わりの発注先もありません。発注せず、調達担当に回します。")]
            return [use("mcp__inventory__create_purchase_order", {"sku": case["sku"], "request_id": f"uc2-{case['id']}"}, "p")]
        last = done[-1]
        if last["is_error"]:
            return [say(f"発注は登録していません: {last['text'][:60]}")]
        o = _json(last)
        if o["status"] == "登録しない":
            return [say(f"発注は登録しませんでした: {o['note']}")]
        return [say(f"発注を登録しました ({o['order_id']}・{o['qty']:,} 個・{o['amount_yen']:,} 円)。状態は「{o['status']}」"
                    + (f"で、{o['approver']}の承認を受けてから発注先へ送ります。" if o["approver"] else "です。"))]
    return expense if case["kind"] == "expense" else order


def crm_plan(case):
    def plan(msgs, tools):
        done = tool_results(msgs)
        cid = re.search(r"(C-\d{3}|IND-\d{3})", first_text(msgs)).group(1)
        if not done:
            return [use("mcp__crm__get_customer", {"customer_id": cid}, "g")]
        if done[0]["is_error"]:
            return [say(f"台帳を読めませんでした: {done[0]['text'][:60]}")]
        c = _json(done[0])
        ct = c["contact"]
        if c["type"] == "個人":
            body = f"お名前: {c['name']} / 電話: {ct.get('phone')}"
        else:
            body = (f"先方担当者: {ct.get('name')} / 電話: {ct.get('phone')} / メール: {ct.get('email')} / "
                    f"与信枠: {c['credit_limit_yen'] if not isinstance(c['credit_limit_yen'], int) else format(c['credit_limit_yen'], ',') + ' 円'}")
        tail = "\n（非表示）の項目は、あなたの権限では見られません。" if c["hidden"] else ""
        return [say(f"{c['id']} {c['name']}\n{body}{tail}")]
    return plan


def report_plan(case):
    def plan(msgs, tools):
        done = tool_results(msgs)
        m = case["month"]
        if not done:
            return [use("mcp__report__get_monthly_sales", {"month": m}, "s"),
                    use("mcp__report__get_inquiry_counts", {"month": m}, "q"),
                    use("mcp__report__get_inventory_snapshot", {"month": m}, "i")]
        if len(done) == 3:
            return [use("mcp__skill__run_skill_script", {"skill": "solaha-monthly-report", "script": "build_report.py",
                                                         "inputs": [d["text"] for d in done]}, "b"),
                    use("mcp__skill__read_skill_file", {"skill": "solaha-monthly-report", "path": "references/style.md"}, "r")]
        out = next(d for d in done if d["tool_use_id"] == "b")
        if out["is_error"]:
            return [say(f"レポートを作れませんでした: {out['text'][:80]}")]
        return [say(_str(out) + "\n- 候補: 前月比が大きく動いた製品について、理由を担当に確かめる"
                    "\n- 候補: 発注点以下の品目の補充の予定を、製造部に確かめる")]
    return plan


def contract_plan(case):
    def plan(msgs, tools):
        done = tool_results(msgs)
        cid = case["contract"]
        if not done:
            return [use("mcp__contract__get_contract_checklist", {}, "k"),
                    use("mcp__skill__read_skill_file", {"skill": "solaha-contract-review", "path": "references/reading_notes.md"}, "n")]
        if len(done) == 2:
            return [use("mcp__contract__get_contract", {"contract_id": cid}, "c")]
        if len(done) == 3:
            found = [{"rule": r, "level": lv} for r, lv, _ in CONTRACT_READING[cid]]
            return [use("mcp__skill__run_skill_script", {"skill": "solaha-contract-review", "script": "overall.py",
                                                         "inputs": [json.dumps(found, ensure_ascii=False)]}, "o")]
        text = _str(done[2])
        title = text.splitlines()[0].lstrip("# ").split("（")[0]
        party = text.split("乙: ")[1].split("（")[0] if "乙: " in text else "-"
        verdict = _str(done[3]).strip()
        hits = {r: (lv, art) for r, lv, art in CONTRACT_READING[cid]}
        rows = "\n".join(f"| R{i} | 当たる | {hits[f'R{i}'][0]} | {hits[f'R{i}'][1]} |" if f"R{i}" in hits
                         else f"| R{i} | 当たらない | - | - |" for i in range(1, 8))
        ask = [f"R{i}" for i in range(1, 8) if hits.get(f"R{i}", ("",))[0] == "高"]
        return [say(f"契約書: {cid} {title} (相手方: {party})\n総合の判定: {verdict}\n\n| 番号 | 判定 | 重さ | 根拠 |\n|---|---|---|---|\n{rows}\n\n"
                    f"人が確かめること: {('、'.join(ask) + ' の条項を法務室に確認する') if ask else '特になし'}")]
    return plan


# ---------------------------------------------------------------- 手を抜く筋書き (sloppy)
# 採点が「起きたこと」で間違いを拾えるかを見るための対照。どれも、ありがちな手抜きを 1 つだけ入れてある。
def kb_sloppy(case):
    """検索の 1 位をそのまま根拠にする (K-4 は 1 位が改定履歴 a-13)。"""
    def plan(msgs, tools):
        done = tool_results(msgs)
        if not done:
            return [use("mcp__kb__search_regulations", {"query": case["q"], "top_k": 3}, "s")]
        h = _json(done[0])["result"][0]
        return [say(f"{KB_ANSWERS[case['id']]}\n根拠: {h['doc_id']} {h['section']}")]
    return plan


def reg_sloppy(case):
    """判定も在庫も確かめずに、いきなり登録の道具を呼ぶ (守りはサーバの側だけ)。"""
    def plan(msgs, tools):
        done = tool_results(msgs)
        if not done:
            if case["kind"] == "expense":
                return [use("mcp__expense__submit_expense", {"employee": "山根 翔太", **case["slip"],
                                                             "request_id": f"uc2s-{case['id']}"}, "s")]
            return [use("mcp__inventory__create_purchase_order", {"sku": case["sku"], "request_id": f"uc2s-{case['id']}"}, "p")]
        return [say("登録しました。" if not done[-1]["is_error"] else "登録できませんでした。")]
    return plan


def crm_sloppy(case):
    """台帳の値をそのまま並べ、見られない項目があることには触れない。"""
    def plan(msgs, tools):
        done = tool_results(msgs)
        cid = re.search(r"(C-\d{3}|IND-\d{3})", first_text(msgs)).group(1)
        if not done:
            return [use("mcp__crm__get_customer", {"customer_id": cid}, "g")]
        c = _json(done[0])
        vals = [str(v) for k, v in c["contact"].items() if v != "（非表示）"] + \
               [str(c[k]) for k in ("name", "credit_limit_yen") if c.get(k) not in (None, "（非表示）")]
        return [say(" / ".join(vals) or "分かりませんでした。")]
    return plan


def report_sloppy(case):
    """スクリプトを使わず、数字を自分で書く (前月比を整数に丸め、いくつかの節を省く)。"""
    def plan(msgs, tools):
        done = tool_results(msgs)
        m = case["month"]
        if not done:
            return [use("mcp__report__get_monthly_sales", {"month": m}, "s"),
                    use("mcp__report__get_inquiry_counts", {"month": m}, "q")]
        s, q = _json(done[0]), _json(done[1])
        pct = round((s["total_yen"] - s["prev_total_yen"]) / s["prev_total_yen"] * 100)
        return [say(f"# 月次レポート（{m}）\n## 1. 売上\n- 売上合計: {s['total_yen']:,} 円（前月比 {pct:+d}%）\n"
                    f"## 2. 問い合わせ\n- 件数の合計: {q['total']:,} 件\n## 4. 次の一手\n- 在庫を増やすべきです。")]
    return plan


def contract_sloppy(case):
    """チェックリストを読まず、総合の判定を自分で決める (何か当たれば法務室、の思い込み)。"""
    def plan(msgs, tools):
        done = tool_results(msgs)
        cid = case["contract"]
        if not done:
            return [use("mcp__contract__get_contract", {"contract_id": cid}, "c")]
        hits = CONTRACT_READING[cid]
        rows = "\n".join(f"| {r} | 当たる | {lv} | {art} |" for r, lv, art in hits)
        return [say(f"契約書: {cid}\n総合の判定: {'法務室レビュー必須' if hits else '問題なし'}\n\n| 番号 | 判定 | 重さ | 根拠 |\n|---|---|---|---|\n{rows}")]
    return plan


PLANS = {1: kb_plan, 2: reg_plan, 3: crm_plan, 4: report_plan, 5: contract_plan}
SLOPPY = {1: kb_sloppy, 2: reg_sloppy, 3: crm_sloppy, 4: report_sloppy, 5: contract_sloppy}


def make_plan(uc: int, cases: list[dict], kind: str = "right"):
    """最初の依頼文から場面を見分けて、その場面の筋書きに回す。kind は right (正しい手順) / sloppy (手抜き)。"""
    plans = PLANS if kind == "right" else SLOPPY
    by_q = {c["q"]: plans[uc](c) for c in cases}

    def plan(msgs, tools):
        return by_q[first_text(msgs)](msgs, tools)
    return plan
