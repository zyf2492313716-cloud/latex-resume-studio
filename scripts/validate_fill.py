#!/usr/bin/env python3
"""
validate_fill.py - Full validation of all 103 resume templates.

For each .docx template:
  - If .yaml exists → use template_engine
  - If no .yaml → use v2 fallback
  - Check output for 5 key fields: name, phone, school, company, summary

Usage:
  python3 scripts/validate_fill.py                    # validate all templates
  python3 scripts/validate_fill.py --template 简约单页01  # validate single template

Output: CSV to stdout
"""

import os
import sys
import csv
import argparse
import tempfile
import zipfile
import base64
import hashlib
import io

# Add src/utils to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'utils'))

from lxml import etree as ET
from PIL import Image, ImageDraw
from photo_replace import inspect_photo_candidates

NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), '..', 'templates')
FALLBACK_TEMPLATES_DIR = '/Users/zhouyufeng/Downloads/1 单页简历'
PHOTO_REQUIRED_TEMPLATES = {'文艺单页01', '文艺单页02', '文艺单页03', '文艺单页04', '文艺单页07', '简约单页01', '活泼单页12'}
STRICT_DEFAULT_TEMPLATES = PHOTO_REQUIRED_TEMPLATES


def make_test_photo_data_url():
    image = Image.new('RGB', (420, 600), '#1d4ed8')
    draw = ImageDraw.Draw(image)
    draw.rectangle((18, 18, 402, 582), outline='white', width=10)
    draw.ellipse((145, 76, 275, 206), fill='#facc15')
    draw.rectangle((118, 260, 302, 548), fill='#f97316')
    draw.polygon([(210, 26), (238, 68), (182, 68)], fill='#22c55e')
    buf = io.BytesIO()
    image.save(buf, format='JPEG', quality=92)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


TEST_DATA = {
    "basicInfo": {
        "name": "周煜峰",
        "title": "预防医学",
        "phone": "15212171672",
        "email": "21301020019@m.fudan.edu.cn",
        "wechat": "",
        "github": "",
        "summary": "已获保研资格。复旦大学预防医学2026届本科，掌握数据分析与跨学科研究能力。",
        "photo": make_test_photo_data_url()
    },
    "education": [{
        "school": "复旦大学",
        "major": "预防医学",
        "degree": "本科",
        "date": "2021.09-2026.06",
        "description": "GPA 3.20/4.0，专业排名43/99，已获保研资格\n核心课程：有机化学(A)、生物化学(A)、儿科学(A)、卫生统计学(A-)\n德国汉堡大学健康经济学暑期学校（2024.07-2024.08）"
    }],
    "experience": [
        {"company": "上海市疾病预防控制中心", "role": "实习生", "date": "2025.10-2026.01", "description": "参与公共卫生数据处理与监测分析，协助完成报告撰写"},
        {"company": "上海市第五人民医院", "role": "临床实习", "date": "2024.09-2025.01", "description": "轮转内科、外科、儿科等科室，参与临床诊疗工作"}
    ],
    "projects": [
        {"name": "第十届全国大学生统计建模大赛", "role": "", "date": "2024.03-2024.07", "description": "运用Python/SPSS进行数据采集、建模与分析，撰写统计建模报告"}
    ],
    "research": [
        {"name": "德隆学者科研项目", "role": "项目负责人", "date": "2022.05-2023.05", "description": "整合超2000份职业健康检查数据，利用STATA/R分析职业暴露与健康指标关联性"},
        {"name": "射阳出生队列数据采集与处理", "role": "", "date": "2023.05-2023.10", "description": "负责现场数据采集、问卷整理及数据库维护，使用SPSS进行数据清洗与统计分析"},
        {"name": "上海市控烟暗访项目", "role": "控烟暗访员", "date": "2022.09-2022.12", "description": "参与实地调研，收集公共场所控烟执行情况数据"}
    ],
    "studentWork": [
        {"organization": "复旦大学学生会枫林办公室权益部", "role": "副部长", "date": "2021-2023", "description": "从事权益服务两年余，负责提案收集与反馈"},
        {"organization": "青年研究中心调研专报部", "role": "研究助理", "date": "", "description": ""},
        {"organization": "TLS社团项目组织部", "role": "部长", "date": "", "description": ""}
    ],
    "honors": ["校三等奖学金（3次）", "校优秀共青团员（2次）", "上海市科普大赛优秀奖", "普译奖翻译大赛上海三等奖"],
    "skills": ["Python", "R", "STATA", "SPSS", "Office", "英语CET-6 470/雅思6.0"]
}

