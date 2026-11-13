"""ラボ 4 の部品: 道具の欄 (tools) の作り替え・偽モデル (キーワード照合)・採点。

  道具の欄の 4 通り (どれも 6 サーバの 17 個から作る。引数の形 input_schema は変えない):
    good   : サーバが出したまま (名前 mcp__<サーバ>__<道具>・説明も元のまま)
    vague  : 説明だけを短いあいまいな一言にする (「データを取得する」など)。名前は元のまま
    names  : 名前だけを tool01〜tool17 にする。説明は元のまま
    subset : 問いの分野のサーバの道具だけを見せる (2〜3 個)。名前も説明も元のまま
  採点は「最初の tool_use の道具」だけを見る。道具は実行しない。

偽モデル (mock) の筋書き = キーワード照合 (KeywordRouter):
  問いの 2 文字組と、渡された道具の説明 (と、名前の英単語を小さな辞書で日本語にしたもの) の重なりで点を付け、
  いちばん点の高い道具を選ぶ。点が低ければ道具を使わない。決まった計算なので毎回同じ答えになる。
  🔴 渡された説明・名前だけを見るので、道具の欄を変えると選び方も変わる (配線が働いていることの確認)。
     ただし数字は Claude の性能の証拠にならない。Claude がどう選ぶかは、キーを入れて回した記録で見る。
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter

from common.kit import data_path, read_json, read_jsonl
from common.llm import say, use

VARIANTS = ("good", "vague", "names", "subset")
VARIANT_JA = {"good": "元の説明", "vague": "あいまいな説明", "names": "名前を番号に", "subset": "分野の道具だけ"}

# あいまいな説明 (一言)。わざと「何の」データかを書かない
VAGUE = {
    "search_regulations": "情報を探す",
    "get_regulation": "文書を取得する",
    "find_customer": "データを探す",
    "get_customer": "データを取得する",
    "list_customers_by_product": "一覧を取得する",
    "get_stock": "情報を取得する",
    "list_below_reorder": "一覧を返す",
    "create_purchase_order": "登録する",
    "check_expense": "確認する",
    "submit_expense": "申請する",
    "get_expense_status": "状況を返す",
    "get_monthly_sales": "数字を取得する",
    "get_inquiry_counts": "件数を返す",
    "get_inventory_snapshot": "データを返す",
    "list_contracts": "一覧を返す",
    "get_contract": "文書を取得する",
    "get_contract_checklist": "項目を返す",
}


def short(name: str | None) -> str | None:
    """mcp__kb__search_regulations → search_regulations"""
    return name.split("__")[-1] if name else None


def server_of(name: str | None) -> str:
    return name.split("__")[1] if name and name.count("__") >= 2 else "なし"


def load_questions() -> list[dict]:
    return read_jsonl(data_path("questions", "tool_selection.jsonl"))


def catalog_server() -> dict[str, str]:
    """道具の名前 (短い) → サーバ名。data/questions/tool_catalog.json から。"""
    return {t: s for s, ts in read_json(data_path("questions", "tool_catalog.json")).items() for t in ts}


def domain(q: dict) -> str:
    """問いの分野 = 最初に呼ぶべき道具のサーバ。道具が要らない問いは kb にする (subset のときに見せる道具)。"""
    return catalog_server().get(q["first_tool"], "kb") if q["first_tool"] else "kb"


# ---------------------------------------------------------------- 道具の欄を作り替える
def make_tools(variant: str, tools: list[dict], q: dict | None = None) -> tuple[list[dict], dict[str, str]]:
    """(モデルに渡す道具の欄, 渡した名前 → 元の名前) を返す。元の tools は書き換えない。"""
    out, back = [], {}
    for i, t in enumerate(tools, 1):
        t = json.loads(json.dumps(t))
        orig = t["name"]
        if variant == "vague":
            t["description"] = VAGUE[short(orig)]
        elif variant == "names":
            t["name"] = f"tool{i:02d}"
        elif variant == "subset":
            if server_of(orig) != domain(q):
                continue
        elif variant != "good":
            raise ValueError(f"variant が不明です: {variant}")
        back[t["name"]] = orig
        out.append(t)
    return out, back


def block_size(tools: list[dict]) -> dict:
    """道具の欄の大きさ。tokens_est は目安 (ASCII 4 字 = 1、それ以外 1 字 = 1 で数えた概算)。
    本物の数は Claude の応答の usage.input_tokens (道具の欄を含む入力全体) で見る。"""
    s = json.dumps(tools, ensure_ascii=False)
    asc = sum(1 for ch in s if ord(ch) < 128)
    return {"tools": len(tools), "chars": len(s), "tokens_est": math.ceil(asc / 4 + (len(s) - asc))}


# ---------------------------------------------------------------- 偽モデル: キーワード照合
GLOSSARY = {   # 名前の英単語 → 日本語 (名前から読み取れることを、この小さな辞書の分だけ照合に足す)
    "kb": "規程", "crm": "顧客", "inventory": "在庫", "expense": "経費", "report": "月次", "contract": "契約",
    "search": "探す", "regulations": "規程", "regulation": "規程", "find": "探す", "customer": "顧客",
    "customers": "顧客", "product": "製品", "stock": "在庫", "below": "下回る", "reorder": "発注点",
    "purchase": "購入", "order": "発注", "check": "確認", "submit": "申請", "status": "状況", "monthly": "月次",
    "sales": "売上", "inquiry": "問い合わせ", "counts": "件数", "snapshot": "月末", "contracts": "契約",
    "checklist": "チェックリスト", "list": "一覧", "create": "登録",
}
_KEEP = re.compile(r"[一-鿿゠-ヿA-Za-z0-9]")   # 漢字・カタカナ・英数を含む組だけ数える
THRESHOLD = 1.0                                                # これより低ければ道具を使わない


def _grams(s: str) -> set[str]:
    s = re.sub(r"[\s、。？?！!・「」（）()]", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1) if _KEEP.search(s[i:i + 2])}


def tool_text(t: dict) -> str:
    words = re.split(r"[_\W]+", t["name"])
    return (t.get("description") or "") + " " + " ".join(GLOSSARY.get(w, "") for w in words)


def route(question: str, tools: list[dict]) -> tuple[str | None, float]:
    """(選んだ道具の名前 or None, 点)。点 = 重なった 2 文字組ごとに 1/(その組を持つ道具の数) の和。同点は欄の先の道具。"""
    if not tools:
        return None, 0.0
    tg = [_grams(tool_text(t)) for t in tools]
    df = Counter(g for s in tg for g in s)
    q = _grams(question)
    best, score = None, 0.0
    for t, g in zip(tools, tg):
        sc = sum(1 / df[x] for x in q & g)
        if sc > score:
            best, score = t["name"], sc
    return (best, round(score, 2)) if score >= THRESHOLD else (None, round(score, 2))


class KeywordRouter:
    """mock の筋書き。MockProvider は筋書きに道具の名前しか渡さないので、渡された request (説明つき) を
    provider.requests[-1] から読む (attach で結びつける)。🔴 数字は性能の証拠にならない。"""

    def __init__(self):
        self.prov = None

    def attach(self, prov) -> "KeywordRouter":
        self.prov = prov
        return self

    def __call__(self, messages, tool_names):
        tools = self.prov.requests[-1].get("tools", []) if self.prov else [{"name": n} for n in tool_names]
        question = messages[-1]["content"][0]["text"]
        name, _ = route(question, tools)
        if name is None:
            return [say("（mock: 道具を使わずに答えます）")]
        return [use(name, {}, "first")]


# ---------------------------------------------------------------- 採点
def first_tool_use(resp: dict) -> tuple[str | None, str]:
    """応答の最初の tool_use の名前 (無ければ None) と、文の先頭 (道具を使わなかったとき見る)。"""
    blocks = resp.get("content", [])
    name = next((b["name"] for b in blocks if b.get("type") == "tool_use"), None)
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    return name, text.strip().replace("\n", " ")[:60]


def score_row(q: dict, picked: str | None, back: dict[str, str]) -> dict:
    """picked はモデルが名乗った名前 (variant の名前)。元の名前に戻して採点する。"""
    orig = back.get(picked) if picked else None
    pred = short(orig) if orig else (f"?{picked}" if picked else None)     # ?xxx = 渡していない名前
    srv = catalog_server()
    return {"id": q["id"], "expected": q["first_tool"], "expected_tools": q["expected_tools"], "picked": picked,
            "pred": pred, "ok": pred == q["first_tool"],
            "ok_also": pred == q["first_tool"] or pred in q.get("also_ok", []),     # 別解 (データの why) も正解とする
            "in_expected": (pred in q["expected_tools"]) if pred else not q["expected_tools"],
            "exp_server": srv.get(q["first_tool"], "なし"), "pred_server": srv.get(pred, "なし" if pred is None else "?")}


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    conf: dict[str, Counter] = {}
    for r in rows:
        conf.setdefault(r["exp_server"], Counter())[r["pred_server"]] += 1
    none = [r for r in rows if r["pred"] is None]
    return {"n": n, "first_ok": sum(r["ok"] for r in rows), "first_ok_also": sum(r.get("ok_also", r["ok"]) for r in rows),
            "in_expected": sum(r["in_expected"] for r in rows),
            "no_tool": len(none), "no_tool_correct": sum(1 for r in none if r["expected"] is None),
            "no_tool_missed": sum(1 for r in none if r["expected"] is not None),
            "tool_when_none": sum(1 for r in rows if r["expected"] is None and r["pred"] is not None),
            "unknown_name": sum(1 for r in rows if r["pred"] and r["pred"].startswith("?")),
            "wrong": [r["id"] for r in rows if not r["ok"]],
            "wrong_also": [r["id"] for r in rows if not r.get("ok_also", r["ok"])],
            "confusion": {k: dict(v) for k, v in conf.items()}}
