"""ラボ 8 の部品: SKILL.md を読む・決まりに照らす・段階ごとに「文脈に入る量」を測る。

  parse_skill(dir)      frontmatter (name・description・allowed-tools…)・本文・本文が指すファイル・フォルダの中身
  validate(skill)       Agent Skills の決まり (agentskills.io/specification と Claude API の追加制約) に照らす
  levels(skill)         段階 1 (name+description、いつも文脈に入る) / 段階 2 (本文、使うときだけ) / 段階 3 (references・scripts、要るときだけ)
  est_tokens(text)      トークン数の **見積り** (英数字 4 文字 ≈ 1、それ以外 1 文字 ≈ 1 の粗い目安)。実測は count_tokens()

🔴 PyYAML は使わない (講座の venv に無い)。frontmatter は「key: value」と、metadata のような 1 段の入れ子だけを読む簡易版。
"""
from __future__ import annotations

import glob
import json
import math
import os
import re
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(ROOT, "skills")
REF = re.compile(r"`((?:scripts|references|assets)/[^`\s]+)`")       # 本文が指すファイル (`scripts/x.py` の形)
XML = re.compile(r"<[A-Za-z/][^>]*>")


# ---------------------------------------------------------------- 読む
@dataclass
class Skill:
    dir: str
    text: str                                    # SKILL.md の全文
    fm: dict                                     # frontmatter
    fm_text: str                                 # frontmatter の生の文
    body: str                                    # 本文 (--- の後ろ)
    files: dict = field(default_factory=dict)    # フォルダの中の SKILL.md 以外 {相対パス: 中身}
    refs: list = field(default_factory=list)     # 本文が指すファイル

    @property
    def name(self) -> str:
        return str(self.fm.get("name", ""))

    @property
    def description(self) -> str:
        return str(self.fm.get("description", ""))


def _unquote(v: str):
    """引用符で囲めば文字列。囲まない数字・true/false は YAML と同じく数・真偽になる (version: 1.0 は文字列ではない)。"""
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    if re.fullmatch(r"-?\d+\.\d*", v):
        return float(v)
    if v in ("true", "false"):
        return v == "true"
    return v


def parse_frontmatter(fm_text: str) -> dict:
    """key: value と、値の無い key の下の字下げした key: value (1 段の入れ子) を読む。"""
    out: dict = {}
    cur = None
    for line in fm_text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0] in " \t" and cur is not None:
            k, _, v = line.strip().partition(":")
            out[cur][k.strip()] = _unquote(v)
            continue
        k, _, v = line.partition(":")
        k, v = k.strip(), v.strip()
        if v == "":
            out[k], cur = {}, k
        else:
            out[k], cur = _unquote(v), None
    return out


def parse_text(text: str, dir: str = "") -> Skill:
    text = text.replace("\r\n", "\n")
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        return Skill(dir=dir, text=text, fm={}, fm_text="", body=text)
    return Skill(dir=dir, text=text, fm=parse_frontmatter(m.group(1)), fm_text=m.group(1), body=m.group(2),
                 refs=sorted(set(REF.findall(m.group(2)))))


def parse_skill(path: str) -> Skill:
    """path はスキルのフォルダ (SKILL.md の入った所)。"""
    with open(os.path.join(path, "SKILL.md"), encoding="utf-8") as f:
        s = parse_text(f.read(), path)
    for p in sorted(glob.glob(os.path.join(path, "**", "*"), recursive=True)):
        rel = os.path.relpath(p, path).replace("\\", "/")
        if os.path.isdir(p) or rel == "SKILL.md" or "__pycache__" in rel:
            continue
        with open(p, encoding="utf-8") as f:
            s.files[rel] = f.read().replace("\r\n", "\n")
    return s


def all_skills(names: list[str] | None = None) -> list[Skill]:
    dirs = sorted(d for d in glob.glob(os.path.join(SKILLS_DIR, "*")) if os.path.exists(os.path.join(d, "SKILL.md")))
    out = [parse_skill(d) for d in dirs]
    if names:
        out = [s for s in out if s.name in names or os.path.basename(s.dir) in names]
    return out


# ---------------------------------------------------------------- 決まりに照らす
@dataclass
class Check:
    rule: str
    ok: bool
    detail: str = ""
    level: str = "必須"      # 必須 / 推奨 / Claude API (Claude の API に載せるときの追加の決まり)


def est_tokens(text: str) -> int:
    """トークン数の見積り。🔴 粗い目安 (英数字・記号 4 文字 ≈ 1、日本語など 1 文字 ≈ 1)。本当の数は --count-tokens で。"""
    ascii_n = sum(1 for ch in text if ord(ch) < 128)
    return math.ceil(ascii_n / 4 + (len(text) - ascii_n))