PLACEHOLDER_NAMES = [
    '宋艾嘉', '肖颖馨', '韩志弘', '李自强', '张三', '李四', '王五', '陈知页', '朱七七',
    '关睢尔', '白晓云', '孟子君', '孟晓思', '关月兰', '钟小艾', '林晓歌', '乔彬', '乔 彬'
]

DEFAULT_LEAK_PATTERNS = [
    '幼儿教师', '财务会计', '华南师范', '湖北十堰大学', '深圳科技网络公司', '英语培训机构',
    '2012.09-2016.05', '2014.07-2015.09', '2012/6一至今', '2013.8一2014.6', '2015.6一2016.6',
    '180-5505-0900', '138-8888-8888', '13888888888', '13888123@qq.com', 'Xiaowangzi',
    '广东省深圳市', '海珠区', '滨江东路', '产品运营总监', '教育学（本科）'
]


def inspect_docx(docx_path):
    """Extract text and structural health signals from a docx file."""
    try:
        with zipfile.ZipFile(docx_path, 'r') as z:
            doc_xml = z.read('word/document.xml').decode('utf-8')
        root = ET.fromstring(doc_xml.encode('utf-8'))
        texts = []
        literal_newline_count = 0
        for t in root.iter(f'{{{NS}}}t'):
            txt = (t.text or '').strip()
            if '\n' in (t.text or ''):
                literal_newline_count += 1
            if txt:
                texts.append(txt)
        joined = ''.join(texts)
        return {
            'texts': texts,
            'literal_newline_count': literal_newline_count,
            'br_count': len(list(root.iter(f'{{{NS}}}br'))),
            'placeholder_hits': [p for p in PLACEHOLDER_NAMES if p in joined],
            'default_hits': [p for p in DEFAULT_LEAK_PATTERNS if p in joined],
        }
    except Exception:
        return {'texts': [], 'literal_newline_count': -1, 'br_count': 0, 'placeholder_hits': [], 'default_hits': []}


def get_docx_texts(docx_path):
    """Extract all non-empty text from a docx file."""
    return inspect_docx(docx_path)['texts']


def detect_sections(texts):
    """Detect which section types are present in the template based on header text."""
    section_headers = {
        'education': ['教育背景', '教育经历', '教育背景EDUCATION'],
        'experience': ['工作经历', '工作经验', '实习经历', '工作经历JOB EXPERIENCE'],
        'honors': ['证书奖励', '荣誉证书', '荣誉奖项', '个人荣誉', '获奖经历', '奖项荣誉', '资格证书'],
        'summary': ['自我评价', '个人介绍', '个人简介', '个人总结'],
        'skills': ['专业技能', '职业技能', '掌握技能', '技能SKILLS'],
        'studentWork': ['校内实践', '在校经历', '社团经历', '学生工作'],
    }
    found = []
    for sec, headers in section_headers.items():
        if any(h in ' '.join(texts) for h in headers):
            found.append(sec)
    return found


def check_field(texts, field_type):
    """Check if a field value appears in the output texts."""
    checks = {
        'name': lambda: any('周煜峰' in t for t in texts),
        'title': lambda: any('预防医学' in t for t in texts),
        'phone': lambda: any('15212171672' in t for t in texts),
        'email': lambda: any('21301020019@m.fudan.edu.cn' in t for t in texts),
        'school': lambda: any('复旦大学' in t for t in texts),
        'company': lambda: any('疾病预防控制中心' in t for t in texts),
        'summary': lambda: any('保研' in t or '预防医学2026' in t for t in texts),
    }
    try:
        return checks.get(field_type, lambda: False)()
    except Exception:
        return False


