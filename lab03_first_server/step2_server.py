"""ステップ 2: 実務で使える形に育てる。ステップ 1 との違いは 5 つ。

  1. 構造化出力   戻り値を pydantic のモデルにする → outputSchema と structuredContent (JSON) が付く
  2. 引数の説明   Annotated[str, Field(description=..., ge=, le=)] → inputSchema に説明と範囲が入る
                  (🔴 docstring の Args: は inputSchema に入らない。引数の説明は Field に書く)
  3. 注釈         ToolAnnotations(read_only_hint=True) → 「読むだけ」とホストに伝える (ヒント。権限の代わりにはならない)
  4. 想定内の失敗 ToolError("…") → is_error=True と、その文がそのままモデルに届く (直し方を書いておく)
  5. 資料と定型文 resource (URI のひな形) と prompt

起動 (stdio): python lab03_first_server/step2_server.py
"""
from __future__ import annotations

import glob
import os
import sys
from typing import Annotated

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pydantic import BaseModel, Field  # noqa: E402

from mcp.server import MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ResourceError, ToolError  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402

from common.kit import data_path, read_text  # noqa: E402

DOCS = {os.path.basename(p)[:-3]: read_text(p) for p in sorted(glob.glob(data_path("kb", "regulations", "*.md")))}
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)


def _title(doc_id: str) -> str:
    return DOCS[doc_id].splitlines()[0].lstrip("# ").strip()


class Hit(BaseModel):
    doc_id: str = Field(description="文書番号 (get_regulation に渡せる)")
    title: str = Field(description="規程の題名")
    matched: int = Field(description="言葉を含む行の数")
    first_line: str = Field(description="最初に当たった行 (80 字まで)")


class Regulation(BaseModel):
    doc_id: str
    title: str
    chars: int = Field(description="本文の字数")
    text: str = Field(description="本文 (Markdown)")


mcp = MCPServer("regs-step2", instructions="ソラハ電機 (架空) の社内規程を探して読むサーバ。答えには文書番号を添えること。")


@mcp.tool(title="規程を探す", annotations=READ_ONLY)
def search_regulations(
    keyword: Annotated[str, Field(description="探す言葉 (例: 出張、経費、在宅勤務)")],
    limit: Annotated[int, Field(ge=1, le=10, description="返す件数の上限")] = 3,
) -> list[Hit]:
    """ソラハ電機の社内規程 (13 本) から言葉を含む規程を探し、当たった行 (題名の行は除く) の多い順に返す。"""
    hits = []
    for doc_id, text in DOCS.items():
        lines = [ln.strip() for ln in text.splitlines()[1:] if keyword in ln]
        if lines:
            hits.append(Hit(doc_id=doc_id, title=_title(doc_id), matched=len(lines), first_line=lines[0][:80]))
    return sorted(hits, key=lambda h: -h.matched)[:limit]


@mcp.tool(title="規程の全文", annotations=READ_ONLY)
def get_regulation(doc_id: Annotated[str, Field(description="文書番号 (a-01〜a-13)")]) -> Regulation:
    """文書番号の規程の全文を返す。番号が分からなければ先に search_regulations を使う。"""
    d = doc_id.strip().lower()
    if d not in DOCS:
        # 想定内の失敗。モデルが読んで直せるように、ある番号を添える
        raise ToolError(f"文書 {doc_id} はありません。ある文書: {min(DOCS)}〜{max(DOCS)}")
    return Regulation(doc_id=d, title=_title(d), chars=len(DOCS[d]), text=DOCS[d])


@mcp.resource("regs://{doc_id}", title="社内規程", mime_type="text/markdown")
def regulation(doc_id: str) -> str:
    """規程 1 本の全文 (資料として読む)。"""
    if doc_id not in DOCS:
        raise ResourceError(f"文書 {doc_id} はありません")
    return DOCS[doc_id]


@mcp.prompt(title="規程に基づいて答える")
def answer_with_citation(question: str) -> str:
    """規程だけを根拠に答えるときの型。"""
    return (f"次の質問に、社内規程だけを根拠に答えてください。\n質問: {question}\n"
            "search_regulations で探し、get_regulation で全文を読んでから答え、最後に「根拠: a-06」の形で文書番号を書く。"
            "規程に書いていないことは「規程に記載がありません」と答える。")


if __name__ == "__main__":
    mcp.run()
