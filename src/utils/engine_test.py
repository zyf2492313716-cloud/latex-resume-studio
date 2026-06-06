"""
engine_test.py - Unit tests for template_engine.py

11 test cases covering core modes, fallback, and edge cases.
Run: python3 -m unittest src/utils/engine_test.py
"""

import os
import sys
import json
import tempfile
import unittest
import zipfile
import base64
import copy
import hashlib
import io

# Ensure src/utils is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lxml import etree as ET
from PIL import Image, ImageDraw
from template_engine import TemplateEngine, fill, fill_with_fallback
from photo_replace import inspect_photo_candidates

NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, 'templates')
EXTERNAL_TEMPLATES_DIR = '/Users/zhouyufeng/Downloads/1 单页简历'
FALLBACK_TEMPLATES_DIR = EXTERNAL_TEMPLATES_DIR if os.path.isdir(EXTERNAL_TEMPLATES_DIR) else TEMPLATES_DIR

TEST_DATA = {
    "basicInfo": {
        "name": "周煜峰",
        "title": "预防医学",
        "phone": "15212171672",
        "email": "21301020019@m.fudan.edu.cn",
        "wechat": "",
        "github": "",
        "summary": "已获保研资格。复旦大学预防医学2026届本科。"
    },
    "education": [
        {"school": "复旦大学", "major": "预防医学", "degree": "本科", "date": "2021.09-2026.06", "description": "GPA 3.20"}
    ],
    "experience": [
        {"company": "上海市疾病预防控制中心", "role": "实习生", "date": "2025.10-2026.01", "description": "公共卫生数据处理"}
    ],
    "projects": [],
    "research": [],
    "studentWork": [],
    "honors": ["校三等奖学金（3次）"],
    "skills": ["Python/R/STATA"]
}

DEFAULT_LEAK_PATTERNS = [
    '钟小艾', '林晓歌', '乔彬', '乔 彬', '幼儿教师', '财务会计', '华南师范', '湖北十堰大学',
    '深圳科技网络公司', '英语培训机构', '2012.09-2016.05', '2014.07-2015.09',
    '2012/6一至今', '2013.8一2014.6', '2015.6一2016.6', '180-5505-0900',
    '138-8888-8888', '13888123@qq.com', 'Xiaowangzi', '广东省深圳市', '海珠区',
    '滨江东路', '产品运营总监', '教育学（本科）'
]


def get_docx_texts(docx_path):
    """Extract all non-empty text nodes from a docx file."""
    with zipfile.ZipFile(docx_path, 'r') as z:
        doc_xml = z.read('word/document.xml').decode('utf-8')
    root = ET.fromstring(doc_xml.encode('utf-8'))
    texts = []
    for t in root.iter(f'{{{NS}}}t'):
        txt = (t.text or '').strip()
        if txt:
            texts.append(txt)
    return texts


def assert_no_default_leaks(testcase, docx_path):
    joined = ''.join(get_docx_texts(docx_path))
    leaks = [p for p in DEFAULT_LEAK_PATTERNS if p in joined]
    testcase.assertEqual(leaks, [], f'default template text leaked into output: {leaks}')


def inspect_docx_structure(docx_path):
    with zipfile.ZipFile(docx_path, 'r') as z:
        doc_xml = z.read('word/document.xml').decode('utf-8')
    root = ET.fromstring(doc_xml.encode('utf-8'))
    literal_newline_count = sum(1 for t in root.iter(f'{{{NS}}}t') if '\n' in (t.text or ''))
    br_count = len(list(root.iter(f'{{{NS}}}br')))
    return literal_newline_count, br_count


def make_test_photo_data_url():
    """Create an asymmetric portrait image so crop/resize bugs are visible."""
    image = Image.new('RGB', (420, 600), '#1d4ed8')
    draw = ImageDraw.Draw(image)
    draw.rectangle((18, 18, 402, 582), outline='white', width=10)
    draw.ellipse((145, 76, 275, 206), fill='#facc15')
    draw.rectangle((118, 260, 302, 548), fill='#f97316')
    draw.polygon([(210, 26), (238, 68), (182, 68)], fill='#22c55e')
    buf = io.BytesIO()
    image.save(buf, format='JPEG', quality=92)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