def validate(s: Skill) -> list[Check]:
    fm, name, desc = s.fm, s.name, s.description
    meta = fm.get("metadata", {})
    out = [
        Check("frontmatter がある", bool(s.fm_text)),
        Check("name 1〜64 文字", 1 <= len(name) <= 64, f"{len(name)} 文字"),
        Check("name は a-z 0-9 - だけ・先頭末尾と連続のハイフン無し", bool(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name)), name),
        Check("name = フォルダ名", not s.dir or name == os.path.basename(s.dir), os.path.basename(s.dir)),
        Check("description 1〜1024 文字", 1 <= len(desc) <= 1024, f"{len(desc)} 文字"),
        Check("compatibility 500 文字以内", len(str(fm.get("compatibility", "") or "")) <= 500,
              f"{len(str(fm.get('compatibility', '') or ''))} 文字"),
        Check("metadata は 文字列→文字列", isinstance(meta, dict) and all(isinstance(v, str) for v in meta.values()),
              ", ".join(meta) if isinstance(meta, dict) else str(meta)),
        Check("name に anthropic / claude を含まない", not re.search("anthropic|claude", name), level="Claude API"),
        Check("name・description に XML タグが無い", not XML.search(name + desc), level="Claude API"),
        Check("本文 500 行以内", len(s.body.splitlines()) <= 500, f"{len(s.body.splitlines())} 行", level="推奨"),
        Check("本文 5000 トークン未満 (見積り)", est_tokens(s.body) < 5000, f"約 {est_tokens(s.body)}", level="推奨"),
    ]
    if "allowed-tools" in fm:
        out.append(Check("allowed-tools はスペース区切り (Experimental)", "," not in fm["allowed-tools"],
                         f"{len(fm['allowed-tools'].split())} 個", level="推奨"))
    missing = [r for r in s.refs if r not in s.files]
    out.append(Check("本文が指すファイルが在る", not missing, ", ".join(missing) or f"{len(s.refs)} 個とも在る"))
    deeper = [f"{r}→{x}" for r in s.refs if r in s.files for x in REF.findall(s.files[r]) if x != r]
    out.append(Check("参照は 1 階層まで (参照先がさらに別のファイルを指さない)", not deeper, ", ".join(deeper),
                     level="推奨"))
    return out


# ---------------------------------------------------------------- 段階ごとに入る量
def listing_line(name: str, description: str) -> str:
    """段階 1: システムプロンプトのスキル一覧に入る 1 行 (name と description だけ)。"""
    return f"- {name}: {description}"


def levels(s: Skill) -> dict:
    l1 = listing_line(s.name, s.description)
    l3 = {p: t for p, t in s.files.items() if p.startswith(("references/", "assets/"))}
    scripts = {p: t for p, t in s.files.items() if p.startswith("scripts/")}
    return {"l1": l1, "l2": s.body, "l3_read": l3, "scripts": scripts}


def size(text: str) -> tuple[int, int]:
    return len(text), est_tokens(text)


def as_tool(name: str, description: str) -> dict:
    """同じ内容を「道具の説明」に詰めたときの道具の定義 (Messages API の tools の 1 つ)。"""
    return {"name": name.replace("-", "_"), "description": description,
            "input_schema": {"type": "object", "properties": {"request": {"type": "string"}}, "required": ["request"]}}


def tool_json(t: dict) -> str:
    return json.dumps(t, ensure_ascii=False)


# ---------------------------------------------------------------- わざと壊した見本 (決まりの検査を見せる)
BAD_SAMPLES = {
    "Solaha_Report": ("---\nname: Solaha_Report\ndescription: レポート\n---\n# 手順\n`references/style.md` を読む\n",
                      "solaha-report"),
    "claude-helper": ("---\nname: claude-helper\ndescription: " + "何でも手伝う。" * 150
                      + "\nmetadata:\n  version: 1.0\n---\n本文\n", "claude-helper"),
    "no-frontmatter": ("# 手順だけ\n1. 何かする\n", "no-frontmatter"),
}


def bad_skill(key: str) -> Skill:
    text, folder = BAD_SAMPLES[key]
    return parse_text(text, os.path.join("(見本)", folder))


# ---------------------------------------------------------------- 本物のトークン数 (キーがあるときだけ)
def count_tokens(texts: dict[str, str], model: str) -> dict[str, int] | None:
    """anthropic の messages.count_tokens で実測する。キーが無ければ何もしないで None。
    🔴 キーは表示しない。LLM_NO_KEY=1 ならキーを探さない (common.llm._api_key と同じ規則)。
    1 通の依頼の枠 (役割など) の分を引くため、"." だけの依頼の数を引く。"""
    from common.llm import _api_key
    key = _api_key()
    if not key:
        return None
    from anthropic import Anthropic
    client = Anthropic(api_key=key)
    del key

    def n(t: str) -> int:
        return client.messages.count_tokens(model=model, messages=[{"role": "user", "content": t}]).input_tokens

    base = n(".")
    return {k: n(t) - base for k, t in texts.items()}
