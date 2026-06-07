#!/usr/bin/env python3
"""Validate that LaTeX templates compile to PDF and macOS can thumbnail them."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "zhou_yufeng_resume.json"
RENDERER = ROOT / "src" / "utils" / "latex_renderer.py"
PHOTO_PNG_DATA_URL = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="


def discover_templates() -> list[str]:
    proc = subprocess.run(
        [sys.executable, str(RENDERER), "list"],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    payload = json.loads(proc.stdout)
    return [item.get("id") or item.get("name") for item in payload.get("templates", []) if item.get("id") or item.get("name")]


def make_photo_fixture(output_dir: Path) -> Path:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data.setdefault("basicInfo", {})["photo"] = PHOTO_PNG_DATA_URL
    fixture = output_dir / "zhou_yufeng_resume.with-photo.json"
    fixture.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return fixture


def run_renderer(template_id: str, output_dir: Path, fixture: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, str(RENDERER), "render", str(fixture), template_id, str(output_dir)],
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


def first_page_has_text(pdf_path: Path) -> tuple[bool, str]:
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        return True, ""
    try:
        proc = subprocess.run(
            [pdftotext, "-f", "1", "-l", "1", str(pdf_path), "-"],
            text=True,
            capture_output=True,
            check=False,
            timeout=45,
        )
    except subprocess.TimeoutExpired:
        return False, "pdftotext first-page check timed out"
    if proc.returncode != 0:
        return False, (proc.stderr or "pdftotext first-page check failed").strip()
    return bool(proc.stdout.replace("\f", "").strip()), ""


def main() -> int:
    work_dir = Path(tempfile.mkdtemp(prefix="latex_preview_image_"))
    try:
        validations = []
        templates = discover_templates()
        fixture = make_photo_fixture(work_dir)
        for template_id in templates:
            template_dir = work_dir / template_id
            thumb_dir = work_dir / f"{template_id}_thumb"
            template_dir.mkdir(parents=True, exist_ok=True)
            thumb_dir.mkdir(parents=True, exist_ok=True)
            result = run_renderer(template_id, template_dir, fixture)
            pdf_path = Path(result.get("pdfPath") or "")
            compiled = bool(result.get("compiled") and pdf_path.exists())
            thumb_ok = compiled and make_thumbnail(pdf_path, thumb_dir)
            first_page_ok, first_page_error = first_page_has_text(pdf_path) if compiled else (False, "")
            validations.append({
                "templateId": template_id,
                "compiled": compiled,
                "pdfPath": str(pdf_path) if compiled else None,
                "thumbnail": thumb_ok,
                "firstPageHasText": first_page_ok,
                "error": result.get("compileError") or result.get("error") or first_page_error,
            })

        ok = all(item["compiled"] and item["thumbnail"] and item["firstPageHasText"] for item in validations)
        print(json.dumps({
            "success": ok,
            "fixture": str(fixture),
            "outputDir": str(work_dir),
            "templateCount": len(templates),
            "validations": validations,
        }, ensure_ascii=False, indent=2))
        return 0 if ok else 1
    finally:
        if "RESUME_DEBUG_PREVIEW" not in os.environ:
            shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
