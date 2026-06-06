"""
template_engine.py - Configuration-driven resume template filler MVP.

5 core matching modes:
1. label_inline: label+value in same w:t node (e.g. "姓名：宋艾嘉")
2. label_adjacent: label in one w:t, value in next w:t (same or next paragraph)
3. keyword_scan: find keyword in text node, expand to word boundaries
4. section_replace: replace content paragraphs in a section
5. label_group: multiple labels followed by multiple values (e.g. 手机/微信/邮箱 → values)

Built-in capabilities:
- Giant paragraph detection (nested paragraph count > 3)
- w:tab handling (logical expansion to space separator)
- 3-layer error handling (section skip → field skip → always produce docx)
"""

# Embedded dependencies (vendored at build time)
import os as _os
_utils_dir = _os.path.dirname(_os.path.abspath(__file__))
import sys as _sys
if _utils_dir not in _sys.path:
    _sys.path.insert(0, _utils_dir)
_libs_path = _os.path.join(_utils_dir, 'libs')
if _os.path.exists(_libs_path):
    _sys.path.insert(0, _libs_path)

import zipfile
from lxml import etree as ET
import yaml
import sys
import re

NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

def _normalize_chinese_spaces(text):
    """Remove spaces between Chinese characters and strip English suffixes."""
    text = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', text)
    text = re.sub(r'\s+[A-Za-z\s]+$', '', text).strip()
    # Strip trailing English suffix even if there are no spaces, provided Chinese chars are present
    if re.search(r'[\u4e00-\u9fff]', text) and re.search(r'[A-Za-z]+$', text):
        text = re.sub(r'\s*[A-Za-z\s]+$', '', text).strip()
    return text

# Register namespace prefixes so lxml preserves them during serialization
_NSMAP = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'mc': 'http://schemas.openxmlformats.org/markup-compatibility/2006',
    'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'wps': 'http://schemas.openxmlformats.org/officeWord/2010/wordprocessingShape',
    'v': 'urn:schemas-microsoft-com:vml',
    'o': 'urn:schemas-microsoft-com:office:office',
    'w14': 'http://schemas.microsoft.com/office/word/2010/wordml',
    'w15': 'http://schemas.microsoft.com/office/word/2012/wordml',
    'wp14': 'http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing',
    'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
}
for prefix, uri in _NSMAP.items():
    ET.register_namespace(prefix, uri)

XML_NS = 'http://www.w3.org/XML/1998/namespace'


def _get_bundled_templates_dir():
    """Return bundled templates dir in both dev (project/templates) and packaged (resources/templates)."""
    here = _os.path.dirname(_os.path.abspath(__file__))
    candidates = [
        _os.path.abspath(_os.path.join(here, '..', 'templates')),
        _os.path.abspath(_os.path.join(here, '..', '..', 'templates')),
    ]
    for d in candidates:
        if _os.path.isdir(d):
            return d
    return candidates[0]


def _cleanup_docx_preview_artifacts(output_path: str):
    """Remove source-less VML image placeholders that QuickLook renders as gray blocks."""
    try:
        from photo_replace import cleanup_empty_vml_imagedata
        result = cleanup_empty_vml_imagedata(output_path)
        if result.get('removed'):
            print(f"docx_cleanup:preview_artifacts:{result.get('removed')}", file=sys.stderr)
        elif result.get('warning'):
            print(f"docx_cleanup:WARN:{result.get('warning')}", file=sys.stderr)
        return result
    except Exception as exc:
        print(f"docx_cleanup:WARN:{exc}", file=sys.stderr)
        return None


def _apply_photo_replacement_if_needed(output_path: str, data: dict):
    """Post-process a filled DOCX with the uploaded portrait, if present.

    Avatar replacement must never make an otherwise valid Word export fail.  The
    detailed diagnostics are emitted to stderr for validation scripts and preview
    debugging, while callers still receive their filled document.
    """
    try:
        photo_value = (data or {}).get('basicInfo', {}).get('photo', '')
        if not photo_value:
            return None
        from photo_replace import replace_photo_in_docx
        result = replace_photo_in_docx(output_path, photo_value)
        if result.get('replaced'):
            media = ','.join(result.get('replaced_media', []))
            print(f"photo_replace:OK:{media}", file=sys.stderr)
        else:
            warnings = '|'.join(result.get('warnings', [])) or 'unknown'
            print(f"photo_replace:WARN:{warnings}", file=sys.stderr)
        return result
    except Exception as exc:
        print(f"photo_replace:WARN:{exc}", file=sys.stderr)
        return None


def _set_xml_space_if_needed(t_node, text):
    if text and (text[:1].isspace() or text[-1:].isspace()):
        t_node.set(f'{{{XML_NS}}}space', 'preserve')
    elif f'{{{XML_NS}}}space' in t_node.attrib:
        del t_node.attrib[f'{{{XML_NS}}}space']


def _find_parent_run(node):
    parent = node.getparent()
    while parent is not None:
        if parent.tag == f'{{{NS}}}r':
            return parent
        parent = parent.getparent()
    return None


def _ensure_run_font_size(run, half_points='16'):
    """Set run font size, preserving existing rPr and using half-point units."""
    if run is None:
        return
    rPr = run.find(f'{{{NS}}}rPr')
    if rPr is None:
        rPr = ET.Element(f'{{{NS}}}rPr')
        run.insert(0, rPr)
    for tag in ('sz', 'szCs'):
        node = rPr.find(f'{{{NS}}}{tag}')
        if node is None:
            node = ET.Element(f'{{{NS}}}{tag}')
            rPr.append(node)
        node.set(f'{{{NS}}}val', half_points)


def _write_text_node_with_breaks(t_node, value):
    """Write text into a w:t node, converting literal \n into w:br siblings.

    Returns newly-created w:t nodes so callers can mark them as modified.
    """
    value = '' if value is None else str(value)
    parts = value.split('\n')
    t_node.text = parts[0]
    _set_xml_space_if_needed(t_node, parts[0])

    inserted_text_nodes = []
    parent = t_node.getparent()
    if len(parts) > 1 and parent is not None:
        insert_at = parent.index(t_node) + 1
        for part in parts[1:]:
            br = ET.Element(f'{{{NS}}}br')
            new_t = ET.Element(f'{{{NS}}}t')
            new_t.text = part
            _set_xml_space_if_needed(new_t, part)
            parent.insert(insert_at, br)
            insert_at += 1
            parent.insert(insert_at, new_t)
            insert_at += 1
            inserted_text_nodes.append(new_t)

    if '@' in value and len(value) > 18:
        _ensure_run_font_size(_find_parent_run(t_node), '16')
    return inserted_text_nodes