def find_template_path(template_name):
    """Find the .docx file for a template by name."""
    # Try exact match in YAML templates dir
    for ext in ['.docx']:
        path = os.path.join(TEMPLATES_DIR, template_name + ext)
        if os.path.exists(path):
            return path
    # Try fallback templates dir
    for ext in ['.docx']:
        path = os.path.join(FALLBACK_TEMPLATES_DIR, template_name + ext)
        if os.path.exists(path):
            return path
    return None


def actual_photo_template_path(template_path):
    docxtpl_path = template_path.replace('.docx', '.docxtpl.docx')
    if os.path.exists(docxtpl_path):
        return docxtpl_path
    return template_path


def media_sha1(docx_path, media_path):
    try:
        with zipfile.ZipFile(docx_path, 'r') as z:
            return hashlib.sha1(z.read(media_path)).hexdigest()
    except Exception:
        return ''


def validate_single(template_name):
    """Validate a single template. Returns dict with results."""
    from template_engine import fill_with_fallback

    template_path = find_template_path(template_name)
    if not template_path:
        return {
            'template_name': template_name,
            'engine_type': 'N/A',
            'sections': '',
            'name': False, 'title': False, 'phone': False, 'email': False,
            'school': False, 'company': False, 'summary': False,
            'literal_newline_count': -1, 'br_count': 0, 'placeholder_hits': '', 'default_hits': '',
            'photo_replaced': False, 'photo_target': '',
            'issues': 'template_not_found',
            'score': 0, 'status': 'TEMPLATE_NOT_FOUND'
        }

    config_path = template_path.replace('.docx', '.yaml')
    has_yaml = os.path.exists(config_path)
    engine_type = 'engine' if has_yaml else 'v2'

    photo_target = ''
    photo_before_hash = ''
    try:
        photo_candidates = inspect_photo_candidates(actual_photo_template_path(template_path))
        if photo_candidates and photo_candidates[0].get('score', 0) >= 30:
            photo_target = photo_candidates[0]['media_path']
            photo_before_hash = media_sha1(actual_photo_template_path(template_path), photo_target)
    except Exception:
        photo_target = ''
        photo_before_hash = ''

    with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
        out_path = f.name

    try:
        fill_with_fallback(template_path, TEST_DATA, out_path)
        inspection = inspect_docx(out_path)
        texts = inspection['texts']
        sections = detect_sections(texts)

        results = {}
        for field in ['name', 'title', 'phone', 'email', 'school', 'company', 'summary']:
            results[field] = check_field(texts, field)

        issues = []
        if not results['title']:
            issues.append('missing_title')
        if not results['email']:
            issues.append('missing_email')
        if inspection['literal_newline_count'] > 0:
            issues.append(f"literal_newline:{inspection['literal_newline_count']}")
        if inspection['placeholder_hits']:
            issues.append('placeholder:' + '|'.join(inspection['placeholder_hits']))
        if inspection.get('default_hits') and template_name in STRICT_DEFAULT_TEMPLATES:
            issues.append('default_leak:' + '|'.join(inspection['default_hits']))

        photo_after_hash = media_sha1(out_path, photo_target) if photo_target else ''
        photo_replaced = bool(photo_target and photo_before_hash and photo_after_hash and photo_before_hash != photo_after_hash)
        if template_name in PHOTO_REQUIRED_TEMPLATES and not photo_replaced:
            issues.append('photo_not_replaced')

        # Score based on the original five key fields and sections the template actually has
        score = 0
        score += 1 if results['name'] else 0
        score += 1 if results['phone'] else 0
        if 'education' in sections:
            score += 1 if results['school'] else 0
        else:
            score += 1  # N/A
        if 'experience' in sections:
            score += 1 if results['company'] else 0
        else:
            score += 1  # N/A
        if 'summary' in sections:
            score += 1 if results['summary'] else 0
        else:
            score += 1  # N/A

        if score < 4:
            status = 'FAIL'
        elif issues:
            status = 'WARN'
        else:
            status = 'OK'

        return {
            'template_name': template_name,
            'engine_type': engine_type,
            'sections': '|'.join(sections),
            'name': results['name'],
            'title': results['title'],
            'phone': results['phone'],
            'email': results['email'],
            'school': results['school'],
            'company': results['company'],
            'summary': results['summary'],
            'literal_newline_count': inspection['literal_newline_count'],
            'br_count': inspection['br_count'],
            'placeholder_hits': '|'.join(inspection['placeholder_hits']),
            'default_hits': '|'.join(inspection.get('default_hits', [])),
            'photo_replaced': photo_replaced,
            'photo_target': photo_target,
            'issues': ';'.join(issues),
            'score': score,
            'status': status
        }
    except Exception as e:
        return {
            'template_name': template_name,
            'engine_type': engine_type,
            'sections': '',
            'name': False, 'title': False, 'phone': False, 'email': False,
            'school': False, 'company': False, 'summary': False,
            'literal_newline_count': -1, 'br_count': 0, 'placeholder_hits': '', 'default_hits': '',
            'photo_replaced': False, 'photo_target': '',
            'issues': str(e),
            'score': 0, 'status': f'ERROR:{e}'
        }
    finally:
        try:
            os.unlink(out_path)
        except Exception:
            pass