def actual_photo_template_path(template_path):
    docxtpl_path = template_path.replace('.docx', '.docxtpl.docx')
    if os.path.exists(docxtpl_path):
        return docxtpl_path
    return template_path


class TestTemplateEngine(unittest.TestCase):

    def test_label_inline_basic(self):
        """label_inline with colon separator (e.g. '手机：138...')."""
        config = {
            "basic_info": {
                "fields": {
                    "phone": {"type": "label_inline", "pattern": "手机"}
                }
            },
            "sections": {}
        }
        engine = TemplateEngine(
            os.path.join(FALLBACK_TEMPLATES_DIR, '简约单页01.docx'),
            config
        )
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
            out = f.name
        result = engine.fill(TEST_DATA, out)
        self.assertTrue(result)
        texts = get_docx_texts(out)
        self.assertTrue(any('15212171672' in t for t in texts))
        os.unlink(out)

    def test_label_inline_no_colon(self):
        """label_inline fallback when no colon separator found."""
        config = {
            "basic_info": {
                "fields": {
                    "name": {"type": "keyword_scan", "keywords": ["宋艾嘉"], "value_scope": "keyword_substring"}
                }
            },
            "sections": {}
        }
        engine = TemplateEngine(
            os.path.join(FALLBACK_TEMPLATES_DIR, '极简单页01.docx'),
            config
        )
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
            out = f.name
        result = engine.fill(TEST_DATA, out)
        self.assertTrue(result)
        texts = get_docx_texts(out)
        self.assertTrue(any('周煜峰' in t for t in texts))
        os.unlink(out)

    def test_label_adjacent_same_para(self):
        """label_adjacent: label in one w:t, value in next w:t (same paragraph)."""
        config = {
            "basic_info": {
                "fields": {
                    "phone": {"type": "label_adjacent", "pattern": "手机"}
                }
            },
            "sections": {}
        }
        engine = TemplateEngine(
            os.path.join(FALLBACK_TEMPLATES_DIR, '知页简历01.docx'),
            config
        )
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
            out = f.name
        result = engine.fill(TEST_DATA, out)
        self.assertTrue(result)
        texts = get_docx_texts(out)
        self.assertTrue(any('15212171672' in t for t in texts))
        os.unlink(out)

    def test_label_adjacent_cross_para(self):
        """label_adjacent: label in paragraph N, value in paragraph N+1..N+3."""
        config = {
            "basic_info": {
                "fields": {
                    "phone": {"type": "label_adjacent", "pattern": "电话"}
                }
            },
            "sections": {}
        }
        engine = TemplateEngine(
            os.path.join(FALLBACK_TEMPLATES_DIR, '极简单页01.docx'),
            config
        )
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
            out = f.name
        result = engine.fill(TEST_DATA, out)
        self.assertTrue(result)
        texts = get_docx_texts(out)
        self.assertTrue(any('15212171672' in t for t in texts))
        os.unlink(out)

    def test_section_replace(self):
        """section_replace: replace content after section header."""
        config = {
            "basic_info": {"fields": {}},
            "sections": {
                "honors": {
                    "header": "证书奖励",
                    "type": "section_replace"
                }
            }
        }
        engine = TemplateEngine(
            os.path.join(FALLBACK_TEMPLATES_DIR, '简约单页01.docx'),
            config
        )
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
            out = f.name
        result = engine.fill(TEST_DATA, out)
        self.assertTrue(result)
        texts = get_docx_texts(out)
        self.assertTrue(any('校三等奖学金' in t for t in texts))
        os.unlink(out)

    def test_keyword_scan_substring(self):
        """keyword_scan with value_scope=keyword_substring expands to word boundaries."""
        config = {
            "basic_info": {
                "fields": {
                    "name": {"type": "keyword_scan", "keywords": ["肖颖馨"], "value_scope": "keyword_substring"}
                }
            },
            "sections": {}
        }
        engine = TemplateEngine(
            os.path.join(FALLBACK_TEMPLATES_DIR, '稳重单页01.docx'),
            config
        )
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
            out = f.name
        result = engine.fill(TEST_DATA, out)
        self.assertTrue(result)
        texts = get_docx_texts(out)
        self.assertTrue(any('周煜峰' in t for t in texts))
        os.unlink(out)

    def test_keyword_scan_full_node(self):
        """keyword_scan with value_scope=full_node replaces entire text node."""
        config = {
            "basic_info": {
                "fields": {
                    "name": {"type": "keyword_scan", "keywords": ["宋艾嘉"], "value_scope": "full_node"}
                }
            },
            "sections": {}
        }
        engine = TemplateEngine(
            os.path.join(FALLBACK_TEMPLATES_DIR, '极简单页01.docx'),
            config
        )
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
            out = f.name
        result = engine.fill(TEST_DATA, out)
        self.assertTrue(result)
        texts = get_docx_texts(out)
        self.assertTrue(any('周煜峰' in t for t in texts))
        os.unlink(out)

    def test_multi_node_name(self):
        """Name split across multiple w:t nodes (e.g. '陈' + '知页')."""
        config = {
            "basic_info": {
                "fields": {
                    "name": {"type": "keyword_scan", "keywords": ["陈知页"], "value_scope": "full_node"}
                }
            },
            "sections": {}
        }
        engine = TemplateEngine(
            os.path.join(FALLBACK_TEMPLATES_DIR, '知页简历01.docx'),
            config
        )
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
            out = f.name
        result = engine.fill(TEST_DATA, out)
        self.assertTrue(result)
        os.unlink(out)

    def test_v2_fallback(self):
        """Template without YAML config falls back to v2 filler."""
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
            out = f.name
        result = fill_with_fallback(
            os.path.join(FALLBACK_TEMPLATES_DIR, '简约单页01.docx'),
            TEST_DATA, out
        )
        self.assertTrue(result)
        texts = get_docx_texts(out)
        self.assertTrue(any('周煜峰' in t for t in texts))
        os.unlink(out)

    def test_section_failure_graceful(self):
        """Section header not found should warn but not crash."""
        config = {
            "basic_info": {"fields": {}},
            "sections": {
                "honors": {
                    "header": "不存在的板块标题",
                    "type": "section_replace"
                }
            }
        }
        engine = TemplateEngine(
            os.path.join(FALLBACK_TEMPLATES_DIR, '简约单页01.docx'),
            config
        )
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
            out = f.name
        result = engine.fill(TEST_DATA, out)
        # Should not crash, warnings should be collected
        self.assertGreater(len(engine.warnings), 0)
        os.unlink(out)

    def test_empty_data(self):
        """Empty data should produce output without errors."""
        config = {
            "basic_info": {
                "fields": {
                    "name": {"type": "keyword_scan", "keywords": ["宋艾嘉"], "value_scope": "full_node"}
                }
            },
            "sections": {}
        }
        engine = TemplateEngine(
            os.path.join(FALLBACK_TEMPLATES_DIR, '极简单页01.docx'),
            config
        )
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
            out = f.name
        result = engine.fill({}, out)
        # Should not crash
        self.assertTrue(os.path.exists(out))
        os.unlink(out)

    def test_spatial_fill(self):
        """Test Level 2.5 spatial engine fallback (when no YAML configuration is present)."""
        import shutil
        temp_dir = tempfile.mkdtemp()
        try:
            # Copy minimalist template to temp directory with a new name, so no YAML file exists near it
            src_template = os.path.join(FALLBACK_TEMPLATES_DIR, '简约单页01.docx')
            test_template = os.path.join(temp_dir, 'no_yaml_template.docx')
            shutil.copy2(src_template, test_template)

            out_docx = os.path.join(temp_dir, 'output.docx')

            # Fill using fallback router
            result = fill_with_fallback(test_template, TEST_DATA, out_docx)
            self.assertTrue(result)

            # Verify data exists in filled template
            texts = get_docx_texts(out_docx)
            self.assertTrue(any('周煜峰' in t for t in texts))
            self.assertTrue(any('15212171672' in t for t in texts))
            self.assertTrue(any('复旦大学' in t for t in texts))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_photo_replacement_representative_templates(self):
        """Uploaded portrait replaces likely photo placeholders without breaking text/XML."""
        templates = ['文艺单页01', '文艺单页02', '文艺单页03', '文艺单页04', '文艺单页07', '简约单页01', '活泼单页12']
        data = copy.deepcopy(TEST_DATA)
        data['basicInfo']['photo'] = make_test_photo_data_url()
        data['education'][0]['description'] = 'GPA 3.20\n核心课程：卫生统计学'

        for template_name in templates:
            with self.subTest(template=template_name):
                template_path = os.path.join(TEMPLATES_DIR, template_name + '.docx')
                self.assertTrue(os.path.exists(template_path), f'missing template: {template_path}')

                source_for_media = actual_photo_template_path(template_path)
                candidates = inspect_photo_candidates(source_for_media)
                self.assertTrue(candidates, f'no image candidates for {template_name}')
                candidate = candidates[0]
                self.assertGreaterEqual(candidate['score'], 30)

                with zipfile.ZipFile(source_for_media, 'r') as z:
                    before_hash = hashlib.sha1(z.read(candidate['media_path'])).hexdigest()

                with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
                    out = f.name
                try:
                    result = fill_with_fallback(template_path, data, out)
                    self.assertTrue(result)

                    texts = get_docx_texts(out)
                    self.assertTrue(any('周煜峰' in t for t in texts))
                    self.assertTrue(any('15212171672' in t for t in texts))
                    assert_no_default_leaks(self, out)

                    literal_newline_count, _br_count = inspect_docx_structure(out)
                    self.assertEqual(literal_newline_count, 0)

                    with zipfile.ZipFile(out, 'r') as z:
                        after_bytes = z.read(candidate['media_path'])
                    after_hash = hashlib.sha1(after_bytes).hexdigest()
                    self.assertNotEqual(before_hash, after_hash)

                    after_candidates = inspect_photo_candidates(out)
                    after_by_path = {c['media_path']: c for c in after_candidates}
                    self.assertIn(candidate['media_path'], after_by_path)
                    self.assertGreaterEqual(after_by_path[candidate['media_path']]['width'], 80)
                    self.assertGreaterEqual(after_by_path[candidate['media_path']]['height'], 80)
                finally:
                    os.unlink(out)
    def test_problem_templates_do_not_leak_defaults_with_blank_title(self):
        """Visible template defaults must be removed even when the user leaves title blank."""
        data = copy.deepcopy(TEST_DATA)
        data['basicInfo']['title'] = ''
        data['education'][0]['description'] = 'GPA 3.20/4.0，专业排名43/99，已获保研资格'
        data['experience'][0]['description'] = '参与公共卫生数据处理与监测分析，协助完成报告撰写'

        for template_name in ['文艺单页03', '文艺单页04']:
            with self.subTest(template=template_name):
                template_path = os.path.join(TEMPLATES_DIR, template_name + '.docx')
                with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
                    out = f.name
                try:
                    self.assertTrue(fill_with_fallback(template_path, data, out))
                    texts = get_docx_texts(out)
                    joined = ''.join(texts)
                    self.assertIn('周煜峰', joined)
                    self.assertIn('15212171672', joined)
                    self.assertIn('复旦大学', joined)
                    self.assertIn('上海市疾病预防控制中心', joined)
                    self.assertNotIn('求职意向：财务会计', joined)
                    assert_no_default_leaks(self, out)
                finally:
                    os.unlink(out)


if __name__ == '__main__':
    unittest.main()
