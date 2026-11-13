"""顧客台帳の MCP サーバ (ユースケース 3)。読むだけ。見せてよい項目は利用者ごとに変わる。

道具:
  find_customer(query)                  会社名・氏名の一部から顧客を探す
  get_customer(customer_id)             顧客 1 件 (見てよくない項目は「（非表示）」)
  list_customers_by_product(product)    製品を買っている顧客の一覧
資料:
  crm://policy                          顧客情報取扱規程

🔴 利用者は common.identity.current_user() (ホストが SOLAHA_USER で渡す・HTTP ではトークンから)。モデルの引数では決めない。
🔴 照会はすべて監査ログ (state/audit.jsonl) に残す。何を隠したかも残す。
起動: python -m servers.crm   (stdio。キットの根で)
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from mcp.server import CacheHint, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from common.identity import NotAllowed, audit, current_user
from common.kit import data_path, read_json, read_text, utf8_console
from common.policy import HIDDEN, redact

SERVER = "crm"
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
CUSTOMERS = {c["id"]: c for c in read_json(data_path("crm", "customers.json"))}

class CustomerBrief(BaseModel):
    id: str
    type: str = Field(description="法人 または 個人")
    name: str = Field(description="会社名・氏名。見てよくなければ（非表示）")
    products: list[str]


class Customer(CustomerBrief):
    sales_rep: str | None = Field(description="担当営業の社員番号")
    rank: str | None = Field(description="取引ランク")
    credit_limit_yen: int | str | None = Field(description="与信枠 (円)")
    contact: dict[str, str] = Field(description="先方担当者 (法人) / 本人 (個人) の連絡先")
    hidden: list[str] = Field(description="この利用者には見せなかった項目")


def _user() -> dict:
    try:
        return current_user()
    except NotAllowed as e:
        raise ToolError(str(e)) from None


def _brief(user: dict, c: dict) -> CustomerBrief:
    r, _ = redact(user, c)
    return CustomerBrief(id=r["id"], type=r["type"], name=r["name"], products=r["products"])



def build(**kw) -> MCPServer:
    """サーバを組み立てる。kw は MCPServer にそのまま渡す (第 7 部で token_verifier と auth を足して HTTP で公開する)。"""
    mcp = MCPServer(
        SERVER,
        instructions="ソラハ電機 (架空) の顧客台帳を読むサーバ。利用者の権限で見せられない項目は「（非表示）」で返す。",
        cache_hints={"tools/list": CacheHint(ttl_ms=300_000, scope="public")},
        **kw,
    )

    @mcp.tool(title="顧客を探す", annotations=READ_ONLY)
    def find_customer(query: str) -> list[CustomerBrief]:
        """会社名 (法人) の一部から顧客を探し、顧客番号・種別・名称・購入製品を返す。
        「株式会社」は付けなくてよい。個人のお客様は名前では探せない (顧客番号で get_customer を使う)。"""
        user = _user()
        q = query.replace("株式会社", "").strip()
        if not q:
            raise ToolError("探す言葉が空です")
        hits = [c for c in CUSTOMERS.values() if c["type"] == "法人" and q in c["name"]]
        audit(SERVER, "find_customer", query=query, returned=[c["id"] for c in hits])
        return [_brief(user, c) for c in hits]


    @mcp.tool(title="顧客 1 件を読む", annotations=READ_ONLY)
    def get_customer(customer_id: str) -> Customer:
        """顧客番号 (C-001 のような法人、IND-001 のような個人) から、顧客の詳細を返す。
        担当営業・取引ランク・与信枠・先方担当者の連絡先を含む。利用者の権限で見せられない項目は「（非表示）」になる。"""
        user = _user()
        c = CUSTOMERS.get(customer_id.strip().upper())
        if not c:
            raise ToolError(f"顧客 {customer_id} は見つかりません")
        r, hidden = redact(user, c)
        audit(SERVER, "get_customer", customer=c["id"], hidden=hidden)
        return Customer(**{k: r[k] for k in ("id", "type", "name", "products", "sales_rep", "rank",
                                             "credit_limit_yen", "contact")}, hidden=hidden)


    @mcp.tool(title="製品の購入顧客", annotations=READ_ONLY)
    def list_customers_by_product(product: str) -> list[CustomerBrief]:
        """製品の型番 (TL-200・GW-5・BX-10・SC-30・DP-8) を買っている顧客の一覧を返す。"""
        user = _user()
        p = product.strip().upper()
        hits = [c for c in CUSTOMERS.values() if p in c["products"]]
        audit(SERVER, "list_customers_by_product", product=p, returned=[c["id"] for c in hits])
        return [_brief(user, c) for c in hits]


    @mcp.resource("crm://policy", title="顧客情報取扱規程", mime_type="text/markdown")
    def policy() -> str:
        """だれがどの項目を見てよいかの規程。"""
        return read_text(data_path("crm", "customer_data_policy.md"))

    return mcp


mcp = build()
__all__ = ["mcp", "build", "HIDDEN"]


if __name__ == "__main__":
    utf8_console()
    mcp.run()
