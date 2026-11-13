"""ラボ 10 (後半): Claude API そのものに Skill と MCP を渡す形。

    python run_api.py --dry                       # 送る request の形を見るだけ (費用 0・キー不要)
    python run_api.py --run --month 2026-09 --name opus   # Skill を API に上げて月次レポートを作らせる (要 API キー)

Claude API の 2 つの部品:
  - Skills (GA): client.skills.create で Skill のフォルダを上げ、container={"skills": [...]} で渡す。
                 Skill は Anthropic 側のコード実行の箱 (container) の中で動く → コード実行の道具が要る
  - MCP コネクタ (beta mcp-client-2025-11-20): mcp_servers に **インターネットから届く HTTPS の URL** を書くと、
                 Anthropic 側が MCP サーバにつなぐ。道具 (tools) だけ。手元の stdio のサーバや社内だけの URL には届かない
→ 手元のサーバの数字は、自分のホスト (MCP の Client) で取ってから渡す。ラボではこの形で月次レポートを作る。

🔴 --run はモデルを呼ぶ (Skill のアップロードも行う)。キーが無ければ呼ばずに止まる。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import anyio

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
from common import llm as L  # noqa: E402
from common.kit import out_dir, write_json  # noqa: E402

LAB = "lab10_mcp_x_skills"
SKILL_DIR = os.path.join(ROOT, "skills", "solaha-monthly-report")
CODE_EXEC = {"type": "code_execution_20260521", "name": "code_execution"}
CODE_EXEC_BETA = "code-execution-2025-08-25"
MCP_BETA = "mcp-client-2025-11-20"


async def month_data(month: str) -> dict:
    """手元の report サーバから、Skill の手順 2 と同じ 3 つの返事を取る (自分のホストの役)。"""
    from mcp import Client
    from servers import report
    async with Client(report.mcp) as c:
        return {"sales.json": (await c.call_tool("get_monthly_sales", {"month": month})).structured_content,
                "inquiries.json": (await c.call_tool("get_inquiry_counts", {"month": month})).structured_content,
                "inventory.json": (await c.call_tool("get_inventory_snapshot", {"month": month})).structured_content}


def skills_request(skill_id: str, month: str, data: dict) -> dict:
    files = "\n\n".join(f"### {n}\n```json\n{json.dumps(v, ensure_ascii=False)}\n```" for n, v in data.items())
    return {
        **L.base_request(),
        "betas": [CODE_EXEC_BETA],
        "container": {"skills": [{"type": "custom", "skill_id": skill_id, "version": "latest"}]},
        "tools": [CODE_EXEC],
        "messages": [{"role": "user", "content":
                      f"{month} の月次レポートを社内の型で作ってください。report サーバの返事は下の 3 つです "
                      f"(手順 2 の代わりに、このままファイルに保存して使ってください)。"
                      f"できたレポートの本文 (report.md の中身) を、最後にそのまま返してください。\n\n{files}"}],
    }


def connector_request() -> dict:
    """MCP コネクタの request の形 (見せるだけ。URL は架空・届かない)。"""
    return {
        **L.base_request(), "max_tokens": 2048,
        "betas": [MCP_BETA],
        "mcp_servers": [{"type": "url", "url": "https://mcp.solaha.example/report/mcp", "name": "report",
                         "authorization_token": "<社内の認可サーバで取ったアクセストークン>"}],
        "tools": [{"type": "mcp_toolset", "mcp_server_name": "report",
                   "default_config": {"enabled": False},
                   "configs": {"get_monthly_sales": {"enabled": True}}}],     # 読むだけの道具だけを許す
        "messages": [{"role": "user", "content": "2026-09 の売上の合計は？"}],
    }


def _short(req: dict) -> str:
    r = json.loads(json.dumps(req, ensure_ascii=False))
    for m in r.get("messages", []):
        if isinstance(m["content"], str) and len(m["content"]) > 160:
            m["content"] = m["content"][:160] + f"…（全 {len(m['content'])} 文字）"
    return json.dumps(r, ensure_ascii=False, indent=1)


async def run(month: str, model: str) -> dict:
    from anthropic import Anthropic
    from anthropic.lib import files_from_dir
    from run_agent import expected_report, score_report
    key = L._api_key()
    if not key:
        raise SystemExit("API キーが見つからないので、モデルを呼びません (--dry を使ってください)")
    client = Anthropic(api_key=key)
    del key
    t0 = time.time()
    skill = client.skills.create(files=files_from_dir(SKILL_DIR), display_name="solaha-monthly-report")
    req = skills_request(skill.id, month, await month_data(month))
    req["model"] = model
    with L.tag(f"{LAB}/api-skills"):
        with client.beta.messages.stream(**req) as s:
            msg = s.get_final_message()
    resp = msg.model_dump(mode="json", exclude_none=True)
    u = resp.get("usage", {})
    cost = L.cost_of(model, u)
    L._record({"provider": "anthropic", "model": model, "cached": False, "in": u.get("input_tokens", 0),
               "out": u.get("output_tokens", 0), "cost_usd": round(cost, 6), "seconds": round(time.time() - t0, 1)})
    text = "".join(b.get("text", "") for b in resp["content"] if b.get("type") == "text")
    kinds = [b.get("type") for b in resp["content"]]
    return {"model": model, "month": month, "skill_id": skill.id, "block_types": kinds, "text": text,
            "usage": u, "cost_usd": round(cost, 4), "seconds": round(time.time() - t0, 1),
            "score": score_report(text, await expected_report(month))}


async def amain(argv=None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--month", default="2026-09")
    ap.add_argument("--model", default=L.DEFAULT_MODEL)
    ap.add_argument("--name", default="")
    a = ap.parse_args(argv)
    if a.run:
        o = await run(a.month, a.model)
        s = o["score"]
        print(f"■ Skills API / model={o['model']} / ブロック {o['block_types']} / {o['seconds']} 秒 / {o['cost_usd']} USD")
        print(f"■ 答え合わせ: 数字の行 {s['matched']}/{s['numeric_lines']} がスクリプトの出力と一致")
        if a.name:
            write_json(os.path.join(out_dir(LAB), f"api_{a.name}.json"), o)
        return o
    data = await month_data(a.month)
    sk, cn = skills_request("skill_xxxxxxxx (アップロードで決まる)", a.month, data), connector_request()
    print("■ 1. Skills (GA) ― Skill はコード実行の箱の中で動く")
    print(_short(sk))
    print("\n■ 2. MCP コネクタ (beta) ― Anthropic 側から、インターネットに出ている HTTPS の MCP サーバにつなぐ")
    print(_short(cn))
    return {"skills_request": sk, "connector_request": cn}


def main(argv=None) -> dict:
    return anyio.run(amain, argv)


if __name__ == "__main__":
    from common.kit import utf8_console
    utf8_console()
    main()
