"""ラボ 9 の部品: Messages API の上で「段階的に読む」を真似るスキルの読み込み係 (skill loader) を、MCP のホストに足す。

  SkillHost(["report"], user="U-04", provider=prov)       common.host.Host を継ぎ足しただけ (Host は書き換えない)
    段階 1: システムプロンプトに、スキルの name と description の一覧だけを入れる
    段階 2: 道具 load_skill(name)               → SKILL.md の本文を返す
    段階 3: 道具 read_skill_file(name, path)    → references/ などのファイルを返す
            道具 run_skill_script(name, script, input_json) → スキルの scripts/ の .py をホストの側で実行し、出力だけを返す

  🔴 守り (モデルが何を渡してきても、ここで止める):
    - name は一覧にあるスキルだけ。path・script は、そのスキルのフォルダの中だけ (.. や絶対パス、別のスキルは断る)
    - スクリプトは scripts/ の中の .py だけ。シェルを通さず [python, スクリプト, 引数...] の並びで起動 (; や | は文字のまま渡る)
    - 入力ファイルは使い捨ての作業フォルダに書く。名前は英数字と ._- だけ (フォルダを指せない)。時間の上限 30 秒

  本物の Claude では: Claude API は Skills をコンテナ + コード実行で動かす (container.skills、Skills API は GA)。
  Claude Code・Agent SDK は .claude/skills/ のフォルダから読む。この読み込み係は、その仕組みを目で見るためのもの。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile

from common.host import Host

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(ROOT, "skills")
LOCAL = ("load_skill", "read_skill_file", "run_skill_script")
SAFE_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
MAX_OUT = 20_000


class SkillError(Exception):
    """モデルに理由を返す失敗 (道具の結果に is_error で載る)。"""


def read_frontmatter(path: str) -> tuple[dict, str]:
    """SKILL.md の frontmatter (上の段の key: value だけ) と本文。"""
    with open(path, encoding="utf-8") as f:
        text = f.read().replace("\r\n", "\n")
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        raise SkillError(f"frontmatter がありません: {path}")
    fm = {k: v.strip().strip("\"'") for k, v in re.findall(r"^([a-z-]+):[ \t]*(.*)$", m.group(1), re.M)}
    return fm, m.group(2)


def discover(skills_dir: str = SKILLS_DIR) -> dict[str, dict]:
    """skills/ の下のスキルを探す。{name: {"dir", "description", "body"}}"""
    out = {}
    for d in sorted(os.listdir(skills_dir)):
        p = os.path.join(skills_dir, d, "SKILL.md")
        if os.path.exists(p):
            fm, body = read_frontmatter(p)
            out[fm["name"]] = {"dir": os.path.join(skills_dir, d), "description": fm["description"], "body": body}
    return out


def skill_list_text(skills: dict[str, dict]) -> str:
    lines = "\n".join(f"- {n}: {s['description']}" for n, s in skills.items())
    return ("<available_skills>\n" + lines + "\n</available_skills>\n"
            "依頼に合うスキルがあれば、取りかかる前に load_skill でそのスキルの手順を読み、手順どおりに進める。"
            "合うスキルが無ければ使わない。")


def tool_specs(names: list[str]) -> list[dict]:
    return [
        {"name": "load_skill", "description": "スキルの手順 (SKILL.md の本文) を読む。一覧にあるスキルの name を渡す。",
         "input_schema": {"type": "object", "properties": {"name": {"type": "string", "enum": names}},
                          "required": ["name"]}},
        {"name": "read_skill_file",
         "description": "スキルのフォルダの中のファイル (references/style.md など、手順が指すもの) を読む。",
         "input_schema": {"type": "object", "properties": {"name": {"type": "string", "enum": names},
                                                           "path": {"type": "string"}}, "required": ["name", "path"]}},
        {"name": "run_skill_script",
         "description": ("スキルの scripts/ の Python スクリプトを実行し、標準出力を返す。input_json は "
                         '{"args": [引数の文字列...], "files": {"ファイル名": 中身 (文字列か JSON)}}。'
                         "files は作業フォルダに書かれ、args からファイル名で指せる。"),
         "input_schema": {"type": "object", "properties": {"name": {"type": "string", "enum": names},
                                                           "script": {"type": "string"},
                                                           "input_json": {"type": "object"}},
                          "required": ["name", "script"]}},
    ]


def inside(base: str, rel: str) -> str:
    """base の中のファイルの本当の場所。外に出るもの (.. ・絶対パス・リンクで外へ) は断る。"""
    if not isinstance(rel, str) or not rel or os.path.isabs(rel) or rel.startswith(("/", "\\")) or ":" in rel:
        raise SkillError(f"パスは、スキルのフォルダからの相対パスで: {rel!r}")
    real_base = os.path.realpath(base)
    p = os.path.realpath(os.path.join(real_base, rel))
    if os.path.commonpath([real_base, p]) != real_base:
        raise SkillError(f"スキルのフォルダの外は読めません: {rel}")
    if not os.path.isfile(p):
        raise SkillError(f"ファイルがありません: {rel}")
    return p


class SkillLoader:
    """3 つの道具の中身 (MCP とは関係なく単独でも試せる)。"""

    def __init__(self, skills: dict[str, dict] | None = None, descriptions: dict[str, str] | None = None):
        self.skills = {n: dict(s) for n, s in (skills or discover()).items()}
        for n, d in (descriptions or {}).items():          # 説明文だけ差し替える実験 (skills/ は書き換えない)
            self.skills[n]["description"] = d

    def _skill(self, name) -> dict:
        if name not in self.skills:
            raise SkillError(f"スキル {name!r} はありません。ある名前: {', '.join(self.skills)}")
        return self.skills[name]

    def load_skill(self, name: str) -> str:
        return self._skill(name)["body"]

    def read_skill_file(self, name: str, path: str) -> str:
        p = inside(self._skill(name)["dir"], path)
        if os.path.basename(p) == "SKILL.md":
            raise SkillError("SKILL.md は load_skill で読む")
        with open(p, encoding="utf-8") as f:
            return f.read()[:MAX_OUT]

    def run_skill_script(self, name: str, script: str, input_json: dict | None = None) -> str:
        sk = self._skill(name)
        rel = script if "/" in script or "\\" in script else f"scripts/{script}"
        p = inside(sk["dir"], rel)
        scripts = os.path.realpath(os.path.join(sk["dir"], "scripts"))
        if os.path.dirname(p) != scripts or not p.endswith(".py"):
            raise SkillError(f"実行できるのは scripts/ の中の .py だけ: {script}")
        inp = input_json or {}
        if isinstance(inp, str):
            inp = json.loads(inp)
        args, files = inp.get("args", []), inp.get("files", {})
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            raise SkillError("args は文字列の並び")
        with tempfile.TemporaryDirectory(prefix="skillrun_") as work:
            for fn, content in files.items():
                if not SAFE_FILE.fullmatch(fn) or ".." in fn:
                    raise SkillError(f"ファイル名は英数字と ._- だけ: {fn!r}")
                with open(os.path.join(work, fn), "w", encoding="utf-8") as f:
                    f.write(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False))
            env = {"PYTHONUTF8": "1", "PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
            r = subprocess.run([sys.executable, p, *args], cwd=work, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=30, env=env, shell=False)
        if r.returncode != 0:      # 最後の行 (例外の種類と理由、スクリプトの 🔴 の文) をモデルに返す
            last = (r.stderr.strip() or r.stdout.strip()).splitlines()[-1:] or [""]
            raise SkillError(f"スクリプトが終了コード {r.returncode} で止まった: {last[0][:300]}")
        return r.stdout[:MAX_OUT]

    def call(self, tool: str, args: dict) -> str:
        if tool == "load_skill":
            return self.load_skill(args.get("name"))
        if tool == "read_skill_file":
            return self.read_skill_file(args.get("name"), args.get("path"))
        if tool == "run_skill_script":
            return self.run_skill_script(args.get("name"), args.get("script", ""), args.get("input_json"))
        raise SkillError(f"道具 {tool} はありません")


class SkillHost(Host):
    """Host + スキルの読み込み係。MCP の道具 (mcp__report__… など) と 3 つの道具を同じ並びでモデルに見せる。"""

    def __init__(self, servers=("report",), *, system: str = "", descriptions: dict[str, str] | None = None,
                 skills: dict[str, dict] | None = None, **kw):
        self.loader = SkillLoader(skills, descriptions)
        base = (system + "\n\n") if system else ""
        super().__init__(servers, system=base + skill_list_text(self.loader.skills), **kw)

    async def refresh_tools(self) -> None:
        await super().refresh_tools()
        self.tools += tool_specs(list(self.loader.skills))

    async def call(self, full: str, args: dict) -> tuple[str, bool]:
        if full not in LOCAL:
            return await super().call(full, args)
        try:
            txt, err = self.loader.call(full, args), False
        except SkillError as e:
            txt, err = str(e), True
        except (subprocess.TimeoutExpired, ValueError, TypeError) as e:
            txt, err = f"{type(e).__name__}: {e}", True
        self._trace.append({"type": "tool", "server": "skill", "tool": full, "args": args, "is_error": err,
                            "text": txt})
        return txt, err
