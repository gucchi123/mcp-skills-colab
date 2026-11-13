"""月次の数字の MCP サーバ (ユースケース 4)。読むだけ。

道具:
  get_monthly_sales(month, product)   製品別の売上 (product を省くと全製品) と合計・前月比
  get_inquiry_counts(month)           区分別の問い合わせ件数
  get_inventory_snapshot(month)       主要品目の月末在庫と発注点
資料:
  report://template                   月次レポートの型
数字はこのサーバが計算して返す (モデルに足し算をさせない)。
起動: python -m servers.report
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from mcp.server import CacheHint, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from common.identity import audit
from common.kit import data_path, read_csv, read_text, utf8_console

SERVER = "report"
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
SALES = read_csv(data_path("report", "sales.csv"))
INQ = read_csv(data_path("report", "inquiries_monthly.csv"))
INV = read_csv(data_path("report", "inventory_monthly.csv"))
MONTHS = sorted({r["month"] for r in SALES})

mcp = MCPServer(SERVER, instructions="ソラハ電機 (架空) の月次の売上・問い合わせ・在庫の数字を返すサーバ。数字は計算済みで返す。",
                cache_hints={"tools/list": CacheHint(ttl_ms=300_000, scope="public")})


def _month(m: str) -> str:
    m = m.strip().replace("/", "-")
    if len(m) == 6 and m[4] != "-":
        m = m[:4] + "-" + m[4:]
    if m not in MONTHS:
        raise ToolError(f"{m} の数字はありません。ある月: {MONTHS[0]}〜{MONTHS[-1]}")
    return m


class SalesRow(BaseModel):
    product: str
    units: int
    revenue_yen: int
    prev_revenue_yen: int | None = Field(description="前月の売上 (前月が無ければ null)")
    change_pct: float | None = Field(description="前月比 (%)、小数 1 桁")


class Sales(BaseModel):
    month: str
    rows: list[SalesRow]
    total_yen: int
    prev_total_yen: int | None
    total_change_pct: float | None
    top_product: str


def _rev(month: str, product: str | None = None) -> int:
    return sum(int(r["revenue"]) for r in SALES if r["month"] == month and (product is None or r["product"] == product))


def _pct(a: int, b: int | None) -> float | None:
    return None if not b else round((a - b) / b * 100, 1)


@mcp.tool(title="月次の売上", annotations=READ_ONLY)
def get_monthly_sales(month: str, product: str | None = None) -> Sales:
    """月 (YYYY-MM、2026-04〜2026-09) の製品別の売上・台数と、合計・前月比・いちばん売れた製品を返す。product で 1 製品に絞れる。"""
    m = _month(month)
    i = MONTHS.index(m)
    prev = MONTHS[i - 1] if i else None
    prods = [r["product"] for r in SALES if r["month"] == m and (product is None or r["product"] == product.upper())]
    if not prods:
        raise ToolError(f"製品 {product} の売上はありません")
    rows = []
    for p in prods:
        r = next(x for x in SALES if x["month"] == m and x["product"] == p)
        pv = _rev(prev, p) if prev else None
        rows.append(SalesRow(product=p, units=int(r["units"]), revenue_yen=int(r["revenue"]), prev_revenue_yen=pv,
                             change_pct=_pct(int(r["revenue"]), pv)))
    tot = sum(r.revenue_yen for r in rows)
    ptot = sum(r.prev_revenue_yen for r in rows) if prev else None
    audit(SERVER, "get_monthly_sales", month=m, product=product)
    return Sales(month=m, rows=rows, total_yen=tot, prev_total_yen=ptot, total_change_pct=_pct(tot, ptot),
                 top_product=max(rows, key=lambda r: r.revenue_yen).product)


class Inquiries(BaseModel):
    month: str
    by_category: dict[str, int]
    total: int
    prev_total: int | None


@mcp.tool(title="月次の問い合わせ件数", annotations=READ_ONLY)
def get_inquiry_counts(month: str) -> Inquiries:
    """月 (YYYY-MM) の問い合わせ件数を区分別 (使い方・不具合・請求・返品・苦情) と合計で返す。前月の合計も返す。"""
    m = _month(month)
    i = MONTHS.index(m)
    by = {r["category"]: int(r["count"]) for r in INQ if r["month"] == m}
    prev = sum(int(r["count"]) for r in INQ if r["month"] == MONTHS[i - 1]) if i else None
    audit(SERVER, "get_inquiry_counts", month=m)
    return Inquiries(month=m, by_category=by, total=sum(by.values()), prev_total=prev)


class StockRow(BaseModel):
    sku: str
    end_stock: int
    reorder_point: int
    below_reorder: bool


@mcp.tool(title="月末の在庫", annotations=READ_ONLY)
def get_inventory_snapshot(month: str) -> list[StockRow]:
    """月 (YYYY-MM) の主要 5 品目の月末在庫と発注点、発注点を割っているかを返す。"""
    m = _month(month)
    rows = [StockRow(sku=r["sku"], end_stock=int(r["end_stock"]), reorder_point=int(r["reorder_point"]),
                     below_reorder=int(r["end_stock"]) <= int(r["reorder_point"])) for r in INV if r["month"] == m]
    audit(SERVER, "get_inventory_snapshot", month=m)
    return rows


@mcp.resource("report://template", title="月次レポートの型", mime_type="text/markdown")
def template() -> str:
    return read_text(data_path("report", "template.md"))


if __name__ == "__main__":
    utf8_console()
    mcp.run()