# All known section headers for boundary detection
ALL_SECTION_HEADERS = [
    '教育背景', '教育经历', '工作经历', '工作经验', '实习经历',
    '校内实践', '实践经历', '证书奖励', '荣誉证书', '荣誉奖项',
    '个人荣誉', '荣誉AWARDS', '自我评价', '个人介绍', '个人信息',
    '专业技能', '职业技能', '掌握技能', '技能SKILLS', '兴趣爱好',
    '资格证书', '在校经历', '获奖经历', '奖项荣誉', '基本信息',
    '联系方式', '主修课程', '其他工作经历', '技能证书',
    '实践经历PRACTICAL EXPERIENCE', '实习经历JOB EXPERIENCE',
    '教育背景EDUCATION', '荣誉AWARDS', '技能SKILLS',
    # Additional headers
    '荣誉奖励', '获得荣誉', '获奖情况', '所获证书', '证书奖项', '技能奖项',
    '个人技能', '工作技能', '软件技能', '外语技能', '职场技能', '商务技能',
    '个人简介', '个人评价', '自我总结', '个人资料', '基本资料', '基础信息',
    '个人简历', '求职简历', '实习实践', '工作实践', '校内活动', '实践活动',
    '竞赛经历', '奖学金', '优势特长', '技能评价', '个人特性',
    '校园经历', '社团经历', '学生工作', '培训经历',
    # English headers
    'EDUCATION', 'EXPERIENCE', 'SKILLS', 'AWARDS', 'INTRODUCTION',
    'PRACTICAL', 'RESUME', 'JOB', 'TRAINING', 'PERSONAL', 'PROFILE',
    'ABOUT', 'CONTACT',
]