def get_all_template_names():
    """Get all template names from both directories."""
    names = set()
    # From YAML templates dir (these have configs)
    if os.path.isdir(TEMPLATES_DIR):
        for f in os.listdir(TEMPLATES_DIR):
            if f.endswith('.docx') and '.marked.' not in f and '.docxtpl.' not in f:
                names.add(f.replace('.docx', ''))
    # From fallback dir
    if os.path.isdir(FALLBACK_TEMPLATES_DIR):
        for f in os.listdir(FALLBACK_TEMPLATES_DIR):
            if f.endswith('.docx') and '.marked.' not in f and '.docxtpl.' not in f:
                names.add(f.replace('.docx', ''))
    return sorted(names)


def main():
    parser = argparse.ArgumentParser(description='Validate resume template filling')
    parser.add_argument('--template', type=str, help='Validate a single template by name')
    parser.add_argument('--json', action='store_true', help='Output as JSON instead of CSV')
    args = parser.parse_args()

    if args.template:
        names = [args.template]
    else:
        names = get_all_template_names()

    results = []
    for name in names:
        result = validate_single(name)
        results.append(result)

    if args.json:
        import json
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=[
            'template_name', 'engine_type', 'sections',
            'name', 'title', 'phone', 'email', 'school', 'company', 'summary',
            'literal_newline_count', 'br_count', 'placeholder_hits', 'default_hits', 'photo_replaced', 'photo_target', 'issues', 'score', 'status'
        ])
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    # Print summary to stderr
    total = len(results)
    engine_count = sum(1 for r in results if r['engine_type'] == 'engine')
    v2_count = sum(1 for r in results if r['engine_type'] == 'v2')
    score_4_plus = sum(1 for r in results if r['score'] >= 4)
    clean_count = sum(1 for r in results if r['score'] >= 4 and not r.get('issues'))
    issue_count = sum(1 for r in results if r.get('issues'))
    avg_score = sum(r['score'] for r in results) / total if total else 0

    print(f"\n=== Validation Summary ===", file=sys.stderr)
    print(f"Total templates: {total}", file=sys.stderr)
    print(f"Engine (YAML):   {engine_count}", file=sys.stderr)
    print(f"V2 fallback:     {v2_count}", file=sys.stderr)
    print(f"Score >= 4/5:    {score_4_plus} ({score_4_plus*100//total}%)", file=sys.stderr)
    print(f"Clean outputs:   {clean_count} ({clean_count*100//total}%)", file=sys.stderr)
    print(f"Issue outputs:   {issue_count}", file=sys.stderr)
    print(f"Average score:   {avg_score:.1f}/5", file=sys.stderr)

    # Count by score
    for score in [5, 4, 3, 2, 1, 0]:
        count = sum(1 for r in results if r['score'] == score)
        if count:
            print(f"  {score}/5: {count} templates", file=sys.stderr)

    if args.template:
        sys.exit(0 if results and results[0]['score'] >= 4 and not results[0].get('issues') else 1)
    sys.exit(0 if score_4_plus == total and issue_count == 0 else 1)


if __name__ == '__main__':
    main()
