"""ラボ 3: 最初のサーバを公式 SDK (mcp 2.3.0 の MCPServer) で書き、Client でつないで確かめる。Claude は呼ばない。

    python run_first_server.py --step 1              # ステップ 1: 型ヒントと docstring から道具の形ができる
    python run_first_server.py --step 2              # ステップ 2: 構造化出力・注釈・ToolError・資料・定型文
    python run_first_server.py --step 2 --json       # 生成された tools/list をそのまま JSON で出す
    python run_first_server.py --errors              # ToolError と想定外の例外で、クライアントに届くものの違い
    python run_first_server.py --step 2 --stdio      # 同じサーバを子プロセス (stdio) で立ててつなぐ
    --show で結果を長めに出す

つなぎ方は Client 1 つ: Client(サーバ) = 同じプロセス (試験向け)、Client(StdioServerParameters(...)) = 子プロセス。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from contextlib import contextmanager

import anyio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp import Client, StdioServerParameters  # noqa: E402

import naive_server  # noqa: E402
import step1_server  # noqa: E402
import step2_server  # noqa: E402

LAB = "lab03_first_server"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STEPS = {1: step1_server, 2: step2_server}


def cut(s: str, n: int) -> str:
    s = s.replace("\n", "⏎")
    return s if len(s) <= n else s[:n] + f"…(全{len(s)}字)"


def tool_json(t) -> dict:
    """tools/list の 1 件を、電文と同じ形 (camelCase・空の項目なし) にする。"""
    return t.model_dump(mode="json", by_alias=True, exclude_none=True)


def show_tools(tools, show: bool) -> None:
    for t in tools:
        print(f"  道具 {t.name}" + (f" ({t.title})" if t.title else ""))
        print(f"    description: {cut(t.description or '', 300 if show else 130)}")
        props = t.input_schema.get("properties", {})
        if "Args:" in (t.description or "") and not any("description" in p for p in props.values()):
            print("    🔴 docstring の Args: は description に入っただけ。引数ごとの説明は空のまま")
        for k, p in props.items():
            extra = {x: p[x] for x in ("default", "minimum", "maximum") if x in p}
            print(f"    引数 {k}: {p.get('type')}" + (f"  {extra}" if extra else "")
                  + ("  必須" if k in t.input_schema.get("required", []) else "")
                  + (f"  説明「{p['description']}」" if "description" in p else "  (説明なし)"))
        out = t.output_schema or {}
        print(f"    outputSchema: {list(out.get('properties', {}))}" + (f"  $defs={list(out['$defs'])}" if "$defs" in out else ""))
        if t.annotations:
            print(f"    annotations: {t.annotations.model_dump(exclude_none=True)}")


# ---------------------------------------------------------------- ステップごと
async def run_step1(c: Client, show: bool) -> dict:
    r = await c.call_tool("search_regulations", {"keyword": "出張"})
    print(f"■ call_tool search_regulations(keyword='出張') → is_error={r.is_error}")
    for ln in r.content[0].text.splitlines():
        print("  " + cut(ln, 200 if show else 80))
    print(f"  structured_content: {cut(json.dumps(r.structured_content, ensure_ascii=False), 200 if show else 70)}")
    print("→ str を返すと、文字の塊が {\"result\": \"…\"} に包まれるだけ。モデルは文字を読み解くしかない")
    return {"is_error": r.is_error, "text": r.content[0].text, "structured": r.structured_content}


async def run_step2(c: Client, show: bool) -> dict:
    out = {}
    r = await c.call_tool("search_regulations", {"keyword": "出張", "limit": 2})
    print(f"■ call_tool search_regulations(keyword='出張', limit=2) → is_error={r.is_error}")
    for h in r.structured_content["result"]:
        print(f"  structured: {h['doc_id']} {h['title']} ({h['matched']} 行)  {cut(h['first_line'], 200 if show else 40)}")
    print(f"  content: TextContent {len(r.content)} 個 (同じ中身の JSON 文字。古いクライアント向け)")
    out["search"] = r.structured_content["result"]
    r = await c.call_tool("get_regulation", {"doc_id": "a-06"})
    print(f"■ get_regulation(a-06) → {r.structured_content['title']} / {r.structured_content['chars']} 字")
    r = await c.call_tool("get_regulation", {"doc_id": "a-99"})
    print(f"■ get_regulation(a-99) → is_error={r.is_error}  「{r.content[0].text}」")
    out["not_found"] = {"is_error": r.is_error, "text": r.content[0].text}
    tpl = (await c.list_resource_templates()).resource_templates
    print(f"■ 資料のひな形: {[t.uri_template for t in tpl]}")
    rr = await c.read_resource("regs://a-01")
    print(f"  read_resource(regs://a-01) → {rr.contents[0].mime_type}  {cut(rr.contents[0].text, 200 if show else 30)}")
    ps = (await c.list_prompts()).prompts
    p = await c.get_prompt("answer_with_citation", {"question": "海外出張は何日前に申請しますか"})
    print(f"■ 定型文: {[x.name for x in ps]} → {cut(p.messages[0].content.text, 300 if show else 60)}")
    out["resource_templates"] = [t.uri_template for t in tpl]
    out["prompt_text"] = p.messages[0].content.text
    return out


# ---------------------------------------------------------------- 失敗の比べ
class _Grab(logging.Handler):
    def __init__(self):
        super().__init__()
        self.rows = []

    def emit(self, rec):
        self.rows.append((rec.getMessage(), bool(rec.exc_info)))


@contextmanager
def server_logs():
    """同じプロセスのサーバのログ (道具の失敗・traceback) を画面に出さずに集める。"""
    lg = logging.getLogger("mcp.server.mcpserver")
    grab, saved = _Grab(), (lg.handlers[:], lg.propagate)
    lg.handlers, lg.propagate = [grab], False
    try:
        yield grab
    finally:
        lg.handlers, lg.propagate = saved


async def run_errors(show: bool) -> dict:
    """同じ「無い番号」でも、書き方でクライアントに届くものが変わる。サーバのログは画面に出さず数えるだけ。"""
    cases = [
        ("ToolError で断る (step2)", step2_server.mcp, "get_regulation", {"doc_id": "a-99"}),
        ("想定外の例外 KeyError (naive)", naive_server.mcp, "get_regulation", {"doc_id": "a-99"}),
        ("引数の範囲外 limit=50 (step2)", step2_server.mcp, "search_regulations", {"keyword": "出張", "limit": 50}),
        ("無い道具の名前 (step2)", step2_server.mcp, "delete_regulation", {"doc_id": "a-01"}),
    ]
    rows = []
    with server_logs() as grab:
        print("■ 失敗したとき、クライアント (= モデル) に届くもの")
        for label, srv, tool, args in cases:
            n0 = len(grab.rows)
            async with Client(srv) as c:
                r = await c.call_tool(tool, args)
            text = r.content[0].text if r.content else ""
            logs = grab.rows[n0:]
            print(f"[{label}] is_error={r.is_error}")
            print(f"  届いた文: 「{cut(text, 400 if show else 90)}」")
            print("  サーバのログ: " + (" / ".join(f"{m[:60]}" + (" +traceback" if tb else "") for m, tb in logs) or "なし"))
            rows.append({"case": label, "is_error": r.is_error, "text": text, "traceback_logged": any(tb for _, tb in logs)})
    print("→ ToolError の文は頭に「Error executing tool <名前>: 」が付いて届く (直し方を書ける)。"
          "想定外の例外は中身を隠して「Error executing tool <名前>」だけ (traceback はサーバのログにだけ)。"
          "どれも例外ではなく is_error=True の結果として返る")
    return {"errors": rows}


# ---------------------------------------------------------------- stdio
def stdio_target(step: int, log):
    """子プロセスで立てる。Jupyter の標準エラーには fileno が無いので、そのときはログをファイルへ回す。"""
    params = StdioServerParameters(command=sys.executable, args=[os.path.join(HERE, f"step{step}_server.py")],
                                   cwd=ROOT, env={**os.environ, "PYTHONUTF8": "1"})
    try:
        sys.stderr.fileno()
        return params                                          # ターミナル: Client(StdioServerParameters(...)) そのまま
    except Exception:
        from mcp.client.stdio import stdio_client
        return stdio_client(params, errlog=log)


async def run_stdio(step: int, show: bool) -> dict:
    print(f"■ step{step}_server.py を子プロセスで起動して stdio でつなぐ (Claude Desktop・Claude Code と同じつなぎ方)")
    log_path = os.path.join(tempfile.gettempdir(), f"lab03_step{step}_stdio.log")
    with open(log_path, "a", encoding="utf-8") as log:
        async with Client(stdio_target(step, log)) as c:
            names = [t.name for t in (await c.list_tools()).tools]
            r = await c.call_tool("search_regulations", {"keyword": "在宅勤務"})
            first = (r.structured_content["result"][0]["doc_id"] if step == 2
                     else r.content[0].text.split()[0])
            print(f"  protocol={c.protocol_version} server={c.server_info.name} 道具={names}")
            print(f"  search_regulations(在宅勤務) → 先頭 {first} / is_error={r.is_error}")
            proto = c.protocol_version
    print("→ サーバのコードは同じ。変わるのはつなぎ方 (Client に渡すもの) だけ")
    return {"protocol": proto, "tools": names, "first": first}


async def amain(argv=None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, default=1, choices=[1, 2])
    ap.add_argument("--json", action="store_true", help="生成された tools/list をそのまま出す")
    ap.add_argument("--errors", action="store_true", help="ToolError と想定外の例外の違い")
    ap.add_argument("--stdio", action="store_true", help="子プロセス (stdio) でつなぐ")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args(argv)
    if a.errors:
        return await run_errors(a.show)
    if a.stdio:
        return await run_stdio(a.step, a.show)
    srv = STEPS[a.step].mcp
    async with Client(srv) as c:
        tools = (await c.list_tools()).tools
        if a.json:
            js = [tool_json(t) for t in tools]
            print(json.dumps({"tools": js}, ensure_ascii=False, indent=1))
            return {"tools": js}
        print(f"■ step{a.step}_server.py を同じプロセスで Client(mcp) につなぐ / protocol={c.protocol_version}")
        print("■ tools/list (SDK が関数から作った形)")
        show_tools(tools, a.show)
        with server_logs():                     # a-99 の失敗のログを画面に混ぜない (--errors で見る)
            res = await (run_step1 if a.step == 1 else run_step2)(c, a.show)
    res["tools"] = [tool_json(t) for t in tools]
    return res


def main(argv=None) -> dict:
    return anyio.run(amain, argv)


if __name__ == "__main__":
    from common.kit import utf8_console
    utf8_console()
    main()
