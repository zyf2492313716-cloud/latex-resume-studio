#!/usr/bin/env python3
"""Validate full coverage for the real 周煜峰 resume fixture.

The high-match LaTeX templates are expected to preserve every key resume fact.
This catches regressions that the general DOCX smoke test intentionally misses.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "src" / "utils" / "latex_renderer.py"
FIXTURE = ROOT / "fixtures" / "zhou_yufeng_resume.json"

TEMPLATE_IDS = ["jakes-ats", "modern-clean"]

KEY_PHRASES = [
    "周煜峰",
    "15212171672",
    "21301020019@m.fudan.edu.cn",
    "复旦大学",
    "预防医学",
    "GPA 3.20/4.0",
    "专业排名43/99",
    "已获保研资格",
    "德国汉堡大学健康经济学暑期学校",
    "上海市疾病预防控制中心",
    "上海市第五人民医院",
    "第十届全国大学生统计建模大赛",
    "Python/SPSS",
    "德隆学者科研项目",
    "超2000份职业健康检查数据",
    "STATA/R",
    "射阳出生队列数据采集与处理",
    "上海市控烟暗访项目",
    "复旦大学学生会枫林办公室权益部",
    "青年研究中心调研专报部",
    "TLS社团项目组织部",
    "医路相伴老少结对共绘老年友好社会实践",
    "校三等奖学金",
    "校优秀共青团员",
    "上海市科普大赛优秀奖",
    "普译奖翻译大赛上海三等奖",
    "Python",
    "R",
    "STATA",
    "SPSS",
    "Office",
    "CET-6",
    "雅思6.0",
]


def run_json(cmd: List[str]) -> Dict[str, Any]:
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {"success": False, "error": "stdout is not JSON", "stdout": proc.stdout}
    payload["returncode"] = proc.returncode
    if proc.stderr:
        payload["stderr"] = proc.stderr
    return payload


def normalize_tex_text(value: str) -> str:
    return (
        value.replace(r"\&", "&")
        .replace(r"\%", "%")
        .replace(r"\$", "$ ")
        .replace(r"\#", "#")
        .replace(r"\_", "_")
        .replace(r"\{", "{")
        .replace(r"\}", "}")
        .replace(" ", "")
    )


def validate_template(template_id: str, output_dir: Path) -> Dict[str, Any]:
    result = run_json([sys.executable, str(RENDERER), "render", str(FIXTURE), template_id, str(output_dir), "--no-compile"])
    tex_path = Path(result.get("texPath") or "") if result.get("texPath") else None
    content = ""
    if tex_path and tex_path.exists():
      content = normalize_tex_text(tex_path.read_text(encoding="utf-8"))
    missing = [phrase for phrase in KEY_PHRASES if phrase.replace(" ", "") not in content]
    ok = bool(result.get("success")) and result.get("returncode") == 0 and tex_path and tex_path.exists() and not missing
    return {
        "templateId": template_id,
        "ok": ok,
        "texPath": str(tex_path) if tex_path else "",
        "missing": missing,
        "result": result,
    }


def main() -> int:
    output_dir = Path(tempfile.mkdtemp(prefix="zhou_yufeng_resume_coverage_"))
    validations = [validate_template(template_id, output_dir) for template_id in TEMPLATE_IDS]
    payload = {
        "success": all(item["ok"] for item in validations),
        "fixture": str(FIXTURE),
        "outputDir": str(output_dir),
        "templates": TEMPLATE_IDS,
        "validations": validations,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    shutil.rmtree(output_dir, ignore_errors=True)
    return 0 if payload["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
