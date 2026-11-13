"""ラボ 10: Claude Agent SDK で、キットの MCP サーバと Skill を組み合わせて業務を通す。

    python run_agent.py --probe                         # つないで中身を見るだけ (モデルを呼ばない・費用 0)
    python run_agent.py --task report --month 2026-09 --run --name opus     # 月次レポート (要 API キー)
    python run_agent.py --task report --month 2026-09 --run --model claude-sonnet-5-5 --name sonnet
    python run_agent.py --task order --run --name order # 書き込みの道具は can_use_tool が止める (要 API キー)
    python run_agent.py --show-saved opus               # 講師の実行記録 (out/agent_opus.jsonl) を表示する (費用 0)

🔴 --run はモデルを呼ぶ。キー (ANTHROPIC_API_KEY) が見つからなければ呼ばずに止まる
   (キーが無いと CLI が別のログイン情報で動くことがあるので、ここでは必ずキーを明示して渡す)。
🔴 Agent SDK の呼び出しは記録の再生 (replay) が効かない。講師の実行は out/ に保存し、ノートブックはそれを表示する。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import time

import anyio

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from common import llm as L  # noqa: E402
from common.kit import out_dir, read_json, data_path, write_json, write_jsonl  # noqa: E402
from agent_setup import SKILLS, WORKSPACE, options  # noqa: E402

LAB = "lab10_mcp_x_skills"
TASKS = {
    "report": "{month} の月次レポートを社内の型で作ってください。数字は report サーバから取ってください。",
    "order": "在庫が発注点を下回っている品目を調べて、足りない分を発注してください。",
}


# ---------------------------------------------------------------- つないで見るだけ (費用 0)
async def probe() -> dict:
    from claude_agent_sdk import ClaudeSDKClient
    env_key = os.environ.pop("ANTHROPIC_API_KEY", None)     # 見るだけなのでキーは渡さない
    try:
        async with ClaudeSDKClient(options("U-02")) as c:
            info = await c.get_server_info() or {}
            for _ in range(40):                                # サーバの起動を待つ (pending → connected)
                st = await c.get_mcp_status()
                if all(s["status"] != "pending" for s in st["mcpServers"]):
                    break
                await anyio.sleep(0.5)
            usage = await c.get_context_usage()
    finally:
        if env_key:
            os.environ["ANTHROPIC_API_KEY"] = env_key
    print(f"■ Claude Code (Agent SDK 同梱) {info.get('claude_code_version')} / 作業フォルダ lab10_mcp_x_skills/workspace")
    print("■ MCP サーバ")
    servers = []
    for s in st["mcpServers"]:
        tools = [(t["name"], "読むだけ" if (t.get("annotations") or {}).get("readOnly") else "書き込みあり")
                 for t in s.get("tools", [])]
        servers.append({"name": s["name"], "status": s["status"], "tools": tools})
        print(f"  {s['name']:<9} {s['status']:<10} " + ", ".join(f"{n} ({k})" for n, k in tools))
    sk = usage.get("skills") or {}
    print(f"■ Skill: 読み込んだ {sk.get('includedSkills')} 本 / 常に文脈に載るのは名前と説明だけ = {sk.get('tokens')} トークン")
    for f in sk.get("skillFrontmatter", []):
        print(f"  {f['name']:<24} {f['tokens']:>4} トークン")
    cats = {c["name"]: (c["tokens"], c.get("isDeferred", False)) for c in usage.get("categories", [])}
    mcp_def = cats.get("MCP tools (deferred)", (0, True))[0]
    print(f"■ MCP の道具: {len(usage.get('mcpTools', []))} 個・{mcp_def} トークン分は「必要になってから読む」(deferred)")
    for t in sorted(usage.get("mcpTools", []), key=lambda t: -t["tokens"])[:4]:
        print(f"  {t['name']:<40} {t['tokens']:>4} トークン")
    return {"version": info.get("claude_code_version"), "servers": servers,
            "skills": [{"name": f["name"], "tokens": f["tokens"]} for f in sk.get("skillFrontmatter", [])],
            "skill_tokens": sk.get("tokens"), "mcp_tools": len(usage.get("mcpTools", [])), "mcp_deferred_tokens": mcp_def}


# ---------------------------------------------------------------- 月次レポートの答え合わせ
async def expected_report(month: str) -> str:
    """同じ月の数字を report サーバから取り、Skill のスクリプトで作った「正しい 1〜3 節」を返す。"""
    import importlib.util
    from mcp import Client
    from servers import report
    spec = importlib.util.spec_from_file_location(
        "build_report", os.path.join(os.path.dirname(HERE), "skills", "solaha-monthly-report", "scripts", "build_report.py"))
    br = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(br)
    async with Client(report.mcp) as c:
        s = (await c.call_tool("get_monthly_sales", {"month": month})).structured_content
        q = (await c.call_tool("get_inquiry_counts", {"month": month})).structured_content
        inv = (await c.call_tool("get_inventory_snapshot", {"month": month})).structured_content
    md, _ = br.build(s, q, inv)
    return md


def score_report(produced: str, expected: str) -> dict:
    """数字を含む行が、スクリプトの出力と一字一句同じかを見る (手で書き写した・丸めた数字を拾う)。"""
    lines = [ln.strip() for ln in expected.splitlines() if re.search(r"\d", ln) and ln.strip()]
    missing = [ln for ln in lines if ln not in produced]
    return {"numeric_lines": len(lines), "matched": len(lines) - len(missing), "missing": missing[:5]}


# ---------------------------------------------------------------- シェルの許可 (人の承認の代わり)
# Windows の Claude Code はシェルに PowerShell を使う (SKILL.md の allowed-tools「Bash(python:*)」は当たらない)
SHELL_TOOLS = ("Bash", "PowerShell")
_FORBIDDEN = ("&", "`", "$(", "<", "\n", "\r", "{", "@(")          # 命令の合成・置き換えは一切通さない
_ENCODING_SET = re.compile(r"^\$env:PYTHONIOENCODING\s*=\s*['\"]?utf-?8['\"]?$", re.I)


def _inside(path: str, root: str) -> bool:
    p, r = os.path.normcase(os.path.normpath(path)), os.path.normcase(os.path.normpath(root))
    return p == r or p.startswith(r + os.sep)


def check_shell(cmd: str, workspace: str = WORKSPACE) -> tuple[bool, str]:
    """シェルのコマンドを ; と | で区切って一つずつ読み、パスを実際に解決して確かめる。
    通すのは: Skill のスクリプトを動かす・作業フォルダの中の .md に書き出す / 読む・作業フォルダの中で cd する、だけ。
    文字列の形 (正規表現) ではなく「解決したパスがどこを指すか」で判定するので、.. や絶対パスで外に出るものは通らない。"""
    if any(f in cmd for f in _FORBIDDEN):
        return False, "命令をつなぐ・置き換える記号がある"
    scripts_roots = [os.path.join(workspace, ".claude", "skills", s, "scripts") for s in SKILLS]
    cwd, ran_script = workspace, False

    def res(p: str) -> str:
        return os.path.normpath(os.path.join(cwd, p.strip("'\"")))

    for seg in [s.strip() for s in cmd.split(";") if s.strip()]:
        if _ENCODING_SET.match(seg):
            continue
        parts = [p.strip() for p in seg.split("|")]
        toks = [t.strip("'\"") for t in parts[0].split()]                 # 引用符で囲んだパスも同じに読む
        if toks and toks[0] == "PYTHONIOENCODING=utf-8":
            toks = toks[1:]
        if not toks:
            return False, "空の命令"
        head = toks[0].lower()
        if head in ("cd", "set-location") and len(toks) == 2:
            cwd = res(toks[1])
            if not _inside(cwd, workspace):
                return False, f"作業フォルダの外へ cd: {toks[1]}"
        elif head in ("python", "python3", "py", "python.exe"):
            rest = toks[1:]
            if rest and rest[0] == "-I":
                rest = rest[1:]
            if not rest or not any(_inside(res(rest[0]), r) for r in scripts_roots) or not rest[0].endswith(".py"):
                return False, "Skill のスクリプト以外を python で動かそうとした"
            args = rest[1:]
            while args:
                t = args.pop(0)
                if t in (">", ">>"):
                    if not args:
                        return False, "書き出し先が無い"
                    t = args.pop(0)
                    if not (t.endswith(".md") and _inside(res(t), workspace)):
                        return False, f"作業フォルダの中の .md 以外に書き出す: {t}"
                elif t.startswith(">"):
                    t = t.lstrip(">")
                    if not (t.endswith(".md") and _inside(res(t), workspace)):
                        return False, f"作業フォルダの中の .md 以外に書き出す: {t}"
                elif not (t.endswith((".json", ".md")) and _inside(res(t), workspace)):
                    return False, f"作業フォルダの外・JSON 以外の引数: {t}"
            ran_script = True
        elif head in ("write-output", "echo") and len(parts) == 1:
            pass                                                         # 画面に出すだけ (終了コードの表示など)
        elif head in ("get-content", "cat", "type") and all(
                t.lower() in ("-encoding", "utf8", "utf-8", "-raw") or (t.endswith(".md") and _inside(res(t), workspace))
                for t in toks[1:]):
            pass
        else:
            return False, f"許していない命令: {toks[0]}"
        for p in parts[1:]:                                        # パイプの先は「.md に書き出す」だけ
            pt = [t.strip("'\"") for t in p.split()]
            files = [t for t in pt[1:] if t.lower() not in ("-encoding", "utf8", "utf-8", "-filepath")]
            if not (pt and pt[0].lower() == "out-file" and len(files) == 1 and files[0].endswith(".md")
                    and _inside(res(files[0]), workspace)):
                return False, f"パイプの先が許していない命令: {p[:40]}"
    return (True, "Skill のスクリプトだけ") if ran_script else (False, "Skill のスクリプトを動かしていない")


FILE_TOOLS = ("Edit", "Write", "MultiEdit")


def check_file_edit(path: str, workspace: str = WORKSPACE) -> tuple[bool, str]:
    """ファイルの編集は、作業フォルダの中 (.claude/ = Skill の写しは除く) だけ通す。"""
    p = os.path.normpath(os.path.join(workspace, path))
    if not _inside(p, workspace):
        return False, "作業フォルダの外のファイル"
    if _inside(p, os.path.join(workspace, ".claude")):
        return False, "Skill の中身 (.claude/) は書き換えない"
    return True, "作業フォルダの中のファイル"


def skill_script_command(cmd: str) -> bool:
    return check_shell(cmd)[0]


def read_text_any(path: str) -> str:
    """PowerShell 5.1 の > は UTF-16 で書くので、BOM を見て読み分ける。"""
    raw = open(path, "rb").read()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


# ---------------------------------------------------------------- 本番 (要 API キー)
def clean_workspace() -> None:
    """前の実行が作ったファイル (JSON・レポート) を消す。.claude/ (Skill の写し) は残す。"""
    for n in os.listdir(WORKSPACE):
        if n == ".claude":
            continue
        p = os.path.join(WORKSPACE, n)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)


def find_report(since: float) -> str | None:
    """この実行で作業フォルダに書かれた .md のうち、月次レポートの見出しを含む最新のもの (サブフォルダも見る)。"""
    found = []
    for d, dirs, files in os.walk(WORKSPACE):
        dirs[:] = [x for x in dirs if x != ".claude"]
        for f in files:
            p = os.path.join(d, f)
            if f.endswith(".md") and os.path.getmtime(p) >= since and "月次レポート" in read_text_any(p):
                found.append((os.path.getmtime(p), p))
    return max(found)[1] if found else None


async def run_task(task: str, month: str, model: str, user: str, auth: str = "key") -> dict:
    """auth="key": 環境変数の API キーで呼ぶ (受講者の既定)。
    auth="login": キーを渡さず、同梱の CLI のログイン (Claude のプラン) で呼ぶ。費用は API に換算した目安として出る。"""
    from claude_agent_sdk import AssistantMessage, ClaudeSDKClient, PermissionResultAllow, PermissionResultDeny, \
        ResultMessage, TextBlock, ToolUseBlock
    asked: list[dict] = []

    async def can_use_tool(name, args, ctx):
        # allowed_tools に無い道具 (書き込み・シェルなど) はここに来る。人の承認の代わり。
        # 通すのは「Skill のスクリプトを作業フォルダのファイルで動かすだけ」のコマンドに限り、ほかは理由を添えて断る
        if name in SHELL_TOOLS:
            ok, why = check_shell(args.get("command", ""))
        elif name in FILE_TOOLS:
            ok, why = check_file_edit(args.get("file_path", ""))
        else:
            ok, why = False, "書き込みのある道具"
        asked.append({"tool": name, "input": args, "allowed": ok, "why": why})
        if ok:
            return PermissionResultAllow()
        return PermissionResultDeny(message=f"許可しません ({why})。この作業で通すシェルの命令は、作業フォルダの中で"
                                            " Skill のスクリプトを動かすことだけです。スクリプトの出力をファイルに残すなら、"
                                            "スクリプトの命令に「> report.md」か「| Out-File -Encoding utf8 report.md」だけを"
                                            "付けてください。ほかの命令はつながないでください。")

    state = tempfile.mkdtemp(prefix="lab10_state_")
    opt = options(user, model=model, can_use_tool=can_use_tool, state_dir=state)
    saved_key = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        if auth == "key":
            key = saved_key or L._api_key()
            if not key:
                raise SystemExit("API キーが見つからないので、モデルを呼びません (--probe か --show-saved を使ってください)")
            opt.env = {**opt.env, "ANTHROPIC_API_KEY": key}        # CLI に渡すだけ。表示しない
            del key
        else:
            opt.env = {**opt.env, "ANTHROPIC_API_KEY": ""}         # キーを渡さない → CLI のログインで動く
        clean_workspace()
        events, t0 = [], time.time()
        prompt = TASKS[task].format(month=month)
        result = None
        with L.tag(f"{LAB}/{task}"):
            async with ClaudeSDKClient(opt) as c:
                await c.query(prompt)
                async for m in c.receive_response():
                    if isinstance(m, AssistantMessage):
                        for b in m.content:
                            if isinstance(b, TextBlock) and b.text.strip():
                                events.append({"type": "text", "text": b.text})
                            elif isinstance(b, ToolUseBlock):
                                events.append({"type": "tool_use", "name": b.name, "input": b.input})
                    elif isinstance(m, ResultMessage):
                        result = m
    finally:
        if saved_key:
            os.environ["ANTHROPIC_API_KEY"] = saved_key
    cost = float(getattr(result, "total_cost_usd", 0) or 0)
    L._record({"provider": f"agent-sdk/{auth}", "model": model, "cached": False,
               "cost_usd": round(cost, 6) if auth == "key" else 0.0, "seconds": round(time.time() - t0, 1)})
    out = {"task": task, "month": month, "model": model, "user": user, "auth": auth, "prompt": prompt, "events": events,
           "asked_permission": asked, "result": getattr(result, "result", None), "is_error": getattr(result, "is_error", None),
           "turns": getattr(result, "num_turns", None), "cost_usd": round(cost, 4), "seconds": round(time.time() - t0, 1),
           "usage": getattr(result, "usage", None)}
    if task == "report":
        rp = find_report(t0)
        out["report_file"] = os.path.relpath(rp, WORKSPACE) if rp else None
        produced = read_text_any(rp) if rp else (out["result"] or "")
        out["report_md"] = produced
        out["score"] = score_report(produced, await expected_report(month))
    return out


def show_run(o: dict) -> None:
    cost = f"{o['cost_usd']} USD" if o.get("auth", "key") == "key" else f"API 換算の目安 {o['cost_usd']} USD (プランのログインで実行)"
    print(f"■ {o['task']} / model={o['model']} / 利用者={o['user']} / {o.get('turns')} ターン / {o['seconds']} 秒 / {cost}")
    for e in o["events"]:
        if e["type"] == "tool_use":
            arg = json.dumps(e["input"], ensure_ascii=False)
            print(f"   → {e['name']} {arg[:100]}{'…' if len(arg) > 100 else ''}")
        else:
            t = e["text"].replace("\n", " ")
            print(f"🤖 {t[:140]}{'…' if len(t) > 140 else ''}")
    skills_used = [e["input"].get("skill") or e["input"].get("command") for e in o["events"]
                   if e["type"] == "tool_use" and e["name"] == "Skill"]
    print(f"■ 使った Skill: {skills_used or 'なし'}")
    for a in o["asked_permission"]:
        cmd = (a["input"].get("command") or "")[:90]
        if a.get("allowed"):
            what = cmd or os.path.relpath(a["input"].get("file_path", ""), WORKSPACE)
            print(f"   ✅ 許可を求められて通した ({a.get('why', 'Skill のスクリプトだけ')}): {a['tool']} {what}")
        else:
            print(f"   ⛔ 許可を求められて断った: {a['tool']} {cmd}" + (f"  … {a['why']}" if a.get("why") else ""))
    if "score" in o:
        s = o["score"]
        where = o.get("report_file") or "最後の返答"
        print(f"■ 答え合わせ ({where}): 数字の行 {s['matched']}/{s['numeric_lines']} がスクリプトの出力と一致")
        for ln in s["missing"]:
            print(f"   ✗ 見つからない: {ln[:100]}")


async def amain(argv=None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--task", choices=list(TASKS))
    ap.add_argument("--month", default="2026-09")
    ap.add_argument("--model", default=L.DEFAULT_MODEL)
    ap.add_argument("--user", default="U-02")
    ap.add_argument("--run", action="store_true", help="モデルを呼ぶ (要 API キー、または --auth login)")
    ap.add_argument("--auth", default="key", choices=["key", "login"],
                    help="key = API キー (既定) / login = キーを渡さず CLI のログイン (Claude のプラン) で呼ぶ")
    ap.add_argument("--show-saved", metavar="NAME")
    ap.add_argument("--name", default="")
    a = ap.parse_args(argv)
    if a.show_saved:
        p = os.path.join(HERE, "out", f"agent_{a.show_saved}.json")
        if not os.path.exists(p):
            print(f"講師の実行記録 out/agent_{a.show_saved}.json はありません")
            return {}
        o = read_json(p)
        show_run(o)
        return o
    if a.task and a.run:
        o = await run_task(a.task, a.month, a.model, a.user, a.auth)
        show_run(o)
        if a.name:
            write_json(os.path.join(out_dir(LAB), f"agent_{a.name}.json"), o)
        return o
    if a.task:
        print("--run を付けるとモデルを呼びます (要 API キー)。いまは何も呼びません。")
        return {}
    r = await probe()
    if a.name:
        write_json(os.path.join(out_dir(LAB), f"probe_{a.name}.json"), r)
    return r


def main(argv=None) -> dict:
    return anyio.run(amain, argv)


if __name__ == "__main__":
    from common.kit import utf8_console
    utf8_console()
    main()
