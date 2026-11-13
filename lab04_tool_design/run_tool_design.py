"""ラボ 4: 道具の設計 ― モデルが「最初に呼ぶ道具」を正しく選べるかを測る。

    python run_tool_design.py --only TS-01,TS-39 --show              # 2 問だけ、1 問ずつ表示 (デモ用)
    python run_tool_design.py --all --name good                      # 40 問を元の説明で、結果を out/ に残す
    python run_tool_design.py --all --variant all --name compare     # 4 通り (元・あいまい・番号の名前・分野だけ) を比べる
    python run_tool_design.py --all --variant vague --show           # あいまいな説明で、外した問いだけを表示
    python run_tool_design.py --describe                             # 道具の欄の大きさ (字数・トークンの目安) と見本

1 問につき依頼を 1 回だけ送り、応答の最初の tool_use を読む (道具は実行しない)。
--provider mock / replay / anthropic (既定は環境変数 LLM_PROVIDER、無ければ mock)。
🔴 mock はキーワード照合の筋書き。数字は Claude の性能の証拠にならない。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import anyio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import llm as L  # noqa: E402
from common.host import Host  # noqa: E402
from common.kit import out_dir, write_json, write_jsonl  # noqa: E402
from tool_variants import (VARIANT_JA, VARIANTS, KeywordRouter, block_size, first_tool_use,  # noqa: E402
                           load_questions, make_tools, score_row, short, summarize)

LAB = "lab04_tool_design"
SYSTEM = ("あなたはソラハ電機 (架空) の社内アシスタントです。社員の質問に答えます。"
          "道具が必要なら道具を使い、道具が要らない質問には道具を使わずに答えてください。")
DEFAULT_ONLY = ["TS-01", "TS-09", "TS-15", "TS-39"]


def _size_line(sizes: list[dict]) -> str:
    if len(sizes) == 1 or len({s["chars"] for s in sizes}) == 1:
        s = sizes[0]
        return f"道具の欄 {s['tools']} 個 {s['chars']:,} 字 ≈ {s['tokens_est']:,} トークン(目安)"
    ch = [s["chars"] for s in sizes]
    tk = [s["tokens_est"] for s in sizes]
    return (f"道具の欄 1 問あたり {min(s['tools'] for s in sizes)}〜{max(s['tools'] for s in sizes)} 個 "
            f"平均 {sum(ch) // len(ch):,} 字 ≈ {sum(tk) // len(tk):,} トークン(目安)")


def _conf_line(conf: dict) -> str:
    """取り違えだけを短く (期待のサーバ→選んだサーバ ×件数)。"""
    bad = [f"{e}→{p} ×{n}" for e, row in conf.items() for p, n in row.items() if p != e]
    return "、".join(bad) if bad else "なし"


async def describe() -> dict:
    qs = load_questions()
    async with Host(user="U-01", provider=L.MockProvider()) as h:
        base = h.tools
    out = {}
    print("■ 道具の欄の大きさ (トークンは目安。本物は usage.input_tokens で測る)")
    for v in VARIANTS:
        sizes = [block_size(make_tools(v, base, q)[0]) for q in (qs if v == "subset" else qs[:1])]
        out[v] = sizes[0] if v != "subset" else {"min_chars": min(s["chars"] for s in sizes),
                                                 "max_chars": max(s["chars"] for s in sizes)}
        print(f"  {v:<6} ({VARIANT_JA[v]}) {_size_line(sizes)}")
    q = qs[12]      # TS-13 (在庫) を見本に
    print(f"■ 同じ道具の見え方 (get_stock)")
    for v in ("good", "vague", "names"):
        t = next(t for t in make_tools(v, base, q)[0] if short(make_tools(v, base, q)[1][t["name"]]) == "get_stock")
        d = t["description"].replace("\n", " ")
        print(f"  {v:<6} name={t['name']}  description={d[:70]}{'…' if len(d) > 70 else ''}")
    return out


async def amain(argv=None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider")
    ap.add_argument("--variant", default="good", help="good / vague / names / subset をカンマ区切り、または all")
    ap.add_argument("--only", help="問いの ID をカンマ区切り (例 TS-01,TS-39)")
    ap.add_argument("--all", action="store_true", help="40 問すべて")
    ap.add_argument("--describe", action="store_true", help="道具の欄の大きさと見本を表示するだけ")
    ap.add_argument("--show", action="store_true", help="1 問ずつ表示 (--all のときは外した問いだけ)")
    ap.add_argument("--name", default="")
    a = ap.parse_args(argv)
    if a.describe:
        return await describe()

    variants = list(VARIANTS) if a.variant == "all" else a.variant.split(",")
    for v in variants:
        if v not in VARIANTS:
            raise SystemExit(f"--variant が不明です: {v} ({' / '.join(VARIANTS)} / all)")
    qs = load_questions()
    want = a.only.split(",") if a.only else ([q["id"] for q in qs] if a.all else DEFAULT_ONLY)
    qs = [q for q in qs if q["id"] in want]
    router = KeywordRouter()
    prov = L.get_provider(a.provider, mock_plan=router)
    if isinstance(prov, L.MockProvider):
        router.attach(prov)                   # 筋書きが「渡された道具の説明」を読めるようにする
    pname = L.provider_name(a.provider)
    print(f"■ 道具の選び方 / provider={pname}" + (" (キーワード照合の筋書き・数字は証拠にならない)" if pname == "mock" else "")
          + f" / {len(qs)} 問 × {len(variants)} 通り")
    summaries, all_rows = {}, []
    async with Host(user="U-01", provider=prov, system=SYSTEM) as h:
        base = list(h.tools)
        for v in variants:
            rows, sizes, usage_in, t0 = [], [], 0, time.time()
            since = time.strftime("%Y-%m-%dT%H:%M:%S")
            for q in qs:
                tools, back = make_tools(v, base, q)
                h.tools = tools                                  # Host.request が道具の欄に入れる
                req = h.request([{"role": "user", "content": [{"type": "text", "text": q["question"]}]}])
                with L.tag(f"{LAB}/{v}/{q['id']}"):
                    resp = prov.create(json.loads(json.dumps(req)))
                picked, text = first_tool_use(resp)
                row = {**score_row(q, picked, back), "variant": v, "text": text if picked is None else "",
                       "usage_in": int(resp.get("usage", {}).get("input_tokens", 0) or 0)}
                rows.append(row)
                sizes.append(block_size(tools))
                usage_in += row["usage_in"]
                if a.show and (a.only or not row["ok"]):
                    mark = "✓" if row["ok"] else ("△" if row["ok_also"] else "✗")     # △ = 期待とは違うが別解
                    got = row["pred"] or "道具なし"
                    exp = q["first_tool"] or "道具なし"
                    print(f"  {mark} {q['id']} {q['question'][:24]:<24} 期待 {exp} → {got}"
                          + (f" (名乗った名前 {picked})" if v == "names" and picked else ""))
            h.tools = base
            s = summarize(rows)
            led = L.ledger_summary(since=since, tag_prefix=f"{LAB}/{v}/")
            s.update(variant=v, block=sizes[0] if len({x["chars"] for x in sizes}) == 1 else
                     {"tools_min": min(x["tools"] for x in sizes), "tools_max": max(x["tools"] for x in sizes),
                      "chars_avg": sum(x["chars"] for x in sizes) // len(sizes),
                      "tokens_est_avg": sum(x["tokens_est"] for x in sizes) // len(sizes)},
                     usage_in_total=usage_in, seconds=round(time.time() - t0, 1), cost_usd=led["cost_usd"])
            summaries[v] = s
            all_rows += rows
            also = f" (別解も正解なら {s['first_ok_also']}/{s['n']})" if s["first_ok_also"] != s["first_ok"] else ""
            print(f"  {v:<6} 最初の道具 {s['first_ok']}/{s['n']}{also}"
                  f"  道具なし {s['no_tool']} (正しく {s['no_tool_correct']}・取りこぼし {s['no_tool_missed']})"
                  + (f"  要らないのに使った {s['tool_when_none']}" if s["tool_when_none"] else "")
                  + f"  {_size_line(sizes)}")
            if len(qs) > len(DEFAULT_ONLY):
                print(f"         取り違え: {_conf_line(s['confusion'])}")
    summ = {"provider": pname, "model": L.DEFAULT_MODEL if pname != "mock" else "mock(キーワード照合)",
            "n_questions": len(qs), "variants": summaries,
            "note": "mock の数字は性能の証拠にならない" if pname == "mock" else ""}
    if a.name:
        d = out_dir(LAB)
        write_jsonl(os.path.join(d, f"runs_{a.name}.jsonl"), all_rows)
        write_json(os.path.join(d, f"summary_{a.name}.json"), summ)
    return {"summary": summ, "rows": all_rows}


def main(argv=None) -> dict:
    return anyio.run(amain, argv)


if __name__ == "__main__":
    from common.kit import utf8_console
    utf8_console()
    main()
