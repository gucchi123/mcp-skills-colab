"""キットの共通部品: データの場所と読み込み、出力の置き場所。

🔴 データはすべて架空 (ソラハ電機株式会社)。data/ は直接書き換えない。直すなら data/make_data.py・make_extra.py を直して作り直す。
"""
from __future__ import annotations

import csv
import json
import os
import sys
from typing import Any, Iterable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")


def data_path(*p: str) -> str:
    return os.path.join(DATA, *p)


def read_text(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def read_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def read_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def append_jsonl(path: str, rows: Iterable[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_csv(path: str) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def state_dir() -> str:
    """サーバが書き込む場所 (登録した経費・発注・監査ログ)。既定はキットの state/。テストでは一時フォルダに向ける。"""
    d = os.environ.get("SOLAHA_STATE_DIR") or os.path.join(ROOT, "state")
    os.makedirs(d, exist_ok=True)
    return d


def utf8_console() -> None:
    """Windows のコンソールで日本語が化けないようにする (プロトコルの中身は元から UTF-8)。"""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def use_labs() -> None:
    """ノートブックから labNN_*/ のモジュールを import できるようにする。"""
    import glob
    for d in sorted(glob.glob(os.path.join(ROOT, "lab*"))):
        if os.path.isdir(d) and d not in sys.path:
            sys.path.insert(0, d)
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)


def out_dir(lab: str) -> str:
    """講師の実行結果の置き場所 (labNN_*/out/)。LAB_OUT=out_mock なら自己検査用の置き場所に書く。"""
    d = os.path.join(ROOT, lab, os.environ.get("LAB_OUT", "out"))
    os.makedirs(d, exist_ok=True)
    return d


def write_jsonl(path: str, rows: Iterable[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# 講座の業務の「今日」。申請日などに使う。いつ回しても同じ結果になるよう固定し、SOLAHA_TODAY=YYYY-MM-DD で変えられる
COURSE_TODAY = "2026-10-24"


def today():
    import datetime as _dt
    return _dt.date.fromisoformat(os.environ.get("SOLAHA_TODAY") or COURSE_TODAY)