class TemplateEngine:
    def __init__(self, template_path: str, config: dict):
        self.template_path = template_path
        self.config = config
        self.warnings = []
        self._modified_nodes = set()  # Track which text nodes were modified

        with zipfile.ZipFile(template_path, 'r') as z:
            self.doc_xml = z.read('word/document.xml').decode('utf-8')
        self.root = ET.fromstring(self.doc_xml.encode('utf-8'))
        self.body = self.root.find(f'{{{NS}}}body')
        self.paragraphs = list(self.body.iter(f'{{{NS}}}p'))

        self._detect_giant_paragraphs()

    def _warn(self, msg: str):
        self.warnings.append(msg)
        print(f"  [WARN] {msg}", file=sys.stderr)

    # ── Giant paragraph detection ──────────────────────────────────────
    def _detect_giant_paragraphs(self):
        self.giant_para_indices = set()
        body_direct = [c for c in self.body if c.tag == f'{{{NS}}}p']
        for p in body_direct:
            nested_count = len(list(p.iter(f'{{{NS}}}p')))
            if nested_count > 3:
                try:
                    idx = self.paragraphs.index(p)
                    self.giant_para_indices.add(idx)
                except ValueError:
                    pass

    # ── Text node helpers ──────────────────────────────────────────────
    def _get_own_text_nodes(self, para):
        nodes = []
        for r in para.findall(f'{{{NS}}}r'):
            for t in r.findall(f'{{{NS}}}t'):
                nodes.append(t)
        return nodes

    def _get_para_texts(self, para):
        result = []
        for r in para.findall(f'{{{NS}}}r'):
            for t in r.findall(f'{{{NS}}}t'):
                txt = (t.text or '').strip()
                if txt:
                    result.append((t, txt))
        return result

    def _get_para_full_text(self, para):
        texts = []
        for r in para.findall(f'{{{NS}}}r'):
            for t in r.findall(f'{{{NS}}}t'):
                if t.text:
                    texts.append(t.text)
        return ''.join(texts).strip()

    def _set_node_text(self, t_node, value):
        inserted = _write_text_node_with_breaks(t_node, value)
        self._modified_nodes.add(t_node)
        for new_t in inserted:
            self._modified_nodes.add(new_t)

    def _clear_node_text(self, t_node):
        t_node.text = ''
        self._modified_nodes.add(t_node)

    # ── Section boundary detection ─────────────────────────────────────
    def _find_section_paras(self, header_text):
        results = []
        normalized_header = _normalize_chinese_spaces(header_text)
        for pi, p in enumerate(self.paragraphs):
            if pi in self.giant_para_indices:
                continue
            own = self._get_own_text_nodes(p)
            for t in own:
                txt = _normalize_chinese_spaces((t.text or '').strip())
                if txt == normalized_header:
                    results.append((pi, p))
                    break
        return results

    def _find_next_header_pi(self, start_pi, skip_text=None):
        normalized_skip = _normalize_chinese_spaces(skip_text) if skip_text else None
        for pi in range(start_pi + 1, len(self.paragraphs)):
            if pi in self.giant_para_indices:
                continue
            own = self._get_own_text_nodes(self.paragraphs[pi])
            for t in own:
                txt = _normalize_chinese_spaces((t.text or '').strip())
                if txt in ALL_SECTION_HEADERS and txt != normalized_skip:
                    return pi
        return len(self.paragraphs)

    def _find_prev_header_pi(self, start_pi, skip_text=None):
        normalized_skip = _normalize_chinese_spaces(skip_text) if skip_text else None
        for pi in range(start_pi - 1, -1, -1):
            if pi in self.giant_para_indices:
                continue
            own = self._get_own_text_nodes(self.paragraphs[pi])
            for t in own:
                txt = _normalize_chinese_spaces((t.text or '').strip())
                if txt in ALL_SECTION_HEADERS and txt != normalized_skip:
                    return pi
        return 0

    def _get_section_content_paras(self, header_pi):
        """Get content paragraphs around a header.
        Returns (before_paras, after_paras) where each is list of (pi, para).
        """
        header_text = self._get_para_full_text(self.paragraphs[header_pi]).strip()
        prev_pi = self._find_prev_header_pi(header_pi, skip_text=header_text)
        next_pi = self._find_next_header_pi(header_pi, skip_text=header_text)

        before = []
        for pi in range(prev_pi, header_pi):
            if pi in self.giant_para_indices:
                continue
            p = self.paragraphs[pi]
            own = self._get_own_text_nodes(p)
            if own:
                before.append((pi, p))

        after = []
        for pi in range(header_pi + 1, next_pi):
            if pi in self.giant_para_indices:
                continue
            p = self.paragraphs[pi]
            own = self._get_own_text_nodes(p)
            if own:
                after.append((pi, p))

        return before, after

    # ── Mode 1: label_inline ───────────────────────────────────────────
    def _match_label_inline(self, para, pattern, value):
        for t, txt in self._get_para_texts(para):
            if pattern in txt:
                sep_idx = txt.find('：')
                if sep_idx < 0:
                    sep_idx = txt.find(':')
                if sep_idx >= 0 and sep_idx >= len(pattern) - 1:
                    before = txt[:sep_idx + 1]
                    self._set_node_text(t, before + value)
                    # Clear other text nodes in same paragraph (template remnants)
                    for other_t, _ in self._get_para_texts(para):
                        if other_t is not t:
                            self._clear_node_text(other_t)
                    return True
        return False

    # ── Mode 2: label_adjacent ─────────────────────────────────────────
    def _match_label_adjacent(self, para, pattern, value):
        """Match label in one text node, value in next non-empty text node (same paragraph)."""
        texts = self._get_para_texts(para)
        for i, (t, txt) in enumerate(texts):
            if txt == pattern or txt.startswith(pattern):
                for j in range(i + 1, len(texts)):
                    t2, txt2 = texts[j]
                    if txt2 and not self._is_label_text(txt2):
                        self._set_node_text(t2, value)
                        return True
        return False

    def _match_label_adjacent_cross_para(self, label_pi, pattern, value, max_distance=3):
        """Match label in paragraph N, value in paragraph N+1..N+max_distance."""
        for offset in range(1, max_distance + 1):
            target_pi = label_pi + offset
            if target_pi >= len(self.paragraphs):
                break
            if target_pi in self.giant_para_indices:
                continue
            p = self.paragraphs[target_pi]
            texts = self._get_para_texts(p)
            for t, txt in texts:
                if txt and not self._is_label_text(txt) and not self._is_section_header(txt):
                    self._set_node_text(t, value)
                    return True
        return False

    def _is_label_text(self, txt):
        label_patterns = [
            '姓名', '电话', '手机', '邮箱', 'Email', 'email',
            '地址', '网址', '院校', '学校', '专业', '学历',
            '年龄', '籍贯', '性别', '身高', '政治面貌',
            '生日', '现居', '微信', '微博', 'QQ',
        ]
        return any(txt.startswith(p) for p in label_patterns)

    def _is_section_header(self, txt):
        return txt in ALL_SECTION_HEADERS

    # ── Mode 3: keyword_scan ───────────────────────────────────────────
    def _match_keyword_scan(self, para, keywords, value, value_scope='keyword_substring'):
        texts = self._get_para_texts(para)
        for t, txt in texts:
            for kw in keywords:
                if kw in txt:
                    if value_scope == 'full_node':
                        # Only match if keyword is significant portion (>30%) or >=2 chars
                        if len(kw) >= 2 or txt == kw:
                            self._set_node_text(t, value)
                            return True
                    else:
                        new_txt = self._expand_and_replace(txt, kw, value)
                        self._set_node_text(t, new_txt)
                        return True
        # Fallback: check concatenated text for split-node keywords
        if texts:
            concat = ''.join(txt for _, txt in texts)
            concat_nospace = concat.replace(' ', '').replace('\u3000', '')
            for kw in keywords:
                kw_nospace = kw.replace(' ', '')
                if kw_nospace in concat_nospace:
                    if value_scope == 'full_node':
                        if len(kw) >= 2:
                            self._set_node_text(texts[0][0], value)
                            for t, _ in texts[1:]:
                                self._clear_node_text(t)
                            return True
                    else:
                        new_concat = self._expand_and_replace(concat, kw, value)
                        self._set_node_text(texts[0][0], new_concat)
                        for t, _ in texts[1:]:
                            self._clear_node_text(t)
                        return True
        return False

    def _expand_and_replace(self, txt, keyword, value):
        idx = txt.find(keyword)
        if idx < 0:
            return txt
        MAX_EXPAND = 5  # Maximum characters to expand in each direction
        MAX_RESULT = 10  # Maximum length of expanded region
        start = idx
        expanded_back = 0
        while start > 0 and expanded_back < MAX_EXPAND:
            ch = txt[start - 1]
            if ch in ' \t，。、；：|/！？（）()[]【】{}':
                break
            start -= 1
            expanded_back += 1
        end = idx + len(keyword)
        expanded_fwd = 0
        while end < len(txt) and expanded_fwd < MAX_EXPAND:
            ch = txt[end]
            if ch in ' \t，。、；：|/！？（）()[]【】{}':
                break
            end += 1
            expanded_fwd += 1
        # If expanded region is too long, just replace the keyword itself
        if (end - start) > MAX_RESULT:
            return txt[:idx] + value + txt[idx + len(keyword):]
        return txt[:start] + value + txt[end:]

    def _fill_keyword_global(self, keywords, value, value_scope='keyword_substring', replace_all=False):
        filled = False
        for pi, p in enumerate(self.paragraphs):
            if pi in self.giant_para_indices:
                continue
            if self._match_keyword_scan(p, keywords, value, value_scope):
                filled = True
                if not replace_all:
                    return True
        return filled

    # ── Mode 5: pattern_match (regex-based phone/email) ──────────────
    def _fill_pattern_match(self, pattern_type, value):
        import re
        if pattern_type == 'phone':
            for pi, p in enumerate(self.paragraphs):
                for t in p.iter(f'{{{NS}}}t'):
                    txt = (t.text or '').strip()
                    if not txt:
                        continue
                    # Build index mapping for non-space, non-dash characters
                    mapping = []
                    text_no_space = ""
                    for idx, char in enumerate(txt):
                        if char not in " \t\n\r-–—":
                            mapping.append(idx)
                            text_no_space += char
                    
                    match = re.search(r'1[3-9]\d{8,9}', text_no_space)
                    if match:
                        start_no_space, end_no_space = match.start(), match.end()
                        start_orig = mapping[start_no_space]
                        end_orig = mapping[end_no_space - 1] + 1
                        new_txt = txt[:start_orig] + value + " " + txt[end_orig:]
                        self._set_node_text(t, new_txt)
                        return True
            return False
        elif pattern_type == 'email':
            regex = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]*\.[a-zA-Z]{2,}')
            for pi, p in enumerate(self.paragraphs):
                for t in p.iter(f'{{{NS}}}t'):
                    txt = (t.text or '').strip()
                    if not txt:
                        continue
                    match = regex.search(txt)
                    if match:
                        new_txt = txt[:match.start()] + value + txt[match.end():]
                        self._set_node_text(t, new_txt)
                        return True
        return False

    # ── Mode 4: section_replace ────────────────────────────────────────
    def _fill_section_replace(self, header_text, value):
        header_paras = self._find_section_paras(header_text)
        if not header_paras:
            return False

        filled = False
        for header_pi, _ in header_paras:
            # Search AFTER the header first
            next_pi = self._find_next_header_pi(header_pi, skip_text=header_text)
            for pi in range(header_pi + 1, next_pi):
                if pi in self.giant_para_indices:
                    continue
                p = self.paragraphs[pi]
                own = self._get_own_text_nodes(p)
                if own:
                    self._set_node_text(own[0], value)
                    for t in own[1:]:
                        self._clear_node_text(t)
                    filled = True
                    break

            # If not found after, search BEFORE the header
            if not filled:
                prev_pi = self._find_prev_header_pi(header_pi, skip_text=header_text)
                for pi in range(header_pi - 1, prev_pi - 1, -1):
                    if pi in self.giant_para_indices:
                        continue
                    p = self.paragraphs[pi]
                    own = self._get_own_text_nodes(p)
                    if own:
                        self._set_node_text(own[0], value)
                        for t in own[1:]:
                            self._clear_node_text(t)
                        filled = True
                        break

            if filled:
                break  # Only fill the FIRST occurrence of a section

        return filled

    # ── Mode 5: label_group ────────────────────────────────────────────
    def _fill_label_group(self, field_patterns, data_values):
        """Handle label group → value group pattern.
        field_patterns: dict of {field_name: label_pattern}
        data_values: dict of {field_name: value}
        """
        # Find all label paragraphs
        label_paras = []
        for pi, p in enumerate(self.paragraphs):
            if pi in self.giant_para_indices:
                continue
            own = self._get_own_text_nodes(p)
            for t in own:
                txt = (t.text or '').strip()
                for field_name, pattern in field_patterns.items():
                    if txt == pattern or txt.startswith(pattern):
                        label_paras.append((pi, field_name))
                        break

        if not label_paras:
            return False

        # Find value paragraphs after the last label
        last_label_pi = max(lp[0] for lp in label_paras)
        value_paras = []
        for pi in range(last_label_pi + 1, len(self.paragraphs)):
            if pi in self.giant_para_indices:
                continue
            p = self.paragraphs[pi]
            own = self._get_own_text_nodes(p)
            if own:
                full_text = self._get_para_full_text(p)
                if full_text and not self._is_label_text(full_text) and not self._is_section_header(full_text):
                    value_paras.append((pi, p))
            if len(value_paras) >= len(label_paras):
                break

        # Match labels to values by position
        filled = False
        for i, (label_pi, field_name) in enumerate(label_paras):
            if field_name not in data_values or not data_values[field_name]:
                continue
            if i < len(value_paras):
                _, p = value_paras[i]
                own = self._get_own_text_nodes(p)
                if own:
                    self._set_node_text(own[0], data_values[field_name])
                    for t in own[1:]:
                        self._clear_node_text(t)
                    filled = True

        return filled

    # ── Entry schema filling ───────────────────────────────────────────
    def _try_fill_entries(self, entry_paras, entry_schema, entries):
        """Try to fill entries in the given paragraphs. Returns number of entries filled."""
        entry_idx = 0
        schema_keys = list(entry_schema.keys())
        primary_field = schema_keys[0] if schema_keys else None

        for pi, p in entry_paras:
            if entry_idx >= len(entries):
                break
            entry = entries[entry_idx]
            filled_any = False
            primary_filled = False
            for field_name, field_cfg in entry_schema.items():
                if field_name not in entry or not entry[field_name]:
                    continue
                value = str(entry[field_name])
                ftype = field_cfg.get('type')
                if ftype == 'keyword_scan':
                    keywords = field_cfg.get('keywords', [])
                    vs = field_cfg.get('value_scope', 'keyword_substring')
                    if self._match_keyword_scan(p, keywords, value, vs):
                        filled_any = True
                        if field_name == primary_field:
                            primary_filled = True
                elif ftype == 'full_node_replace':
                    fmt = field_cfg.get('format', '{value}')
                    formatted = fmt.format(value=value, **{k: str(entry.get(k, '')) for k in entry})
                    own = self._get_own_text_nodes(p)
                    if own:
                        self._set_node_text(own[0], formatted)
                        for t in own[1:]:
                            self._clear_node_text(t)
                        filled_any = True
                        if field_name == primary_field:
                            primary_filled = True

            # Only move to next entry when the primary field (company/school) is filled
            if primary_filled:
                entry_idx += 1
        return entry_idx

    def _fill_entry_schema(self, header_text, entry_schema, entries, item_separator='paragraph'):
        header_paras = self._find_section_paras(header_text)
        if not header_paras:
            return False

        for header_pi, _ in header_paras:
            before_paras, after_paras = self._get_section_content_paras(header_pi)

            # Try AFTER first (most common in Chinese templates), then BEFORE
            filled = 0
            if after_paras:
                filled = self._try_fill_entries(after_paras, entry_schema, entries)
            if filled == 0 and before_paras:
                filled = self._try_fill_entries(before_paras, entry_schema, entries)

            if filled > 0:
                return True

        return False

    def _fill_entry_global_fallback(self, entry_schema, entries):
        """Last-resort entry fill for templates where content is far from its header."""
        entry_paras = []
        for pi, p in enumerate(self.paragraphs):
            if pi in self.giant_para_indices:
                continue
            own = self._get_own_text_nodes(p)
            if not own:
                continue
            full_text = self._get_para_full_text(p)
            if not full_text or self._is_section_header(full_text) or self._is_label_text(full_text):
                continue
            entry_paras.append((pi, p))
        return self._try_fill_entries(entry_paras, entry_schema, entries) > 0

    def _fill_title_fallback(self, value):
        """Fill job-title/target placeholders when YAML only had a missing label."""
        title_placeholders = [
            '平面设计', '网页设计师', '美术主编', 'UI设计师', '销售员岗位',
            '产品经理', '运营专员', '行政助理', '市场专员', '数控编程师', '营销经理',
            '应聘岗位', '目标职位', '求职目标', '职位名称', '岗位名称', '意向岗位',
        ]
        if self._fill_keyword_global(title_placeholders, value, 'keyword_substring', replace_all=True):
            return True

        for pattern in ['求职意向', '目标职位', '应聘职位', '应聘岗位', '意向岗位', '职位', '岗位']:
            for pi, p in enumerate(self.paragraphs):
                if pi in self.giant_para_indices:
                    continue
                if self._match_label_inline(p, pattern, value):
                    return True

        # Last resort for templates whose job title is a standalone short headline near the top.
        candidate_text = None
        for pi, p in enumerate(self.paragraphs):
            if pi in self.giant_para_indices:
                continue
            own = self._get_own_text_nodes(p)
            full_text = self._get_para_full_text(p)
            if not own or not full_text or any(t in self._modified_nodes for t in own):
                continue
            if self._is_section_header(full_text) or self._is_label_text(full_text):
                continue
            if '@' in full_text or re.search(r'\d{4,}|\d{2,}岁', full_text):
                continue
            if len(full_text) <= 30 and (pi < 25 or any(k in full_text for k in ['岗位', '职位', '专员', '经理', '设计', '工程师', '实习', '运营', '市场'])):
                candidate_text = full_text
                break
        if candidate_text:
            filled = False
            for pi, p in enumerate(self.paragraphs):
                if pi in self.giant_para_indices:
                    continue
                own = self._get_own_text_nodes(p)
                if own and self._get_para_full_text(p) == candidate_text:
                    self._set_node_text(own[0], value)
                    for t in own[1:]:
                        self._clear_node_text(t)
                    filled = True
            if filled:
                return True
        return False

    def _fill_summary_fallback(self, value):
        """Fill a plausible long-text summary placeholder when a configured header is absent."""
        summary_markers = ['自我评价', '个人介绍', '个人总结', '自我介绍', '个人陈述', '个人简介', '个人评价', '关于我']
        skip_markers = ['电话', '手机', '邮箱', 'Email', '教育', '经历', '技能', '荣誉', '证书', '工作', '实习']

        # Prefer paragraphs that mention a summary marker but include placeholder content.
        for pi, p in enumerate(self.paragraphs):
            if pi in self.giant_para_indices:
                continue
            own = self._get_own_text_nodes(p)
            full_text = self._get_para_full_text(p)
            if own and any(m in full_text for m in summary_markers) and full_text not in summary_markers:
                self._set_node_text(own[0], value)
                for t in own[1:]:
                    self._clear_node_text(t)
                return True

        # Last resort: replace an untouched, non-structural long paragraph.
        for pi, p in enumerate(self.paragraphs):
            if pi in self.giant_para_indices:
                continue
            own = self._get_own_text_nodes(p)
            full_text = self._get_para_full_text(p)
            if not own or not full_text or any(t in self._modified_nodes for t in own):
                continue
            if self._is_section_header(full_text) or any(m in full_text for m in skip_markers):
                continue
            if 20 <= len(full_text) <= 220:
                self._set_node_text(own[0], value)
                for t in own[1:]:
                    self._clear_node_text(t)
                return True
        return False

    def _ensure_contact_fields(self, basic):
        """Ensure required phone/email text exists even when a template lacks explicit placeholders."""
        doc_text = ''.join(t.text or '' for t in self.root.iter(f'{{{NS}}}t'))
        missing_parts = []
        phone = basic.get('phone')
        email = basic.get('email')
        if phone and phone not in doc_text:
            missing_parts.append(phone)
        if email and email not in doc_text:
            missing_parts.append(email)
        if not missing_parts:
            return False

        contact_labels = ['电话', '手机', '邮箱', 'Email', 'E-mail', '联系方式', '联系我', 'CONTACT', 'QQ', '微信']
        target = None

        # Prefer an existing contact/basic-info paragraph.
        for pi, p in enumerate(self.paragraphs):
            if pi in self.giant_para_indices:
                continue
            own = self._get_own_text_nodes(p)
            full_text = self._get_para_full_text(p)
            if not own or not full_text:
                continue
            if (phone and phone in full_text) or any(label in full_text for label in contact_labels):
                target = (own, full_text)
                break

        # Fallback to an early short personal-info paragraph.
        if target is None:
            for pi, p in enumerate(self.paragraphs[:40]):
                if pi in self.giant_para_indices:
                    continue
                own = self._get_own_text_nodes(p)
                full_text = self._get_para_full_text(p)
                if not own or not full_text or self._is_section_header(full_text):
                    continue
                if len(full_text) <= 60 and not any(h in full_text for h in ['教育', '工作', '经历', '技能', '荣誉']):
                    target = (own, full_text)
                    break

        if target is None:
            return False

        own, full_text = target
        separator = ' | ' if full_text else ''
        self._set_node_text(own[0], full_text + separator + ' | '.join(missing_parts))
        for t in own[1:]:
            self._clear_node_text(t)
        return True

    # ── Main fill method ───────────────────────────────────────────────
    def fill(self, data: dict, output_path: str) -> bool:
        basic = data.get('basicInfo', {})
        any_filled = False

        # Collect label_group fields
        bi_cfg = self.config.get('basic_info', {}).get('fields', {})
        label_group_fields = {}
        non_group_fields = {}

        for field_name, field_cfg in bi_cfg.items():
            if field_cfg.get('type') == 'label_group':
                label_group_fields[field_name] = field_cfg
            else:
                non_group_fields[field_name] = field_cfg

        # Fill label_group fields first
        if label_group_fields:
            patterns = {k: v.get('pattern', '') for k, v in label_group_fields.items()}
            values = {k: basic.get(k, '') for k in label_group_fields}
            if self._fill_label_group(patterns, values):
                any_filled = True

        # Fill non-group basic_info fields
        unfilled_basic_fields = []
        for field_name, field_cfg in non_group_fields.items():
            value = basic.get(field_name)
            if not value:
                continue

            ftype = field_cfg.get('type')
            filled = False

            if ftype == 'label_inline':
                pattern = field_cfg.get('pattern', '')
                for pi, p in enumerate(self.paragraphs):
                    if pi in self.giant_para_indices:
                        continue
                    if self._match_label_inline(p, pattern, value):
                        filled = True
                        break
                # Fallback: try giant paragraphs too
                if not filled:
                    for pi in self.giant_para_indices:
                        p = self.paragraphs[pi]
                        if self._match_label_inline(p, pattern, value):
                            filled = True
                            break

            elif ftype == 'label_adjacent':
                pattern = field_cfg.get('pattern', '')
                for pi, p in enumerate(self.paragraphs):
                    if pi in self.giant_para_indices:
                        continue
                    if self._match_label_adjacent(p, pattern, value):
                        filled = True
                        break
                # Fallback: try giant paragraphs too
                if not filled:
                    for pi in self.giant_para_indices:
                        p = self.paragraphs[pi]
                        if self._match_label_adjacent(p, pattern, value):
                            filled = True
                            break
                # Fallback: cross-paragraph label_adjacent
                if not filled:
                    for pi, p in enumerate(self.paragraphs):
                        if pi in self.giant_para_indices:
                            continue
                        own = self._get_own_text_nodes(p)
                        for t in own:
                            txt = (t.text or '').strip()
                            if txt == pattern or txt.startswith(pattern):
                                if self._match_label_adjacent_cross_para(pi, pattern, value):
                                    filled = True
                                    break
                        if filled:
                            break

            elif ftype == 'keyword_scan':
                keywords = field_cfg.get('keywords', [])
                vs = field_cfg.get('value_scope', 'keyword_substring')
                # Replace all occurrences for name/title, first-only for others
                ra = field_name in ('name', 'title')
                filled = self._fill_keyword_global(keywords, value, vs, replace_all=ra)

            elif ftype == 'pattern_match':
                # Regex-based matching for phone/email without labels
                pattern_type = field_cfg.get('pattern_type', '')
                filled = self._fill_pattern_match(pattern_type, value)

            elif ftype == 'section_replace':
                section = field_cfg.get('section', '')
                filled = self._fill_section_replace(section, value)

            if not filled and field_name == 'title':
                filled = self._fill_title_fallback(value)
            if not filled and field_name == 'summary':
                filled = self._fill_summary_fallback(value)

            if not filled:
                unfilled_basic_fields.append((field_name, ftype))
            else:
                any_filled = True

        if self._ensure_contact_fields(basic):
            any_filled = True

        doc_text_after_basic = ''.join(t.text or '' for t in self.root.iter(f'{{{NS}}}t'))
        if basic.get('summary') and str(basic.get('summary')) not in doc_text_after_basic and 'summary' not in non_group_fields:
            if self._fill_summary_fallback(str(basic.get('summary'))):
                any_filled = True
                doc_text_after_basic = ''.join(t.text or '' for t in self.root.iter(f'{{{NS}}}t'))

        for field_name, ftype in unfilled_basic_fields:
            value = basic.get(field_name)
            if value and str(value) not in doc_text_after_basic:
                self._warn(f"Field '{field_name}' not filled (type={ftype})")
            elif value:
                any_filled = True

        # Fill sections (education, experience, etc.)
        for sec_name, sec_cfg in self.config.get('sections', {}).items():
            header = sec_cfg.get('header', '')
            sec_type = sec_cfg.get('type')

            if sec_type == 'section_replace':
                items = data.get(sec_name, [])
                if not items:
                    continue
                if isinstance(items[0], str):
                    value = '\n'.join(f'• {item}' if sec_name == 'honors' else item for item in items)
                else:
                    value = '\n'.join(str(item) for item in items)
                if self._fill_section_replace(header, value):
                    any_filled = True
                else:
                    self._warn(f"Section '{sec_name}' header '{header}' not found")

            elif 'entry_schema' in sec_cfg:
                entries = data.get(sec_name, [])
                if not entries:
                    continue
                schema = sec_cfg['entry_schema']
                sep = sec_cfg.get('item_separator', 'paragraph')
                filled_entries = self._fill_entry_schema(header, schema, entries, sep)
                if not filled_entries:
                    filled_entries = self._fill_entry_global_fallback(schema, entries)
                if filled_entries:
                    any_filled = True
                else:
                    self._warn(f"Section '{sec_name}' entries not filled")

        # Snapshot modified nodes BEFORE post-processing cleanup
        self._fill_modified = set(self._modified_nodes)

        # Post-processing: replace ALL remaining placeholder names globally
        name = basic.get('name', '')
        if name:
            PLACEHOLDER_NAMES = [
                '宋艾嘉', '肖颖馨', '韩志弘', '李自强', '张三', '李四', '王五',
                '赵六', '关睢尔', '陈小明', '刘小红', '周洁', '吴芳',
                '白晓云', '王若琳', '沈慧美', '林晓歌', '林月明', '柳云萧',
                '苏语凝', '钟小艾', '冯青', '张小泉', '云海', '陈知页',
                '孟子君', '孟晓思', '关月兰', '宋艾嘉',
            ]
            for pi, p in enumerate(self.paragraphs):
                if pi in self.giant_para_indices:
                    continue
                texts = self._get_para_texts(p)
                for t, txt in texts:
                    if txt in PLACEHOLDER_NAMES:
                        self._set_node_text(t, name)
                # Also check concatenated text for split-node names
                if texts:
                    concat = ''.join(txt for _, txt in texts)
                    concat_ns = concat.replace(' ', '').replace('\u3000', '')
                    for ph in PLACEHOLDER_NAMES:
                        ph_ns = ph.replace(' ', '')
                        if ph_ns in concat_ns:
                            self._set_node_text(texts[0][0], name)
                            for t, _ in texts[1:]:
                                self._clear_node_text(t)
                            break

            # Keep post-processed placeholder replacements from being blanked by cleanup.
            self._fill_modified.update(self._modified_nodes)

        # Post-processing: clear paragraphs that were NOT modified by the fill.
        # For templates with duplicated content (two text box areas),
        # the engine fills one copy but leaves the other untouched.
        # Blank all untouched, non-header, non-giant paragraphs with significant text.
        all_headers = set(ALL_SECTION_HEADERS)
        for sec_cfg in self.config.get('sections', {}).values():
            h = sec_cfg.get('header', '')
            if h:
                all_headers.add(h)
        # Also add basic_info labels to the safe list
        for fcfg in bi_cfg.values():
            p = fcfg.get('pattern', '')
            if p:
                all_headers.add(p)

        for pi, p in enumerate(self.paragraphs):
            if pi in self.giant_para_indices:
                continue
            own = self._get_own_text_nodes(p)
            if not own:
                continue
            # Check if ANY text node in this paragraph was modified during fill (not post-processing)
            if any(t in self._fill_modified for t in own):
                continue
            full_text = self._get_para_full_text(p)
            if not full_text or len(full_text) < 1:
                continue
            if full_text.strip() in all_headers:
                continue
            # This paragraph was untouched - blank it
            self._clear_node_text(own[0])
            for t in own[1:]:
                self._clear_node_text(t)

        self._save(output_path)
        _cleanup_docx_preview_artifacts(output_path)
        _apply_photo_replacement_if_needed(output_path, data)
        return any_filled

    def _save(self, output_path: str):
        xml_bytes = ET.tostring(self.root, xml_declaration=True, encoding='UTF-8', standalone=True)

        with zipfile.ZipFile(self.template_path, 'r') as zin:
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    if item.filename == 'word/document.xml':
                        zout.writestr(item, xml_bytes)
                    else:
                        zout.writestr(item, zin.read(item.filename))


