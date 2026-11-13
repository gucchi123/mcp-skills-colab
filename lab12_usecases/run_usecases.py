"""ラボ 12: ソラハ電機 (架空) の 5 つの業務を最後まで流し、正解と機械で照合する。

    python run_usecases.py --show                                   # 5 場面を少しずつ (各 1〜2 件)、やりとりも表示
    python run_usecases.py --uc 2 --all --show                      # 経費・発注の登録 10 件 (確認の画面も出る)
    python run_usecases.py --uc 3 --only U-01/C-001,U-06/C-001      # 同じ問いを、営業と経理で
    python run_usecases.py --uc 4 --only 2026-08                    # 8 月の月次レポート (Skill)
    python run_usecases.py --all --name all                         # 全場面・全件、結果を out/ に残す
    python run_usecases.py --all --plan sloppy                      # 手抜きの筋書きで、採点が間違いを拾うか (mock だけ)

  --uc 1..5 / all   1 規程の問い合わせ 2 経費・発注の登録 3 顧客台帳の照会と権限 4 月次レポート 5 契約書の一次レビュー
  --provider mock / replay / anthropic (既定は環境変数 LLM_PROVIDER、無ければ mock)
--plan right / sloppy は mock の筋書き (mock のときだけ効く)。🔴 合格の数は Claude の性能の証拠にならない。
登録・監査ログは、走らせるたびに空にした out/state_<name>/ に書く (前の実行の記録と混ざらないように)。
UC2 の伝票の日付と、サーバが付ける申請日は、どちらも講座の「今日」(common.kit.today、既定 2026-10-24) で決まる。
いつ回しても同じ結果になる (記録の再生も古くならない)。--today で変えると両方が一緒に変わる (環境変数 SOLAHA_TODAY)。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import sys
import time

import anyio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import llm as L  # noqa: E402
from common.host import Host  # noqa: E402
from common.kit import out_dir, state_dir, write_json, write_jsonl  # noqa: E402
from uc_skill_host import SkillHost, load_skill, skill_system  # noqa: E402
from usecase_plans import make_plan  # noqa: E402
from usecases import (CONTRACT_SYSTEM, CONTRACT_USER, CRM_SYSTEM, DEFAULT_CASES, KB_SYSTEM, KB_USER,  # noqa: E402
                      REG_SYSTEM, REG_USER, REPORT_SYSTEM, REPORT_USER, UC_TITLE, SlipApprover, all_cases,
                      judge_contract, judge_crm, judge_kb, judge_reg, judge_report, state_rows)

LAB = "lab12_usecases"


def show(r, width: int = 110) -> None:
    """記録を画面に出す (common.host.show と同じ形。道具の引数と結果は短く切る: 月次の JSON が長いので)。"""
    cut = lambda s: s[:width] + ("…" if len(s) > width else "")  # noqa: E731
    for e in r.trace:
        if e["type"] == "model":
            if e["text"]:
                print(f"🤖 {e['text']}")
            for u in e["tool_uses"]:
                print(f"   → {u['name']} {cut(json.dumps(u['input'], ensure_ascii=False))}")
        elif e["type"] == "tool":
            print(f"   {'✗' if e['is_error'] else '✓'} {e['tool']}: {cut(e['text'].replace(chr(10), ' '))}")
        elif e["type"] == "confirm":
            print(f"   ? 確認 {e['tool']}: {e['message']} → {e['action']}")
    print(f"[{r.stop}] in={r.usage['input_tokens']} out={r.usage['output_tokens']}")


async def _run(h, uc, case, show_it):
    with L.tag(f"{LAB}/uc{uc}/{case['id']}"):
        r = await h.run(case["q"])
    if show_it:
        show(r)
    return r


async def run_uc(uc: int, cases: list[dict], prov, show_it: bool) -> list[tuple[dict, object, object]]:
    """(case, RunResult, Result) の並び。場面ごとにホストの組み方 (サーバ・利用者・確認・Skill) が違う。"""
    out = []
    if uc == 1:
        async with Host(["kb"], user=KB_USER, provider=prov, system=KB_SYSTEM) as h:
            for c in cases:
                r = await _run(h, uc, c, show_it)
                out.append((c, r, judge_kb(c, r)))
    elif uc == 2:
        approver = SlipApprover()          # 確認の画面を、依頼の伝票と見比べて決める人の代わり
        async with Host(["expense", "inventory"], user=REG_USER, provider=prov, system=REG_SYSTEM, approver=approver) as h:
            for c in cases:
                approver.case = c
                before = {f: len(state_rows(f)) for f in ("expenses.jsonl", "orders.jsonl")}
                r = await _run(h, uc, c, show_it)
                out.append((c, r, judge_reg(c, r, before)))
    elif uc == 3:
        for c in cases:                    # 利用者はホストが決める。人ごとにホストを立て直す
            n0 = len(state_rows("audit.jsonl"))
            async with Host(["crm"], user=c["user"], provider=prov, system=CRM_SYSTEM, tag_user=True) as h:
                r = await _run(h, uc, c, show_it)
            out.append((c, r, judge_crm(c, r, state_rows("audit.jsonl")[n0:])))
    elif uc in (4, 5):
        sk = load_skill("solaha-monthly-report" if uc == 4 else "solaha-contract-review")
        server, user, base = ("report", REPORT_USER, REPORT_SYSTEM) if uc == 4 else ("contract", CONTRACT_USER, CONTRACT_SYSTEM)
        async with SkillHost([server, "skill"], user=user, provider=prov, system=skill_system(sk, base),
                             allowed_tools=sk["allowed"]) as h:
            for c in cases:
                r = await _run(h, uc, c, show_it)
                out.append((c, r, (judge_report if uc == 4 else judge_contract)(c, r)))
    return out


async def amain(argv=None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider")
    ap.add_argument("--uc", default="all", help="1〜5 をカンマ区切り、または all")
    ap.add_argument("--only", help="場面の中の件の ID をカンマ区切り (例 K-1,EX-2,U-01/C-001,2026-09,LC-03)")
    ap.add_argument("--all", action="store_true", help="選んだ場面の全件")
    ap.add_argument("--plan", default="right", choices=["right", "sloppy"], help="mock の筋書き")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--today", help="講座の「今日」を変える YYYY-MM-DD (既定 2026-10-24。伝票の日付とサーバの申請日が一緒に変わる)")
    ap.add_argument("--name", default="")
    a = ap.parse_args(argv)
    ucs = [1, 2, 3, 4, 5] if a.uc == "all" else [int(x) for x in a.uc.split(",")]
    only = set(a.only.split(",")) if a.only else None
    pname = L.provider_name(a.provider)

    # 登録・監査ログの置き場所を、この実行専用の空のフォルダにする (終わったら元に戻す)
    st = os.path.join(out_dir(LAB), f"state_{a.name or 'last'}")
    shutil.rmtree(st, ignore_errors=True)
    old = os.environ.get("SOLAHA_STATE_DIR")
    os.environ["SOLAHA_STATE_DIR"] = st
    old_today = os.environ.get("SOLAHA_TODAY")
    if a.today:
        os.environ["SOLAHA_TODAY"] = a.today          # 伝票の日付とサーバの申請日を一緒に動かす
    print(f"■ 業務の場面 / provider={pname}" + (f" (筋書き {a.plan}・数字は証拠にならない)" if pname == "mock" else "")
          + f" / 登録と監査ログ: {os.path.relpath(state_dir(), out_dir(LAB))}/")
    rows, per_uc = [], {}
    try:
        for uc in ucs:
            cases = [c for c in all_cases(uc, dt.date.fromisoformat(a.today) if a.today else None) if (c["id"] in only if only else (a.all or c["id"] in DEFAULT_CASES[uc]))]
            if not cases:
                continue
            prov = L.get_provider(a.provider, mock_plan=make_plan(uc, cases, a.plan))
            print(f"── UC{uc} {UC_TITLE[uc]} ({len(cases)} 件)")
            t0, since = time.time(), time.strftime("%Y-%m-%dT%H:%M:%S")
            done = await run_uc(uc, cases, prov, a.show)
            for c, r, res in done:
                print(res.summary())
                rows.append({"uc": uc, "id": c["id"], "ok": res.ok, "checks": res.checks, "review": res.review,
                             "notes": res.notes, "called": res.called, "text": r.text, "stop": r.stop})
            led = L.ledger_summary(since=since, tag_prefix=f"{LAB}/uc{uc}/")
            per_uc[uc] = {"n": len(done), "passed": sum(res.ok for _, _, res in done),
                          "failed": [c["id"] for c, _, res in done if not res.ok],
                          "review": [c["id"] for c, _, res in done if res.review],
                          "seconds": round(time.time() - t0, 1), "cost_usd": led["cost_usd"]}
    finally:
        for k, v in (("SOLAHA_STATE_DIR", old), ("SOLAHA_TODAY", old_today)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    n, ok = sum(v["n"] for v in per_uc.values()), sum(v["passed"] for v in per_uc.values())
    print(f"→ 合格 {ok}/{n}" + "".join(f"・UC{u} {v['passed']}/{v['n']}" for u, v in per_uc.items())
          + f"・不合格 {[i for v in per_uc.values() for i in v['failed']] or 'なし'}")
    summ = {"provider": pname, "plan": a.plan if pname == "mock" else None, "model": L.DEFAULT_MODEL if pname != "mock" else "mock", "n": n, "passed": ok,
            "per_uc": per_uc, "cost_usd": round(sum(v["cost_usd"] for v in per_uc.values()), 4)}
    if a.name:
        d = out_dir(LAB)
        write_jsonl(os.path.join(d, f"runs_{a.name}.jsonl"), rows)
        write_json(os.path.join(d, f"summary_{a.name}.json"), summ)
    return {"summary": summ, "rows": rows, "state_dir": st}


def main(argv=None) -> dict:
    return anyio.run(amain, argv)


if __name__ == "__main__":
    from common.kit import utf8_console
    utf8_console()
    main()
