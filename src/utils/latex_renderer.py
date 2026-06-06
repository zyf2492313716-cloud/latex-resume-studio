#!/usr/bin/env python3
"""LaTeX resume renderer for the isolated LaTeX Resume Studio workspace.

The renderer is intentionally additive: it consumes the same JSON data model used by
src/utils/aiParser.js and emits a .tex file for every render. If a supported LaTeX
compiler is installed, it also compiles the file to PDF.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

SUPPORTED_COMPILERS = ("tectonic", "xelatex", "lualatex", "latexmk")

TEX_ESCAPE_MAP = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

BULLET_PREFIX_RE = re.compile(r"^\s*[-•*·●◦▪▫]+\s*")


def json_dumps(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def print_json(payload: Dict[str, Any]) -> None:
    print(json_dumps(payload))


def find_default_templates_dir() -> Path:
    env_dir = os.environ.get("LATEX_TEMPLATES_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()

    script = Path(__file__).resolve()
    candidates = [
        script.parents[2] / "latex_templates" if len(script.parents) > 2 else None,  # dev: repo/src/utils/file.py
        script.parents[1] / "latex_templates" if len(script.parents) > 1 else None,  # packaged: Resources/utils/file.py
        Path.cwd() / "latex_templates",
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate.resolve()
    return (script.parents[2] / "latex_templates").resolve()


def load_meta(template_dir: Path) -> Dict[str, Any]:
    meta_path = template_dir / "meta.json"
    with meta_path.open("r", encoding="utf-8") as f:
        meta = json.load(f)
    meta.setdefault("id", template_dir.name)
    meta.setdefault("displayName", meta["id"])
    meta.setdefault("group", "LaTeX 模板")
    meta.setdefault("tags", [])
    meta.setdefault("engineType", "latex")
    meta.setdefault("kind", "latex")
    return meta


def list_templates(templates_dir: Path) -> List[Dict[str, Any]]:
    if not templates_dir.exists():
        return []
    items: List[Dict[str, Any]] = []
    for child in sorted(templates_dir.iterdir(), key=lambda p: p.name):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        if not (child / "meta.json").exists() or not (child / "template.tex.j2").exists():
            continue
        try:
            meta = load_meta(child)
            meta["path"] = str(child)
            items.append(meta)
        except Exception as exc:  # pragma: no cover - diagnostic path
            items.append({
                "id": child.name,
                "displayName": child.name,
                "path": str(child),
                "kind": "latex",
                "engineType": "latex",
                "error": str(exc),
            })
    return items


def detect_compiler(preferred: Optional[str] = None) -> Dict[str, Any]:
    candidates: Iterable[str] = [preferred] if preferred else SUPPORTED_COMPILERS
    checked: List[Dict[str, Any]] = []
    for name in candidates:
        if not name:
            continue
        path = shutil.which(name)
        checked.append({"name": name, "path": path})
        if path:
            return {
                "available": True,
                "name": name,
                "path": path,
                "checked": checked,
                "message": f"已检测到 LaTeX 编译器: {name}",
            }
    return {
        "available": False,
        "name": None,
        "path": None,
        "checked": checked,
        "message": "未检测到 tectonic/xelatex/lualatex/latexmk；当前可导出 .tex，安装 Tectonic 或 MacTeX 后可生成 PDF。",
    }


def tex_escape(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    return "".join(TEX_ESCAPE_MAP.get(ch, ch) for ch in text)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def split_description(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw_items = [str(v) for v in value]
    else:
        text = str(value).replace("\r\n", "\n").replace("\r", "\n")
        # Preserve explicit newlines first. If the user entered one long Chinese paragraph,
        # split common resume separators into bullets as a gentle normalization.
        if "\n" in text:
            raw_items = text.split("\n")
        else:
            raw_items = re.split(r"(?<=[。；;])\s*", text)
    items: List[str] = []
    for item in raw_items:
        cleaned = BULLET_PREFIX_RE.sub("", item).strip()
        cleaned = cleaned.strip("；;。 ")
        if cleaned:
            items.append(tex_escape(cleaned))
    return items


def safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def normalize_basic(raw: Dict[str, Any]) -> Dict[str, Any]:
    basic = raw.get("basicInfo") or {}
    phone = clean_text(basic.get("phone"))
    email = clean_text(basic.get("email"))
    wechat = clean_text(basic.get("wechat"))
    github = clean_text(basic.get("github"))
    contacts = []
    for label, value in [("电话", phone), ("邮箱", email), ("微信", wechat), ("GitHub", github)]:
        if value:
            contacts.append({"label": tex_escape(label), "value": tex_escape(value)})
    return {
        "name": tex_escape(clean_text(basic.get("name")) or "求职者"),
        "title": tex_escape(clean_text(basic.get("title"))),
        "phone": tex_escape(phone),
        "email": tex_escape(email),
        "wechat": tex_escape(wechat),
        "github": tex_escape(github),
        "summary": tex_escape(clean_text(basic.get("summary"))),
        "contacts": contacts,
    }


def normalize_entry(item: Dict[str, Any], fields: Iterable[str]) -> Dict[str, Any]:
    normalized = {field: tex_escape(clean_text(item.get(field))) for field in fields}
    normalized["date"] = tex_escape(clean_text(item.get("date")))
    normalized["description"] = tex_escape(clean_text(item.get("description")))
    normalized["bullets"] = split_description(item.get("description"))
    return normalized


def normalize_context(raw: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    education = [normalize_entry(item, ("school", "major", "degree")) for item in safe_list(raw.get("education")) if isinstance(item, dict)]
    experience = [normalize_entry(item, ("company", "role")) for item in safe_list(raw.get("experience")) if isinstance(item, dict)]
    projects = [normalize_entry(item, ("name", "role")) for item in safe_list(raw.get("projects")) if isinstance(item, dict)]
    research = [normalize_entry(item, ("name", "role")) for item in safe_list(raw.get("research")) if isinstance(item, dict)]
    student_work = [normalize_entry(item, ("organization", "role")) for item in safe_list(raw.get("studentWork")) if isinstance(item, dict)]
    honors = [tex_escape(clean_text(item)) for item in safe_list(raw.get("honors")) if clean_text(item)]
    skills = [tex_escape(clean_text(item)) for item in safe_list(raw.get("skills")) if clean_text(item)]

    sections = {
        "education": education,
        "experience": experience,
        "projects": projects,
        "research": research,
        "studentWork": student_work,
        "honors": honors,
        "skills": skills,
    }
    return {
        "meta": meta,
        "basic": normalize_basic(raw),
        "education": education,
        "experience": experience,
        "projects": projects,
        "research": research,
        "studentWork": student_work,
        "honors": honors,
        "skills": skills,
        "sections": sections,
    }


def sanitize_filename(value: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|\s]+", "_", value).strip("._")
    return value or "resume"


def resolve_template(templates_dir: Path, template_id: str) -> Tuple[Path, Dict[str, Any]]:
    if not re.match(r"^[A-Za-z0-9_.-]+$", template_id):
        raise ValueError(f"非法模板 ID: {template_id}")
    template_dir = templates_dir / template_id
    if not template_dir.exists():
        raise FileNotFoundError(f"LaTeX 模板不存在: {template_id}")
    if not (template_dir / "template.tex.j2").exists():
        raise FileNotFoundError(f"模板缺少 template.tex.j2: {template_id}")
    return template_dir, load_meta(template_dir)


def render_tex(data_path: Path, template_id: str, output_dir: Path, templates_dir: Path) -> Dict[str, Any]:
    template_dir, meta = resolve_template(templates_dir, template_id)
    with data_path.open("r", encoding="utf-8") as f:
        raw_data = json.load(f)

    context = normalize_context(raw_data, meta)
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["tex"] = tex_escape

    try:
        template = env.get_template(f"{template_dir.name}/template.tex.j2")
    except TemplateNotFound as exc:
        raise FileNotFoundError(f"Jinja2 模板未找到: {exc}") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_name = clean_text((raw_data.get("basicInfo") or {}).get("name")) or "resume"
    file_stem = sanitize_filename(f"{raw_name}_{template_id}")
    tex_path = output_dir / f"{file_stem}.tex"
    rendered = template.render(**context)
    tex_path.write_text(rendered, encoding="utf-8")
    return {
        "success": True,
        "template": meta,
        "texPath": str(tex_path),
        "pdfPath": None,
        "compiled": False,
    }


def run_command(cmd: List[str], cwd: Path, timeout: int = 90000) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout / 1000,
        check=False,
    )


def compile_pdf(tex_path: Path, compiler: Dict[str, Any]) -> Dict[str, Any]:
    name = compiler.get("name")
    out_dir = tex_path.parent
    pdf_path = tex_path.with_suffix(".pdf")

    commands: List[List[str]] = []
    if name == "tectonic":
        commands = [[compiler["path"], "--keep-logs", "--synctex=0", str(tex_path)]]
    elif name == "xelatex":
        commands = [[compiler["path"], "-interaction=nonstopmode", "-halt-on-error", "-output-directory", str(out_dir), str(tex_path)]] * 2
    elif name == "lualatex":
        commands = [[compiler["path"], "-interaction=nonstopmode", "-halt-on-error", "-output-directory", str(out_dir), str(tex_path)]] * 2
    elif name == "latexmk":
        commands = [[compiler["path"], "-xelatex", "-interaction=nonstopmode", "-halt-on-error", "-outdir=" + str(out_dir), str(tex_path)]]
    else:
        return {"compiled": False, "pdfPath": None, "compileError": f"不支持的编译器: {name}"}

    stdout_chunks: List[str] = []
    stderr_chunks: List[str] = []
    for cmd in commands:
        proc = run_command(cmd, out_dir)
        stdout_chunks.append(proc.stdout or "")
        stderr_chunks.append(proc.stderr or "")
        if proc.returncode != 0:
            return {
                "compiled": False,
                "pdfPath": None,
                "compileError": f"{name} 编译失败，退出码 {proc.returncode}",
                "stdout": "\n".join(stdout_chunks)[-8000:],
                "stderr": "\n".join(stderr_chunks)[-8000:],
            }

    return {
        "compiled": pdf_path.exists(),
        "pdfPath": str(pdf_path) if pdf_path.exists() else None,
        "compileError": None if pdf_path.exists() else f"{name} 执行完成但未生成 PDF",
        "stdout": "\n".join(stdout_chunks)[-8000:],
        "stderr": "\n".join(stderr_chunks)[-8000:],
    }


def command_list(args: argparse.Namespace) -> int:
    templates_dir = Path(args.templates_dir).resolve() if args.templates_dir else find_default_templates_dir()
    print_json({"success": True, "templatesDir": str(templates_dir), "templates": list_templates(templates_dir)})
    return 0


def command_status(args: argparse.Namespace) -> int:
    print_json({"success": True, "compiler": detect_compiler(args.compiler)})
    return 0


def command_render(args: argparse.Namespace) -> int:
    templates_dir = Path(args.templates_dir).resolve() if args.templates_dir else find_default_templates_dir()
    output_dir = Path(args.output_dir).expanduser().resolve()
    result = render_tex(Path(args.data_json).expanduser().resolve(), args.template_id, output_dir, templates_dir)
    compiler = detect_compiler(args.compiler)
    result["compiler"] = compiler
    result["templatesDir"] = str(templates_dir)

    if args.no_compile:
        result["compiler"]["message"] = "已按要求仅生成 .tex，未尝试编译 PDF。"
        print_json(result)
        return 0

    if not compiler.get("available"):
        result["missingCompiler"] = True
        print_json(result)
        return 0

    compile_result = compile_pdf(Path(result["texPath"]), compiler)
    result.update(compile_result)
    print_json(result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render resume JSON with LaTeX Jinja2 templates")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_list = subparsers.add_parser("list", help="List available LaTeX templates")
    p_list.add_argument("--templates-dir", default=None)
    p_list.set_defaults(func=command_list)

    p_status = subparsers.add_parser("status", help="Detect available LaTeX compiler")
    p_status.add_argument("--compiler", default=None, help="Prefer one compiler name")
    p_status.set_defaults(func=command_status)

    p_render = subparsers.add_parser("render", help="Render a resume JSON file to .tex and optional PDF")
    p_render.add_argument("data_json")
    p_render.add_argument("template_id")
    p_render.add_argument("output_dir")
    p_render.add_argument("--templates-dir", default=None)
    p_render.add_argument("--compiler", default=None)
    p_render.add_argument("--no-compile", action="store_true")
    p_render.set_defaults(func=command_render)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print_json({"success": False, "error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
