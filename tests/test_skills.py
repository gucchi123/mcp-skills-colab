"""Skill の試験 (LLM なし)。SKILL.md の形・スクリプトの計算を正解と照合する。

  - SKILL.md の frontmatter が Agent Skills の決まり (name・description の長さと文字・ディレクトリ名との一致) に合う
  - 契約: overall.py の総合の判定が正解 8 本と一致する
  - 月次: report サーバの返事 → build_report.py の数字が正解 5 か月と一致する
"""
from __future__ import annotations

import glob
import importlib.util
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mcp import Client  # noqa: E402

from common.kit import data_path, read_json  # noqa: E402
from servers import report  # noqa: E402

SKILLS = sorted(glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md")))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: os.path.basename(os.path.dirname(p)))
def test_skill_frontmatter(path):
    text = open(path, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    assert m, "frontmatter が無い"
    fm = dict(re.findall(r"^([a-z-]+):\s*(.*)$", m.group(1), re.M))
    name, desc = fm["name"], fm["description"]
    assert 1 <= len(name) <= 64 and re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name)
    assert name == os.path.basename(os.path.dirname(path))
    assert not re.search("anthropic|claude", name)
    assert 1 <= len(desc) <= 1024
    assert len(m.group(2).splitlines()) <= 500
    for ref in re.findall(r"`((?:scripts|references)/[^`\s]+)`", text):     # 本文が指すファイルが在る
        assert os.path.exists(os.path.join(os.path.dirname(path), ref)), ref


def test_contract_overall_matches_gold():
    ov = load(os.path.join(ROOT, "skills", "solaha-contract-review", "scripts", "overall.py"), "overall")
    gold = read_json(data_path("contract", "gold_findings.json"))
    for cid, g in gold.items():
        assert ov.overall([{"rule": f["rule"], "level": f["level"]} for f in g["findings"]]) == g["overall"], cid


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_monthly_report_matches_gold():
    br = load(os.path.join(ROOT, "skills", "solaha-monthly-report", "scripts", "build_report.py"), "build_report")
    gold = read_json(data_path("report", "gold_numbers.json"))
    keys = ["revenue_total", "revenue_mom_pct", "top_product", "top_product_revenue", "fastest_growth_product",
            "fastest_growth_pct", "inquiries_total", "inquiries_mom_pct", "top_inquiry_category", "top_inquiry_count",
            "complaints", "low_stock_count", "low_stock_skus"]
    async with Client(report.mcp) as c:
        for m, g in gold.items():
            s = (await c.call_tool("get_monthly_sales", {"month": m})).structured_content
            q = (await c.call_tool("get_inquiry_counts", {"month": m})).structured_content
            inv = (await c.call_tool("get_inventory_snapshot", {"month": m})).structured_content
            json.dumps([s, q, inv])                      # ファイルに保存できる形であること
            _, nums = br.build(s, q, inv)
            for k in keys:
                assert nums[k] == g[k], (m, k, nums[k], g[k])
