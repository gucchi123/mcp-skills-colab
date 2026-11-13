"""当たった項目から、総合の判定を出す (チェックリストの「総合の判定」をそのまま書いたもの)。
usage: python overall.py '[{"rule": "R4", "level": "高"}, ...]'     当たる項目が無ければ '[]'
"""
import json
import sys

LEVELS = {"R1": {"中"}, "R2": {"高"}, "R3": {"中"}, "R4": {"高", "中"}, "R5": {"高"}, "R6": {"低"}, "R7": {"中"}}


def overall(findings: list[dict]) -> str:
    for f in findings:
        if f["rule"] not in LEVELS or f["level"] not in LEVELS[f["rule"]]:
            raise ValueError(f"チェックリストに無い組み合わせ: {f['rule']} {f['level']}")
    levels = {f["level"] for f in findings}
    if "高" in levels:
        return "法務室レビュー必須"
    if "中" in levels:
        return "部長確認"
    if "低" in levels:
        return "担当者確認"
    return "問題なし"


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(overall(json.loads(sys.argv[1] if len(sys.argv) > 1 else "[]")))
