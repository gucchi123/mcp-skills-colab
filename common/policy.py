"""顧客情報取扱規程 (data/crm/customer_data_policy.md) を、道具の側で当てはめる。

🔴 見せてよいかどうかはサーバが決める。モデルに「見せないで」と頼むだけでは守れない (指示は破られうる)。
   正解 (data/crm/access_gold.json) とは tests/test_policy.py で 189 組すべてを照合している。
"""
from __future__ import annotations

import copy

HIDDEN = "（非表示）"
MANAGERS = {"課長", "副部長", "部長"}


def visible_fields(user: dict, cust: dict) -> set[str]:
    """規程の条ごとに、見てよい項目を足していく。"""
    v = {"id", "type", "products"}                                  # 第3条1・第4条1: 基本は全社員
    if cust["type"] == "個人":
        if user["role"] == "desk":                                  # 第4条2: 個人の名称と連絡先は窓口だけ
            v |= {"name", "contact.name", "contact.phone", "contact.email", "contact.address"}
        return v
    v.add("name")                                                   # 第3条1: 会社名は全社員
    if user["department"] == "情報システム部":                       # 第5条: 管理者でも中身は見ない
        return v
    sales_mgr = user["role"] == "sales" and user["position"] in MANAGERS
    if sales_mgr or user["department"] == "経理部":                  # 第3条2: 取引条件
        v |= {"rank", "credit_limit_yen"}
    if sales_mgr or cust["sales_rep"] == user["id"]:                # 第3条3: 先方担当者
        v |= {"contact.name", "contact.phone", "contact.email"}
    elif user["role"] == "desk":
        v |= {"contact.name", "contact.phone"}
    return v


def redact(user: dict, cust: dict) -> tuple[dict, list[str]]:
    """見てよくない項目を「（非表示）」に置き換えた写しと、置き換えた項目の一覧を返す (第6条: 隠したことは伏せない)。"""
    vis = visible_fields(user, cust)
    out, hidden = copy.deepcopy(cust), []
    for k in ("name", "sales_rep", "rank", "credit_limit_yen"):
        if k in out and k not in vis and out[k] is not None:
            if k == "sales_rep":
                continue                                            # 担当営業が誰かは社内の情報として全員に見せる
            out[k] = HIDDEN; hidden.append(k)
    for k, val in list(out.get("contact", {}).items()):
        if f"contact.{k}" not in vis:
            out["contact"][k] = HIDDEN; hidden.append(f"contact.{k}")
    return out, hidden
