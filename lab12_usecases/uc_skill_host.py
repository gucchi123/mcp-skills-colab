"""ラボ 12 の部品: Skill を読み込んだホスト。

Claude Code では、Skill (SKILL.md) が読み込まれると、モデルは手順どおりに MCP の道具を呼び、
スクリプトを Bash(python …) で動かし、references/ を Read で読む。このラボのホストには Bash も Read も無いので、
その 2 つの代わりを小さな MCP サーバ「skill」としてラボの中に置く:

  run_skill_script(skill, script, inputs)   scripts/ のスクリプトを子プロセスの python で本当に動かし、標準出力を返す
  read_skill_file(skill, path)              Skill のフォルダの中のファイル (references/…) を読む

  - 動かせるスクリプトは 2 本だけ (月次の build_report.py・契約の overall.py)。Skill のフォルダの外は読めない
  - モデルに見せる道具は SKILL.md の allowed-tools の mcp__… と、この skill サーバの道具だけ (load_skill が作る)
🔴 common/host.py は servers/ のサーバしか立てられないので、Host を継承して skill サーバを足している (common は書き換えない)。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from common.host import Host
from common.kit import ROOT, read_text

SKILLS = os.path.join(ROOT, "skills")
SCRIPTS = {("solaha-monthly-report", "build_report.py"): 3, ("solaha-contract-review", "overall.py"): 1}   # 入力の数

mcp = MCPServer("skill", instructions="読み込んだ Skill のスクリプトを実行し、Skill のファイルを読む (Bash(python) と Read の代わり)。")


@mcp.tool(title="Skill のスクリプトを実行する", annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def run_skill_script(skill: str, script: str, inputs: list[str]) -> str:
    """Skill の scripts/ にあるスクリプトを python で実行し、標準出力をそのまま返す。
    solaha-monthly-report の build_report.py: inputs に get_monthly_sales・get_inquiry_counts・get_inventory_snapshot の
    返事 (JSON の文字列そのまま) を、この順に 3 つ渡す (ファイルに保存して渡すのと同じ)。
    solaha-contract-review の overall.py: inputs に当たった項目の JSON を 1 つ渡す (例 '[{"rule": "R4", "level": "高"}]'、無ければ '[]')。"""
    want = SCRIPTS.get((skill, script))
    if want is None:
        raise ToolError(f"実行できるのは {', '.join(f'{k}/{s}' for k, s in SCRIPTS)} だけです")
    if len(inputs) != want:
        raise ToolError(f"{script} の inputs は {want} 個です (渡されたのは {len(inputs)} 個)")
    folder = os.path.join(SKILLS, skill)
    with tempfile.TemporaryDirectory(prefix="skill_") as tmp:
        if script == "build_report.py":                  # Skill の手順どおり、返事をファイルに保存してから渡す
            args = []
            for name, text in zip(("sales.json", "inquiries.json", "inventory.json"), inputs):
                p = os.path.join(tmp, name)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(text)
                args.append(p)
        else:
            args = inputs
        r = subprocess.run([sys.executable, os.path.join("scripts", script), *args], cwd=folder, capture_output=True,
                           text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"}, timeout=60)
    if r.returncode != 0:
        tail = (r.stderr or r.stdout).strip().splitlines()[-1:] or ["(出力なし)"]
        raise ToolError(f"{script} が止まりました (終了コード {r.returncode}): {tail[0][:300]}")
    return r.stdout.strip()


@mcp.tool(title="Skill のファイルを読む", annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def read_skill_file(skill: str, path: str) -> str:
    """Skill のフォルダの中のファイル (例 references/style.md) を読む。SKILL.md が「読む」と書いているファイルに使う。"""
    folder = os.path.realpath(os.path.join(SKILLS, skill))
    p = os.path.realpath(os.path.join(folder, path))
    if not folder.startswith(os.path.realpath(SKILLS)) or not p.startswith(folder + os.sep) or not os.path.isfile(p):
        raise ToolError(f"{skill}/{path} は読めません (Skill のフォルダの中のファイルだけ)")
    return read_text(p)


# ---------------------------------------------------------------- Skill の読み込み
def load_skill(name: str) -> dict:
    """SKILL.md を読み、{name, description, body, allowed} を返す。allowed はホストに渡す道具の型。"""
    text = read_text(os.path.join(SKILLS, name, "SKILL.md"))
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    fm = dict(re.findall(r"^([a-z-]+):\s*(.*)$", m.group(1), re.M))
    allowed = [t for t in fm.get("allowed-tools", "").split() if t.startswith("mcp__")] + ["mcp__skill__*"]
    return {"name": fm["name"], "description": fm["description"], "body": m.group(2).strip(), "allowed": allowed}


def skill_system(skill: dict, base: str) -> str:
    """Skill を読み込んだときのシステムプロンプト (Claude Code が SKILL.md の本文を文脈に入れるのと同じ考え)。"""
    return (f"{base}\n\n次の Skill が読み込まれています。手順どおりに進めてください。\n"
            f"<skill name=\"{skill['name']}\">\n{skill['body']}\n</skill>\n\n"
            f"このホストには Bash と Read がありません。スクリプトの実行は mcp__skill__run_skill_script "
            f"(skill=\"{skill['name']}\")、Skill のファイル (references/…) を読むのは mcp__skill__read_skill_file で行ってください。")


class SkillHost(Host):
    """Host に skill サーバ (同じプロセス) を足したもの。servers/ のサーバの立て方は Host のまま。"""

    def _target(self, name: str):
        if name == "skill":
            if self.mode != "inprocess":
                raise ValueError("skill サーバは inprocess だけで立てます")
            return mcp
        return super()._target(name)
