"""規程の当てはめ (経費精算・購買)。data/make_data.py の関数をそのまま使う。

正解を作った規則と、道具が判定に使う規則を同じ一つにしておく (二重に書くと食い違う)。
規則が正しいことは data/check_data.py が、規程の文から別に書き直した規則で照合している。
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import os

from common.kit import DATA

_spec = importlib.util.spec_from_file_location("solaha_make_data", os.path.join(DATA, "make_data.py"))
_md = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_md)   # make_data.py は __main__ のときだけ書き出すので、読み込むだけなら何も書かない

PEOPLE: dict = _md.PEOPLE                 # 氏名 → (部署, 職位)
LADDER: list = _md.LADDER
HOLIDAYS = _md.HOLIDAYS_2026
exp_judge = _md.exp_judge                  # (申請, 全申請) → (decision, reasons, approver)
po_approval = _md.po_approval              # 発注金額 → 承認者 (None は不要)
WEEKDAY = "月火水木金土日"


def is_holiday(d: dt.date) -> bool:
    return d.weekday() >= 5 or d in HOLIDAYS