def fill_with_docxtpl(template_path: str, data: dict, output_path: str) -> bool:
    """Fill a template using docxtpl (Level 1 in progressive fallback)."""
    try:
        from docxtpl import DocxTemplate
        doc = DocxTemplate(template_path)
        
        # Build context
        context = {}
        basic = data.get('basicInfo', {})
        for k, v in basic.items():
            if k == 'photo':
                continue
            context[k] = v
            
        # Explicit mapping for basic info fields
        context['name'] = basic.get('name', '')
        context['title'] = basic.get('title', '')
        context['phone'] = basic.get('phone', '')
        context['email'] = basic.get('email', '')
        context['wechat'] = basic.get('wechat', '')
        context['address'] = basic.get('address', '')
        context['birthday'] = basic.get('birthday', '')
        context['degree'] = basic.get('degree', '')
        context['major'] = basic.get('major', '')
        context['summary'] = basic.get('summary', '') or data.get('summary', '')
        
        # Map list sections
        edus = data.get('education', [])
        exps = data.get('experience', [])
        sw_list = data.get('studentWork', [])
        honors = data.get('honors', [])
        skills = data.get('skills', [])

        # For 文艺单页01 basic info compatibility
        context['basic_school'] = edus[0].get('school', '') if edus else ''
        context['basic_major'] = edus[0].get('major', '') if edus else ''
        context['age'] = basic.get('birthday', '')
        
        # Legacy compatibility (flat first item)
        if edus:
            context['edu_school'] = edus[0].get('school', '')
            context['edu_major'] = edus[0].get('major', '')
            context['edu_degree'] = edus[0].get('degree', '')
            context['edu_date'] = edus[0].get('date', '')
        if exps:
            context['exp_company'] = exps[0].get('company', '')
            context['exp_role'] = exps[0].get('role', '')
            context['exp_date'] = exps[0].get('date', '')
            context['exp_desc'] = exps[0].get('description', '')

        # Flat indexed mapping for TextBox level layout templates (up to 2 items)
        for i in range(1, 3):
            # Education
            edu = edus[i-1] if len(edus) >= i else {}
            context[f'edu_school{i}'] = edu.get('school', '')
            context[f'edu_major{i}'] = edu.get('major', '')
            context[f'edu_degree{i}'] = edu.get('degree', '')
            context[f'edu_date{i}'] = edu.get('date', '')
            context[f'edu_desc{i}'] = edu.get('description', '')
            context[f'edu_slash{i}'] = '/' if edu.get('major') or edu.get('degree') else ''
            
            # Experience
            exp = exps[i-1] if len(exps) >= i else {}
            context[f'exp_company{i}'] = exp.get('company', '')
            context[f'exp_role{i}'] = exp.get('role', '')
            context[f'exp_date{i}'] = exp.get('date', '')
            context[f'exp_desc{i}'] = exp.get('description', '')

            # Student Work
            sw = sw_list[i-1] if len(sw_list) >= i else {}
            context[f'sw_org{i}'] = sw.get('organization', '')
            context[f'sw_role{i}'] = sw.get('role', '')
            context[f'sw_date{i}'] = sw.get('date', '')
            context[f'sw_desc{i}'] = sw.get('description', '')

        # Honors
        if honors:
            context['honors'] = '\n'.join('• ' + h if not h.startswith('•') and not h.startswith('-') else h for h in honors)
        else:
            context['honors'] = ''
            
        # Skills
        if skills:
            context['skills'] = '；'.join(skills)
            for idx in range(1, 4):
                context[f'skill{idx}'] = skills[idx-1] if len(skills) >= idx else ''
        else:
            context['skills'] = ''
            for idx in range(1, 4):
                context[f'skill{idx}'] = ''

        doc.render(context)
        doc.save(output_path)
        
        # Post-process the generated document to fix layout details
        try:
            with zipfile.ZipFile(output_path, 'r') as zin:
                xml_bytes = zin.read('word/document.xml')
            root = ET.fromstring(xml_bytes)
            
            # 1. Remove empty marked paragraphs to clean up dangling bullet points
            p_to_remove = []
            for p in root.iter(f'{{{NS}}}p'):
                if p.get('delIfEmpty') == '1':
                    all_text = "".join(t.text for t in p.iter(f'{{{NS}}}t') if t.text).strip()
                    # If paragraph text is empty or only bullet punctuation
                    if not all_text or all_text in ['■', '•', '*', '-', ':', '：']:
                        p_to_remove.append(p)
            for p in p_to_remove:
                parent = p.getparent()
                if parent is not None:
                    parent.remove(p)
            
            # 2. Prevent long email addresses from wrapping
            for r in root.iter(f'{{{NS}}}r'):
                for t in r.iter(f'{{{NS}}}t'):
                    if t.text and '@' in t.text and len(t.text) > 18:
                        rPr = r.find(f'{{{NS}}}rPr')
                        if rPr is None:
                            rPr = ET.Element(f'{{{NS}}}rPr')
                            r.insert(0, rPr)
                        sz = rPr.find(f'{{{NS}}}sz')
                        if sz is None:
                            sz = ET.Element(f'{{{NS}}}sz')
                            rPr.append(sz)
                        szCs = rPr.find(f'{{{NS}}}szCs')
                        if szCs is None:
                            szCs = ET.Element(f'{{{NS}}}szCs')
                            rPr.append(szCs)
                        sz.set(f'{{{NS}}}val', '16')  # 8pt
                        szCs.set(f'{{{NS}}}val', '16')
            
            # 3. Resize long skill labels to prevent text overlaps and line wraps
            user_skills = [context.get(f'skill{i}', '') for i in range(1, 4)]
            user_skills = [s for s in user_skills if s]
            for r in root.iter(f'{{{NS}}}r'):
                for t in r.iter(f'{{{NS}}}t'):
                    if t.text and t.text in user_skills and len(t.text) > 6:
                        rPr = r.find(f'{{{NS}}}rPr')
                        if rPr is None:
                            rPr = ET.Element(f'{{{NS}}}rPr')
                            r.insert(0, rPr)
                        sz = rPr.find(f'{{{NS}}}sz')
                        if sz is None:
                            sz = ET.Element(f'{{{NS}}}sz')
                            rPr.append(sz)
                        szCs = rPr.find(f'{{{NS}}}szCs')
                        if szCs is None:
                            szCs = ET.Element(f'{{{NS}}}szCs')
                            rPr.append(szCs)
                        length = len(t.text)
                        new_sz = '12' if length > 14 else ('14' if length > 9 else '16')  # 6pt, 7pt, 8pt
                        sz.set(f'{{{NS}}}val', new_sz)
                        szCs.set(f'{{{NS}}}val', new_sz)
            
            # Write back
            xml_out = ET.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
            temp_zip_path = output_path + '.tmp.zip'
            with zipfile.ZipFile(output_path, 'r') as zin:
                with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zout:
                    for item in zin.infolist():
                        if item.filename == 'word/document.xml':
                            zout.writestr(item, xml_out)
                        else:
                            zout.writestr(item, zin.read(item.filename))
            _os.replace(temp_zip_path, output_path)
            print("Post-processing: Empty paragraphs and fonts cleaned up successfully.", file=_sys.stderr)
        except Exception as pe:
            print(f"Post-processing warning: {pe}", file=_sys.stderr)

        _cleanup_docx_preview_artifacts(output_path)
        _apply_photo_replacement_if_needed(output_path, data)
        print(f"{_os.path.basename(template_path)}:docxtpl:OK", file=_sys.stderr)
        return True
    except Exception as e:
        print(f"docxtpl error: {e}", file=_sys.stderr)
        return False


