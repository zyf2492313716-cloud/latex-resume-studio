#!/usr/bin/env python3
"""Validate that LaTeX templates compile to PDF and macOS can thumbnail them."""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "zhou_yufeng_resume.json"
RENDERER = ROOT / "src" / "utils" / "latex_renderer.py"
TEMPLATES = ["awesome-accent", "deedy-two-column", "jakes-ats", "modern-clean"]


def run_renderer(template_id: str, output_dir: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, str(RENDERER), "render", str(FIXTURE), template_id, str(output_dir)],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {"success": False, "stdout": proc.stdout, "stderr": proc.stderr}
    payload["returncode"] = proc.returncode
    return payload


def make_thumbnail(pdf_path: Path, output_dir: Path) -> bool:
    if sys.platform != "darwin":
        return True
    qlmanage = Path("/usr/bin/qlmanage")
    if not qlmanage.exists():
        return False
    proc = subprocess.run(
        [str(qlmanage), "-t", "-s", "1600", "-o", str(output_dir), str(pdf_path)],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    return proc.returncode == 0 and any(output_dir.glob("*.png"))


def main() -> int:
    work_dir = Path(tempfile.mkdtemp(prefix="latex_preview_image_"))
    try:
        validations = []
        for template_id in TEMPLATES:
            template_dir = work_dir / template_id
            thumb_dir = work_dir / f"{template_id}_thumb"
            template_dir.mkdir(parents=True, exist_ok=True)
            thumb_dir.mkdir(parents=True, exist_ok=True)
            result = run_renderer(template_id, template_dir)
            pdf_path = Path(result.get("pdfPath") or "")
            compiled = bool(result.get("compiled") and pdf_path.exists())
            thumb_ok = compiled and make_thumbnail(pdf_path, thumb_dir)
            validations.append({
                "templateId": template_id,
                "compiled": compiled,
                "pdfPath": str(pdf_path) if compiled else None,
                "thumbnail": thumb_ok,
                "error": result.get("compileError") or result.get("error") or "",
            })

        ok = all(item["compiled"] and item["thumbnail"] for item in validations)
        print(json.dumps({
            "success": ok,
            "fixture": str(FIXTURE),
            "outputDir": str(work_dir),
            "validations": validations,
        }, ensure_ascii=False, indent=2))
        return 0 if ok else 1
    finally:
        if "RESUME_DEBUG_PREVIEW" not in __import__("os").environ:
            shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
