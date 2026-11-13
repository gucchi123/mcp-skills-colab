"""契約書の文書庫の MCP サーバ (ユースケース 5)。読むだけ。

道具:
  list_contracts()               契約書の一覧 (番号・題・相手方)
  get_contract(contract_id)      契約書 1 本の全文
  get_contract_checklist()       一次レビューのチェックリスト (R1〜R7 と総合の判定)
資料:
  contracts://{contract_id}      契約書 1 本
判定 (どこが問題か) はこのサーバではしない。チェックリストの当てはめは Skill (手順) とモデルが行い、正解と照合する。
起動: python -m servers.contract
"""
from __future__ import annotations

import glob
import os

from pydantic import BaseModel

from mcp.server import CacheHint, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from common.identity import audit
from common.kit import data_path, read_text, utf8_console

SERVER = "contract"
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
DOCS = {os.path.splitext(os.path.basename(p))[0]: read_text(p)
        for p in sorted(glob.glob(data_path("contract", "LC-*.md")))}

mcp = MCPServer(SERVER, instructions="ソラハ電機 (架空) の契約書を読むサーバ。",
                cache_hints={"tools/list": CacheHint(ttl_ms=300_000, scope="public")})


class ContractBrief(BaseModel):
    id: str
    title: str
    party: str


def _brief(cid: str, text: str) -> ContractBrief:
    head = text.splitlines()[0].lstrip("# ")
    title = head.split("（")[0]
    party = text.split("乙: ")[1].split("（")[0] if "乙: " in text else "-"
    return ContractBrief(id=cid, title=title, party=party)


@mcp.tool(title="契約書の一覧", annotations=READ_ONLY)
def list_contracts() -> list[ContractBrief]:
    """契約書の番号 (LC-01〜LC-08)・題・相手方の一覧を返す。"""
    audit(SERVER, "list_contracts")
    return [_brief(k, v) for k, v in DOCS.items()]


@mcp.tool(title="契約書を読む", annotations=READ_ONLY)
def get_contract(contract_id: str) -> str:
    """契約書の番号 (LC-01 など) から全文を返す。"""
    cid = contract_id.strip().upper()
    if cid not in DOCS:
        raise ToolError(f"契約書 {contract_id} はありません。ある番号: {', '.join(DOCS)}")
    audit(SERVER, "get_contract", contract=cid)
    return DOCS[cid]


@mcp.tool(title="一次レビューのチェックリスト", annotations=READ_ONLY)
def get_contract_checklist() -> str:
    """契約書の一次レビューで確認する項目 (R1〜R7) と、総合の判定 (法務室レビュー必須・部長確認・担当者確認・問題なし) の決め方を返す。"""
    audit(SERVER, "get_contract_checklist")
    return read_text(data_path("contract", "checklist.md"))


@mcp.resource("contracts://{contract_id}", title="契約書", mime_type="text/markdown")
def contract(contract_id: str) -> str:
    if contract_id not in DOCS:
        raise ToolError(f"契約書 {contract_id} はありません")
    return DOCS[contract_id]


if __name__ == "__main__":
    utf8_console()
    mcp.run()