def has_jinja2_tags(template_path: str) -> bool:
    """Check if template contains Jinja2 placeholders."""
    try:
        with zipfile.ZipFile(template_path, 'r') as z:
            doc_xml = z.read('word/document.xml').decode('utf-8')
        return '{{' in doc_xml or '{%' in doc_xml
    except Exception:
        return False


def has_textboxes(template_path: str) -> bool:
    """Check if template contains absolute positioning textboxes."""
    try:
        with zipfile.ZipFile(template_path, 'r') as z:
            doc_xml = z.read('word/document.xml').decode('utf-8')
        return 'w:txbxContent' in doc_xml
    except Exception:
        return False


def fill(template_path: str, config: dict, data: dict, output_path: str) -> bool:
    engine = TemplateEngine(template_path, config)
    return engine.fill(data, output_path)


def fill_with_config_path(template_path: str, config_path: str, data: dict, output_path: str) -> bool:
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return fill(template_path, config, data, output_path)


def fill_with_fallback(template_path: str, data: dict, output_path: str, layout_adjustments: dict = None) -> bool:
    """Fill a template using docxtpl/YAML config/spatial with v2 fallback.

    Priority:
    1. Template has .docxtpl.docx version → use docxtpl
    2. Template contains Jinja2 tags → use docxtpl
    3. Template is in spatial whitelist → use spatial_engine (Level 2.5)
    4. Template has .yaml → use template_engine (YAML config)
    5. Template has textboxes → use spatial_engine fallback (Level 2.5)
    6. Template engine fails AND yaml has fallback: true → use v2
    7. Template has no .yaml and no textboxes → use v2 directly
    """
    import os

    # Level 1: Check for manually marked template (.docxtpl.docx)
    docxtpl_path = template_path.replace('.docx', '.docxtpl.docx')
    if not os.path.exists(docxtpl_path):
        bundled_dir = _get_bundled_templates_dir()
        alt_docxtpl = os.path.join(bundled_dir, os.path.basename(docxtpl_path))
        if os.path.exists(alt_docxtpl):
            docxtpl_path = alt_docxtpl

    if os.path.exists(docxtpl_path) and has_jinja2_tags(docxtpl_path):
        return fill_with_docxtpl(docxtpl_path, data, output_path)

    # Level 1.5: Template contains Jinja2 tags directly
    if has_jinja2_tags(template_path):
        return fill_with_docxtpl(template_path, data, output_path)

    # White-listed templates that perform much better with spatial engine
    spatial_whitelist = {
        "文艺单页03", "文艺单页04", "文艺单页07", "文艺单页09", "文艺单页16",
        "活泼单页12", "知页简历02", "知页简历03", "稳重单页01", "稳重单页21",
        "简约单页18", "简约单页19", "简约单页30",
        "文艺单页10", "文艺单页12", "稳重单页06", "稳重单页12", "稳重单页20", "简约单页25"
    }
    base_name = os.path.basename(template_path).replace('.docx', '')
    
    if base_name in spatial_whitelist and has_textboxes(template_path):
        try:
            from spatial_engine import fill_spatial
            result = fill_spatial(template_path, data, output_path, layout_adjustments)
            if result:
                print(f"{os.path.basename(template_path)}:spatial:OK", file=sys.stderr)
                return True
        except Exception as e:
            print(f"{os.path.basename(template_path)}:spatial:ERROR_{e}", file=sys.stderr)

    # Level 2: YAML config (for flow layouts)
    config_path = template_path.replace('.docx', '.yaml')
    if not os.path.exists(config_path):
        bundled_dir = _get_bundled_templates_dir()
        alt_config = os.path.join(bundled_dir, os.path.basename(config_path))
        if os.path.exists(alt_config):
            config_path = alt_config

    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            result = fill(template_path, config, data, output_path)
            if result:
                print(f"{os.path.basename(template_path)}:engine:OK", file=sys.stderr)
                return True
            if config.get('fallback', False):
                print(f"{os.path.basename(template_path)}:engine:FAIL_FALLBACK", file=sys.stderr)
            else:
                print(f"{os.path.basename(template_path)}:engine:FAIL_NO_FALLBACK", file=sys.stderr)
                return False
        except Exception as e:
            print(f"{os.path.basename(template_path)}:engine:ERROR_{e}", file=sys.stderr)

    # Level 3: v2 fallback
    from docx_filler_v2 import fill_template as v2_fill
    try:
        v2_fill(template_path, data, output_path)
        _cleanup_docx_preview_artifacts(output_path)
        _apply_photo_replacement_if_needed(output_path, data)
        print(f"{os.path.basename(template_path)}:v2:OK", file=sys.stderr)
        return True
    except Exception as e:
        print(f"{os.path.basename(template_path)}:v2:ERROR_{e}", file=sys.stderr)
        return False


