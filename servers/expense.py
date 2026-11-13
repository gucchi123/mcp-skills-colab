"""経費精算の MCP サーバ (ユースケース 2)。判定 (読むだけ) と、申請の登録 (書き込み) を持つ。

道具:
  check_expense(...)            経費精算規程を当てはめた判定 (自動承認・承認者・経理部の確認・差し戻し) を返す。登録しない
  submit_expense(..., request_id) 申請を登録する (人の確認つき・同じ request_id は二重に登録しない)
  get_expense_status(claim_id)  申請の状況

🔴 申請者は利用者本人だけ (他人の名前で申請させない)。利用者はホストが SOLAHA_USER で渡す。
🔴 判定は data/make_data.py の規則そのもの (common.rules.exp_judge)。モデルに判定させない。
起動: python -m servers.expense
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from mcp.server import MCPServer
from mcp.server.mcpserver import Elicit, Resolve
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from common.identity import NotAllowed, audit, audit_confirm_requested, current_user
from common.kit import append_jsonl, data_path, read_json, read_jsonl, read_text, state_dir, today, utf8_console
from common.rules import PEOPLE, exp_judge

SERVER = "expense"
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITES = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
CATEGORIES = Literal["交通費", "宿泊費", "会議費", "接待交際費", "書籍費", "消耗品費"]
DECISION_JA = {"auto_approve": "自動承認", "needs_manager": "承認者の承認が必要", "needs_finance": "経理部の確認が必要",
               "reject": "差し戻し"}
PAST = read_json(data_path("expense", "claims.json"))

mcp = MCPServer(SERVER, instructions="ソラハ電機 (架空) の経費精算。判定は規程の規則で行い、登録は利用者の確認を取ってから。")


class Judgement(BaseModel):
    decision: str = Field(description="自動承認 / 承認者の承認が必要 / 経理部の確認が必要 / 差し戻し")
    reasons: list[str] = Field(description="差し戻し・経理部の確認の事由")
    approver: str | None = Field(description="承認者の職位 (承認が必要なとき)")


class Submitted(Judgement):
    claim_id: str
    request_id: str
    duplicate: bool


def _claims_path() -> str:
    return os.path.join(state_dir(), "expenses.jsonl")


def _submitted() -> list[dict]:
    return read_jsonl(_claims_path()) if os.path.exists(_claims_path()) else []


def _claim(employee: str, category: str, expense_date: str, amount: int, vendor: str, description: str,
           receipt: bool, ic_record: bool, attendees: int | None, nights: int | None, pre_approval: str | None,
           submitted: str | None) -> dict:
    if employee not in PEOPLE:
        raise ToolError(f"社員 {employee} は経費精算の名簿にありません")
    try:
        dt.date.fromisoformat(expense_date)
        sub = submitted or today().isoformat()
        dt.date.fromisoformat(sub)
    except ValueError:
        raise ToolError("日付は YYYY-MM-DD で渡してください") from None
    if category in ("会議費", "接待交際費") and not attendees:
        raise ToolError(f"{category}は人数 (attendees) が要ります")
    if category == "宿泊費" and not nights:
        raise ToolError("宿泊費は泊数 (nights) が要ります")
    dept, pos = PEOPLE[employee]
    return {"employee": employee, "department": dept, "position": pos, "category": category, "expense_date": expense_date,
            "submitted": sub, "amount": int(amount), "attendees": attendees, "nights": nights, "receipt": receipt,
            "ic_record": ic_record, "pre_approval": pre_approval, "vendor": vendor, "description": description}


def _judge(c: dict) -> Judgement:
    others = PAST + _submitted()
    d, reasons, approver = exp_judge({**c, "id": c.get("id", "NEW")}, others)
    return Judgement(decision=DECISION_JA[d], reasons=reasons, approver=approver)


@mcp.tool(title="経費の判定", annotations=READ_ONLY)
def check_expense(employee: str, category: CATEGORIES, expense_date: str, amount: int, vendor: str,
                  description: str, receipt: bool, ic_record: bool = False, attendees: int | None = None,
                  nights: int | None = None, pre_approval: str | None = None, submitted: str | None = None) -> Judgement:
    """経費精算規程を当てはめて、申請がどう扱われるか (自動承認・承認者の承認・経理部の確認・差し戻しと事由) を返す。登録はしない。
    employee は申請者の氏名。expense_date・submitted は YYYY-MM-DD (submitted を省くと今日 = 講座では 2026-10-24)。amount は税込みの円。
    会議費・接待交際費は attendees (人数)、宿泊費は nights (泊数)、接待交際費は pre_approval (事前申請の番号 PA-xxxx) を渡す。
    receipt は領収書の有無、ic_record は交通系 IC カードの利用履歴の有無。"""
    j = _judge(_claim(employee, category, expense_date, amount, vendor, description, receipt, ic_record, attendees,
                      nights, pre_approval, submitted))
    audit(SERVER, "check_expense", employee=employee, amount=amount, decision=j.decision)
    return j


class Confirm(BaseModel):
    ok: bool = Field(description="この内容で申請してよければ true")


def ask_confirm(employee: str, category: str, expense_date: str, amount: int, vendor: str, request_id: str
                ) -> Elicit[Confirm] | Confirm:
    """登録の前に利用者へ確認する。同じ依頼の 2 回目と、どのみち断る申請 (本人以外・利用者が決まらない) は確認を求めない。"""
    if any(c["request_id"] == request_id for c in _submitted()):
        return Confirm(ok=True)
    try:
        if employee != current_user()["name"]:
            return Confirm(ok=False)          # 本体が「本人以外」で断る。断る申請に「よろしいですか」を出さない
    except NotAllowed:
        return Confirm(ok=False)              # 本体が「利用者が決まっていません」で断る
    # 🔴 断られた (decline) ときは本体まで来ない (SDK が先に失敗を返す)。確認を求めたことはここで残す
    audit_confirm_requested(SERVER, "submit_expense", request_id, amount=int(amount))
    return Elicit(f"経費を申請します: {employee}・{category}・{expense_date}・{vendor}・{int(amount):,} 円。よろしいですか。", Confirm)


@mcp.tool(title="経費を申請する", annotations=WRITES)
def submit_expense(employee: str, category: CATEGORIES, expense_date: str, amount: int, vendor: str,
                   description: str, receipt: bool, request_id: str,
                   confirm: Annotated[Confirm, Resolve(ask_confirm)],
                   ic_record: bool = False, attendees: int | None = None, nights: int | None = None,
                   pre_approval: str | None = None) -> Submitted:
    """経費の申請を登録する (申請者は利用者本人だけ)。登録の前に利用者に内容を見せて確認を取る。
    引数の意味は check_expense と同じ。request_id は申請ごとに一つ決めた文字列で、同じ request_id で呼び直しても二重には登録しない。
    判定 (自動承認・承認者・経理部・差し戻し) も一緒に返す。差し戻しに当たる申請も登録はされ、差し戻しの状態になる。"""
    try:
        user = current_user()
    except NotAllowed as e:
        raise ToolError(str(e)) from None
    prev = next((c for c in _submitted() if c["request_id"] == request_id), None)
    if prev:
        audit(SERVER, "submit_expense", request_id=request_id, duplicate=True, claim_id=prev["id"])
        return Submitted(claim_id=prev["id"], request_id=request_id, duplicate=True, **prev["judgement"])
    if employee != user["name"]:
        audit(SERVER, "submit_expense", request_id=request_id, refused="本人以外の申請", employee=employee)
        raise ToolError(f"申請者 ({employee}) が利用者 ({user['name']}) と違います。経費は本人だけが申請できます")
    if not confirm.ok:
        audit(SERVER, "submit_expense", request_id=request_id, declined=True)
        raise ToolError("利用者が申請を取りやめました。登録していません")
    c = _claim(employee, category, expense_date, amount, vendor, description, receipt, ic_record, attendees, nights,
               pre_approval, None)
    j = _judge(c)
    cid = f"N-{len(_submitted()) + 1:04d}"
    append_jsonl(_claims_path(), [{**c, "id": cid, "request_id": request_id, "judgement": j.model_dump(),
                                   "at": dt.datetime.now().isoformat(timespec="seconds")}])
    audit(SERVER, "submit_expense", request_id=request_id, claim_id=cid, decision=j.decision)
    return Submitted(claim_id=cid, request_id=request_id, duplicate=False, **j.model_dump())


@mcp.tool(title="申請の状況", annotations=READ_ONLY)
def get_expense_status(claim_id: str) -> Judgement:
    """申請番号 (過去の申請 E-01〜E-42、この窓口で登録した N-0001 など) の判定と状況を返す。"""
    cid = claim_id.strip().upper()
    c = next((x for x in PAST if x["id"] == cid), None)
    if c:
        j = _judge({k: v for k, v in c.items() if k != "gold"})
    else:
        s = next((x for x in _submitted() if x["id"] == cid), None)
        if not s:
            raise ToolError(f"申請 {claim_id} は見つかりません")
        j = Judgement(**s["judgement"])
    audit(SERVER, "get_expense_status", claim_id=cid)
    return j


@mcp.resource("expense://policy", title="経費精算規程", mime_type="text/markdown")
def policy() -> str:
    return read_text(data_path("expense", "policy.md"))


if __name__ == "__main__":
    utf8_console()
    mcp.run()
