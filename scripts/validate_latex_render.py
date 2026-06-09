#!/usr/bin/env python3
"""Validate LaTeX template discovery and .tex generation.

This script intentionally uses --no-compile so it can run on machines without a
local LaTeX distribution. PDF compilation is covered by src/utils/latex_renderer.py
when tectonic/xelatex/lualatex/latexmk is installed.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "src" / "utils" / "latex_renderer.py"
FIXTURE = ROOT / "fixtures" / "sample_resume.zh.json"
JINJA_TOKEN_RE = re.compile(
    r"\{%-?\s*(if|for|endif|endfor|include|else|elif)\b"
    r"|\{\{\s*-?\s*(basic|education|experience|projects|research|studentWork|skills|honors|sections|meta|loop|contact|bullet|item|e|p|r|s)\b"
)


def run_json(cmd: List[str]) -> Dict[str, Any]:
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {"success": False, "error": "stdout is not JSON", "stdout": proc.stdout, "stderr": proc.stderr}
    payload["returncode"] = proc.returncode
    if proc.stderr:
        payload["stderr"] = proc.stderr
    return payload


def validate_template(template_id: str, output_dir: Path) -> Dict[str, Any]:
    result = run_json([sys.executable, str(RENDERER), "render", str(FIXTURE), template_id, str(output_dir), "--no-compile"])
    tex_path = Path(result.get("texPath") or "") if result.get("texPath") else None
    checks = {
        "hasTexPath": bool(tex_path),
        "texExists": bool(tex_path and tex_path.exists()),
        "hasDocumentClass": False,
        "hasNoJinjaMarkers": False,
    }
    if tex_path and tex_path.exists():
        content = tex_path.read_text(encoding="utf-8")
        checks["hasDocumentClass"] = "\\documentclass" in content
        checks["hasNoJinjaMarkers"] = not JINJA_TOKEN_RE.search(content)
    ok = bool(result.get("success")) and result.get("returncode") == 0 and all(checks.values())
    return {"templateId": template_id, "ok": ok, "checks": checks, "result": result}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate LaTeX renderer/template smoke tests")
    parser.add_argument("--template", action="append", help="Template ID to validate; repeatable. Defaults to all discovered templates.")
    parser.add_argument("--keep-output", action="store_true", help="Keep generated .tex output directory")
    args = parser.parse_args()

    list_result = run_json([sys.executable, str(RENDERER), "list"])
    templates = list_result.get("templates") or []
    template_ids = args.template or [item.get("id") or item.get("name") for item in templates]
    template_ids = [item for item in template_ids if item]

    temp_dir = Path(tempfile.mkdtemp(prefix="resume_latex_validate_"))
    validations = [validate_template(template_id, temp_dir) for template_id in template_ids]
    all_ok = bool(list_result.get("success")) and bool(template_ids) and all(item["ok"] for item in validations)

    payload = {
        "success": all_ok,
        "root": str(ROOT),
        "renderer": str(RENDERER),
        "fixture": str(FIXTURE),
        "outputDir": str(temp_dir),
        "templateCount": len(template_ids),
        "listResult": list_result,
        "validations": validations,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if not args.keep_output:
        shutil.rmtree(temp_dir, ignore_errors=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