if __name__ == '__main__':
    import json as _json

    if len(sys.argv) < 3:
        print("Usage: python template_engine.py <data.json> <template.docx> <output.docx>")
        print("   or: python template_engine.py <config.yaml> <template.docx> <output.docx> --config-mode")
        sys.exit(1)

    arg1 = sys.argv[1]
    template_path = sys.argv[2]
    output_path = sys.argv[3] if len(sys.argv) > 3 else 'output.docx'

    # Read data from stdin or file
    if arg1.endswith('.json'):
        with open(arg1, 'r', encoding='utf-8') as f:
            data = _json.load(f)
    elif arg1.endswith('.yaml') or arg1.endswith('.yml'):
        # Config-mode: config yaml + template + output, data from stdin
        config_path = arg1
        if not sys.stdin.isatty():
            data = _json.load(sys.stdin)
        else:
            data = {
                "basicInfo": {
                    "name": "张三", "title": "软件工程师",
                    "phone": "13812345678", "email": "zhangsan@example.com",
                    "summary": "10年软件开发经验"
                },
                "education": [{"school": "清华大学", "major": "计算机科学", "degree": "本科", "date": "2009-2013"}],
                "experience": [{"company": "字节跳动", "role": "高级工程师", "date": "2018-至今", "description": "负责推荐系统开发"}],
                "honors": ["国家奖学金", "ACM竞赛金奖"],
                "skills": ["Python", "Java", "Go"]
            }
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        success = fill(template_path, config, data, output_path)
        print(f"{'OK' if success else 'WARN'}: {output_path}")
        sys.exit(0 if success else 1)
    else:
        print(f"Unknown arg: {arg1}", file=sys.stderr)
        sys.exit(1)

    # JSON data mode: use fill_with_fallback
    layout_adjustments = None
    if len(sys.argv) > 4:
        layout_adj_path = sys.argv[4]
        if os.path.exists(layout_adj_path):
            try:
                with open(layout_adj_path, 'r', encoding='utf-8') as f:
                    layout_adjustments = _json.load(f)
            except Exception as le:
                print(f"Error loading layout adjustments: {le}", file=sys.stderr)

    success = fill_with_fallback(template_path, data, output_path, layout_adjustments)
    print(f"{'OK' if success else 'WARN'}: {output_path}")
    sys.exit(0 if success else 1)
