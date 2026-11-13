"""ラボ 10: Claude Agent SDK に、キットの MCP サーバと Skill を読ませる設定。

Agent SDK は Claude Code の本体 (同梱の CLI) を子プロセスで動かす。CLI が
  - Skill: 作業フォルダ (workspace/) の .claude/skills/ から読む (setting_sources=["project"] と skills=[...])
  - MCP  : mcp_servers に書いたサーバを stdio で起動し、道具を mcp__<サーバ>__<道具> の名前で見せる
  - 権限 : allowed_tools に無い道具は can_use_tool (人の承認の代わり) に聞く
を受け持つ。ラボ 9 で自分で書いた「Skill の読み込み」と「道具の繋ぎ込み」を、出来合いの仕組みに任せる形。

🔴 利用者 (SOLAHA_USER) はサーバを起動するときに環境変数で渡す (モデルに決めさせない)。
"""
from __future__ import annotations

import os
import shutil
import sys

from common.kit import ROOT

HERE = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.join(HERE, "workspace")
SKILLS = ("solaha-monthly-report", "solaha-contract-review")
READ_ONLY_TOOLS = [
    "mcp__report__get_monthly_sales", "mcp__report__get_inquiry_counts", "mcp__report__get_inventory_snapshot",
    "mcp__contract__list_contracts", "mcp__contract__get_contract", "mcp__contract__get_contract_checklist",
    "mcp__kb__search_regulations", "mcp__kb__get_regulation",
    "mcp__inventory__get_stock", "mcp__inventory__list_below_reorder",
]   # 書き込みのある道具 (mcp__inventory__create_purchase_order) だけは入れない


def prepare_workspace() -> str:
    """workspace/.claude/skills/ にキットの Skill を写す (Windows では symlink に管理者権限が要るので写す)。"""
    dst_root = os.path.join(WORKSPACE, ".claude", "skills")
    os.makedirs(dst_root, exist_ok=True)
    for name in SKILLS:
        dst = os.path.join(dst_root, name)
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(os.path.join(ROOT, "skills", name), dst, ignore=shutil.ignore_patterns("__pycache__"))
    return WORKSPACE


def mcp_servers(user: str, names=("report", "contract", "kb", "inventory"), state_dir: str | None = None) -> dict:
    env = {"PYTHONUTF8": "1", "PYTHONPATH": ROOT, "SOLAHA_USER": user}
    if state_dir:
        env["SOLAHA_STATE_DIR"] = state_dir
    return {n: {"type": "stdio", "command": sys.executable, "args": ["-m", f"servers.{n}"], "env": env} for n in names}


def options(user: str = "U-02", *, model: str = "claude-opus-5-5", effort: str = "high", can_use_tool=None,
            allowed_tools: list[str] | None = None, state_dir: str | None = None, max_turns: int = 20):
    from claude_agent_sdk import ClaudeAgentOptions
    prepare_workspace()
    return ClaudeAgentOptions(
        cwd=WORKSPACE,
        setting_sources=["project"],          # workspace/.claude/ だけを読む (講師の手元の設定を混ぜない)
        skills=list(SKILLS),
        mcp_servers=mcp_servers(user, state_dir=state_dir),
        strict_mcp_config=True,               # mcp_servers に書いたものだけ (ほかの設定ファイルの MCP を読まない)
        allowed_tools=allowed_tools if allowed_tools is not None else READ_ONLY_TOOLS,
        can_use_tool=can_use_tool,
        model=model,
        effort=effort,
        max_turns=max_turns,
        env={"PYTHONUTF8": "1"},
    )
