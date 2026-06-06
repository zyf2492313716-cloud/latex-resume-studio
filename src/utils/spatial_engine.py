import os
import sys
import re
import zipfile
import io

# 动态引入嵌入的依赖库目录
_libs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'libs')
if os.path.exists(_libs_path):
    sys.path.insert(0, _libs_path)

import lxml.etree as ET

NS_W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS_WP = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
NS_V = 'urn:schemas-microsoft-com:vml'
XML_NS = 'http://www.w3.org/XML/1998/namespace'


def _get_bundled_templates_dir():
    """Return bundled templates dir in dev (project/templates) or packaged resources."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.abspath(os.path.join(here, '..', 'templates')),
        os.path.abspath(os.path.join(here, '..', '..', 'templates')),
    ]
    for d in candidates:
        if os.path.isdir(d):
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
    """Apply uploaded portrait replacement for spatial engine outputs."""
    try:
        photo_value = (data or {}).get('basicInfo', {}).get('photo', '')
        if not photo_value:
            return None
        from photo_replace import replace_photo_in_docx
        result = replace_photo_in_docx(output_path, photo_value)
        if result.get('replaced'):
            print(f"photo_replace:OK:{','.join(result.get('replaced_media', []))}", file=sys.stderr)
        else:
            print(f"photo_replace:WARN:{'|'.join(result.get('warnings', [])) or 'unknown'}", file=sys.stderr)
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
        if parent.tag == f'{{{NS_W}}}r':
            return parent
        parent = parent.getparent()
    return None


def _ensure_run_font_size(run, half_points='16'):
    if run is None:
        return
    rPr = run.find(f'{{{NS_W}}}rPr')
    if rPr is None:
        rPr = ET.Element(f'{{{NS_W}}}rPr')
        run.insert(0, rPr)
    for tag in ('sz', 'szCs'):
        node = rPr.find(f'{{{NS_W}}}{tag}')
        if node is None:
            node = ET.Element(f'{{{NS_W}}}{tag}')
            rPr.append(node)
        node.set(f'{{{NS_W}}}val', half_points)


def _write_text_node_with_breaks(t_node, value):
    value = '' if value is None else str(value)
    parts = value.split('\n')
    t_node.text = parts[0]
    _set_xml_space_if_needed(t_node, parts[0])

    parent = t_node.getparent()
    if len(parts) > 1 and parent is not None:
        insert_at = parent.index(t_node) + 1
        for part in parts[1:]:
            br = ET.Element(f'{{{NS_W}}}br')
            new_t = ET.Element(f'{{{NS_W}}}t')
            new_t.text = part
            _set_xml_space_if_needed(new_t, part)
            parent.insert(insert_at, br)
            insert_at += 1
            parent.insert(insert_at, new_t)
            insert_at += 1

    if '@' in value and len(value) > 18:
        _ensure_run_font_size(_find_parent_run(t_node), '16')

# 全局板块关键字
SECTION_PATTERNS = {
    'education': ['教育背景', '教育经历', '修业背景', '教育', 'EDUCATION', 'Education'],
    'experience': ['工作经历', '工作经验', '实习经历', '工作实践', '工作', 'EXPERIENCE', 'Experience', 'JOB EXPERIENCE', '实习实践'],
    'projects': ['项目经验', '项目经历', '专研项目', '项目', 'PROJECTS', 'Projects'],
    'studentWork': ['校内实践', '在校经历', '社团经历', '学生活动', '学生工作', '实践经验'],
    'honors': ['荣誉证书', '荣誉奖项', '证书奖励', '个人荣誉', '获奖经历', '奖项荣誉', '资格证书', '荣誉AWARDS', 'AWARDS'],
    'skills': ['专业技能', '职业技能', '掌握技能', '技能特长', '技能证书', '技能', 'SKILLS', 'Skills'],
    'summary': ['自我评价', '个人介绍', '个人总结', '自我介绍', '个人陈述', '个人简介', '关于我', 'INTRODUCTION'],
    'interests': ['兴趣爱好', '兴趣', '爱好'],
}

# 基础信息已知占位名字
ALL_KNOWN_NAMES = [
    '宋艾嘉', '肖颖馨', '韩志弘', '李自强', '张三', '李四', '王五',
    '赵六', '关睢尔', '陈小明', '刘小红', '周洁', '吴芳',
    '白晓云', '王若琳', '沈慧美', '林晓歌', '林月明', '柳云萧',
    '苏语凝', '钟小艾', '冯青', '张小泉', '云海', '陈知页',
    '孟子君', '孟晓思', '关月兰', '刘璇凯', '张全峰', '张悦然',
    '张晓龙', '张璐瑶', '张筱婕', '张语敏', '张韵艺', '文如菁',
    '林丹阳', '林博文', '林宇凡', '李元茹', '李小冉', '柳元青',
    '梁静', '王宇凡', '王晓峰', '王灵筠', '王菲', '王雅丹',
    '田筱雨', '艾明远', '高凌云', '黄怡佳', '郭洁', '陈洁',
    '顾元昊', '刘诗芸', '刘明', '周芳', '陆然', '杨阳',
    '张宇帆', '张莜婕', '朗云', '赵晓', '林萧', '庄晓', '乔彬',
    '简晓云', '陈韵竹', '林悦然', '周子琪', '张雨涵', '李明轩',
    '王思远', '刘子涵', '赵雨萱', '孙梦琪', '周雅婷', '吴晓峰',
    '郑思远', '黄子轩', '林雅琪', '陈思远', '张雅婷', '李雨涵',
    '王梦琪', '刘子轩', '赵雅婷', '孙雨涵', '周子轩', '吴雅琪',
    '郑雨萱', '黄梦琪', '林子轩', '陈雅婷', '张思远', '李雅琪',
    '王雨萱', '刘梦琪', '赵子轩', '孙雅婷', '周雨涵', '吴思远',
    '郑雅婷', '黄雨涵', '林梦琪', '陈子轩', '张子涵', '李子轩',
    '王雅婷', '刘雅琪', '赵思远', '孙子轩', '周梦琪', '吴子涵',
    '郑子轩', '黄雅婷', '林雨涵', '陈雨萱', '林宇凡', '赵晓',
    '张 芸', '刘 璇', '庄 晓', '乔 彬', '林 萧', '知页', '陈知页',
    '谢云', '谢 云', '李思', '李 思', '朱七七', '朱 七七',
]

def parse_pt_to_emu(val_str):
    """Parse pt/in/cm/mm style value and return EMU."""
    if not val_str:
        return 0
    match = re.match(r'([\d.-]+)(pt|in|cm|mm)?', val_str.strip())
    if not match:
        try:
            # 无单位默认为 dxa (1 dxa = 635 EMU)
            return int(float(val_str.strip()) * 635)
        except ValueError:
            return 0
    val = float(match.group(1))
    unit = match.group(2)
    if unit == 'pt':
        return int(val * 12700)
    elif unit == 'in':
        return int(val * 914400)
    elif unit == 'cm':
        return int(val * 360000)
    elif unit == 'mm':
        return int(val * 36000)
    else:
        return int(val * 635)


class SpatialFiller:
    def __init__(self, template_path: str, data: dict):
        self.template_path = template_path
        self.data = data
        self.warnings = []
        self.base_name = os.path.basename(template_path).replace('.docx', '').replace('.docxtpl', '')

        with zipfile.ZipFile(template_path, 'r') as z:
            self.doc_xml = z.read('word/document.xml').decode('utf-8')
        
        self.root = ET.fromstring(self.doc_xml.encode('utf-8'))

        # Load YAML config to expand known names dynamically
        self.known_names = list(ALL_KNOWN_NAMES)
        yaml_path = template_path.replace('.docx', '.yaml').replace('.docxtpl.docx', '.yaml')
        if not os.path.exists(yaml_path):
            bundled_dir = _get_bundled_templates_dir()
            alt_yaml = os.path.join(bundled_dir, os.path.basename(yaml_path))
            if os.path.exists(alt_yaml):
                yaml_path = alt_yaml

        if os.path.exists(yaml_path):
            try:
                import yaml
                with open(yaml_path, 'r', encoding='utf-8') as f:
                    yaml_config = yaml.safe_load(f) or {}
                # Extract custom name keywords
                name_cfg = yaml_config.get('basic_info', {}).get('fields', {}).get('name', {})
                if name_cfg and 'keywords' in name_cfg:
                    for kw in name_cfg['keywords']:
                        if kw not in self.known_names:
                            self.known_names.append(kw)
                        # Also add with space removed if applicable
                        kw_clean = kw.replace(" ", "")
                        if kw_clean not in self.known_names:
                            self.known_names.append(kw_clean)
            except Exception:
                pass
        
    def _extract_textboxes(self):
        """Extract all non-empty textboxes and map their coordinates (EMU) and sizes, along with font properties."""
        txbxs = []
        for txbx in self.root.iter(f'{{{NS_W}}}txbxContent'):
            # Extract own text
            texts = []
            for t in txbx.iter(f'{{{NS_W}}}t'):
                if t.text:
                    texts.append(t.text)
            full_text = "".join(texts).strip()
            if not full_text:
                continue
                
            x, y, w, h = None, None, None, None
            
            # 1. Check if nested in drawing anchor
            parent = txbx.getparent()
            drawing_node = None
            while parent is not None:
                if parent.tag == f'{{{NS_W}}}drawing':
                    drawing_node = parent
                    break
                parent = parent.getparent()
                
            if drawing_node is not None:
                anchor = drawing_node.find(f'{{{NS_WP}}}anchor')
                if anchor is not None:
                    pos_h = anchor.find(f'{{{NS_WP}}}positionH')
                    pos_v = anchor.find(f'{{{NS_WP}}}positionV')
                    offset_h = pos_h.find(f'{{{NS_WP}}}posOffset') if pos_h is not None else None
                    offset_v = pos_v.find(f'{{{NS_WP}}}posOffset') if pos_v is not None else None
                    if offset_h is not None and offset_h.text:
                        x = int(offset_h.text)
                    if offset_v is not None and offset_v.text:
                        y = int(offset_v.text)
                    
                    extent = anchor.find(f'{{{NS_WP}}}extent')
                    if extent is not None:
                        w = int(extent.get('cx', '0'))
                        h = int(extent.get('cy', '0'))
            
            # 2. Check VML shape if drawing didn't yield coordinates
            if x is None or y is None:
                parent = txbx.getparent()
                shape_node = None
                while parent is not None:
                    if parent.tag == f'{{{NS_V}}}shape':
                        shape_node = parent
                        break
                    parent = parent.getparent()
                    
                if shape_node is not None:
                    style = shape_node.get('style', '')
                    style_dict = {}
                    for item in style.split(';'):
                        if ':' in item:
                            parts = item.split(':', 1)
                            style_dict[parts[0].strip().lower()] = parts[1].strip()
                    
                    margin_left = style_dict.get('margin-left') or style_dict.get('left')
                    margin_top = style_dict.get('margin-top') or style_dict.get('top')
                    if margin_left:
                        x = parse_pt_to_emu(margin_left)
                    if margin_top:
                        y = parse_pt_to_emu(margin_top)
                        
                    width_str = style_dict.get('width')
                    height_str = style_dict.get('height')
                    if width_str:
                        w = parse_pt_to_emu(width_str)
                    if height_str:
                        h = parse_pt_to_emu(height_str)
            
            # Extract basic font properties for frontend interactive rendering
            font_size = 10.5
            color = '#333333'
            bold = False
            align = 'left'
            
            jc = txbx.find(f'.//{{{NS_W}}}jc')
            if jc is not None and jc.get(f'{{{NS_W}}}val'):
                val = jc.get(f'{{{NS_W}}}val')
                if val in ['left', 'right', 'center']:
                    align = val
                elif val == 'both':
                    align = 'justify'
            
            r = txbx.find(f'.//{{{NS_W}}}r')
            if r is not None:
                rPr = r.find(f'{{{NS_W}}}rPr')
                if rPr is not None:
                    sz = rPr.find(f'{{{NS_W}}}sz')
                    if sz is not None and sz.get(f'{{{NS_W}}}val'):
                        try:
                            font_size = float(sz.get(f'{{{NS_W}}}val')) / 2.0
                        except ValueError:
                            pass
                    color_node = rPr.find(f'{{{NS_W}}}color')
                    if color_node is not None and color_node.get(f'{{{NS_W}}}val'):
                        c_val = color_node.get(f'{{{NS_W}}}val')
                        color = '#000000' if c_val == 'auto' else f'#{c_val}'
                    b = rPr.find(f'{{{NS_W}}}b')
                    if b is not None:
                        bold = True

            # Calculate path ID
            xpath = self.root.getroottree().getpath(txbx)
            
            txbxs.append({
                'node': txbx,
                'text': full_text,
                'xpath': xpath,
                'x': x if x is not None else 0,
                'y': y if y is not None else 0,
                'w': w if w is not None else 2286000,  # default ~180pt
                'h': h if h is not None else 1270000,  # default ~100pt
                'fontSize': font_size,
                'color': color,
                'bold': bold,
                'align': align
            })
            
        return txbxs

    def _cluster_columns(self, txbxs):
        """Perform 1D DBSCAN-like clustering on X coordinates."""
        if not txbxs:
            return []

        # Enable global layout sorting only for specific whitelist templates
        global_sorting_whitelist = {"文艺单页10", "文艺单页12", "稳重单页06", "稳重单页12", "稳重单页20", "简约单页25"}
        if hasattr(self, 'base_name') and self.base_name in global_sorting_whitelist:
            return [txbxs]

        # Sort by X axis
        sorted_txbxs = sorted(txbxs, key=lambda d: d['x'])
        columns = []
        current_col = [sorted_txbxs[0]]
        threshold = 1000000  # 约 2.7 cm
        
        for item in sorted_txbxs[1:]:
            if item['x'] - current_col[-1]['x'] < threshold:
                current_col.append(item)
            else:
                columns.append(current_col)
                current_col = [item]
        columns.append(current_col)
        return columns

    def _is_basic_info_box(self, text):
        for name in self.known_names:
            if name in text:
                return True
        text_no_space = re.sub(r'[\s\-–—]+', '', text)
        if re.search(r'1[3-9]\d{9}', text_no_space):
            return True
        if re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]*\.[a-zA-Z]{2,}', text):
            return True
        for prefix in ['微信', 'wechat', 'QQ', '地址', 'address', '求职意向', '应聘职位']:
            if prefix in text and len(text) < 40:
                return True
        return False

    def _parse_inline_header(self, text):
        """Detect if header and content are in the same text block."""
        for sec_type, patterns in SECTION_PATTERNS.items():
            for pat in patterns:
                # Header must be at the beginning of the text block
                if text.startswith(pat):
                    # Strict length / suffix check: e.g. "教育背景\n学校名称" or "教育背景 华中师大"
                    rest = text[len(pat):].strip()
                    if rest:
                        return sec_type, pat, rest
                    else:
                        return sec_type, pat, ""
        return None, None, None

    def fill(self, output_path: str, layout_adjustments: dict = None) -> bool:
        if layout_adjustments:
            self._apply_layout_adjustments(layout_adjustments)
            
        txbxs = self._extract_textboxes()
        if not txbxs:
            self.warnings.append("No absolute layout textboxes found.")
            return False

        if self._fill_template_specific(txbxs):
            self._write_output_docx(output_path)
            _cleanup_docx_preview_artifacts(output_path)
            _apply_photo_replacement_if_needed(output_path, self.data)
            return True

        columns = self._cluster_columns(txbxs)
        basic = self.data.get('basicInfo', {})
        
        # Track filled textbox nodes to prevent double replacement
        filled_nodes = set()

        # Gather user sections
        edus = self.data.get('education', [])
        exps = self.data.get('experience', [])
        projs = self.data.get('projects', [])
        sw_list = self.data.get('studentWork', [])
        honors = self.data.get('honors', [])
        skills = self.data.get('skills', [])

        # Process columns to identify section blocks
        for ci, col in enumerate(columns):
            # Sort boxes in the same column by Y coordinate (top-to-bottom)
            sorted_boxes = sorted(col, key=lambda d: d['y'])
            
            # Scan to find headers and group subsequent boxes under them
            current_section = None
            section_boxes = []
            
            for box in sorted_boxes:
                full_txt = box['text']
                node = box['node']
                
                # Check for explicit standalone header
                is_header = False
                for sec_type, patterns in SECTION_PATTERNS.items():
                    if full_txt in patterns and len(full_txt) < 15:
                        # Found a standalone header box
                        if current_section and section_boxes:
                            self._fill_section_boxes(current_section, section_boxes, filled_nodes)
                        current_section = sec_type
                        section_boxes = []
                        is_header = True
                        filled_nodes.add(node)  # Do not modify header box text
                        break
                        
                if is_header:
                    continue
                    
                if self._is_basic_info_box(full_txt):
                    continue
                    
                # Check for inline header (header + content in same box)
                sec_type, pat, rest = self._parse_inline_header(full_txt)
                if sec_type:
                    # Fill the previous section first
                    if current_section and section_boxes:
                        self._fill_section_boxes(current_section, section_boxes, filled_nodes)
                    
                    # Split this inline box into header part and content part
                    # Modify this node's text by replacing the content portion
                    content_val = self._format_inline_section_value(sec_type)
                    if content_val:
                        # Keep the header text prefix
                        separator = "\n" if "\n" in full_txt else " "
                        self._replace_textbox_text(node, f"{pat}{separator}{content_val}")
                        filled_nodes.add(node)
                    
                    # Reset section context
                    current_section = None
                    section_boxes = []
                    continue
                
                # If currently inside a section, accumulate content boxes
                if current_section:
                    section_boxes.append(box)
                    
            # Fill the last accumulated section of the column
            if current_section and section_boxes:
                self._fill_section_boxes(current_section, section_boxes, filled_nodes)

        # --- Phase 2: Global Basic Info & Fallback Keyword Scan ---
        # Any box not claimed by a major section, or matches regex
        label_prefixes = {
            '姓名': 'name', '名字': 'name', 'Name': 'name',
            '手机': 'phone', '电话': 'phone', '电话号码': 'phone', 'Phone': 'phone',
            '邮箱': 'email', 'Email': 'email', 'E-mail': 'email', '邮箱地址': 'email',
            '微信': 'wechat', 'WeChat': 'wechat', 'QQ': 'wechat',
            '地址': 'address', 'Address': 'address',
            '求职意向': 'title', '目标职位': 'title', '应聘职位': 'title', 'Job Target': 'title',
        }

        for box in txbxs:
            node = box['node']
            if node in filled_nodes:
                continue
            txt = box['text']
            
            modified = False
            new_txt = txt

            # 0. Replace based on label_prefixes (e.g. 姓名：朱七七)
            for prefix, field in label_prefixes.items():
                val = basic.get(field)
                if not val:
                    continue
                prefix_pat = r'\s*'.join(list(prefix)) # e.g. 姓\s*名
                match_colon = re.search(r'(' + prefix_pat + r')\s*[：:]\s*(.+)', new_txt)
                if match_colon:
                    raw_val = match_colon.group(2).strip()
                    if raw_val and raw_val != val and len(raw_val) < 50:
                        start_idx = match_colon.start(2)
                        end_idx = match_colon.end(2)
                        new_txt = new_txt[:start_idx] + val + new_txt[end_idx:]
                        modified = True
                        break
            
            # 1. Replace phone numbers (e.g. 13800138000, 152 0032 0007, 138-0000-0000)
            if basic.get('phone'):
                mapping = []
                text_no_space = ""
                for idx, char in enumerate(new_txt):
                    if char not in " \t\n\r-–—":
                        mapping.append(idx)
                        text_no_space += char
                
                match = re.search(r'1[3-9]\d{8,9}', text_no_space)
                if match:
                    start_no_space, end_no_space = match.start(), match.end()
                    start_orig = mapping[start_no_space]
                    end_orig = mapping[end_no_space - 1] + 1
                    new_txt = new_txt[:start_orig] + basic['phone'] + " " + new_txt[end_orig:]
                    modified = True
                    
            # 2. Replace email addresses
            if basic.get('email'):
                email_pat = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
                if re.search(email_pat, new_txt):
                    new_txt = re.sub(email_pat, basic['email'], new_txt)
                    modified = True
                    
            # 3. Replace known placeholder names
            if basic.get('name'):
                for name in self.known_names:
                    if name in new_txt:
                        new_txt = new_txt.replace(name, basic['name'])
                        modified = True
                        break
                        
            # 4. Replace placeholder titles
            if basic.get('title'):
                for title in ['平面设计', '网页设计师', '美术主编', 'UI设计师', '销售员岗位']:
                    if title in new_txt:
                        new_txt = new_txt.replace(title, basic['title'])
                        modified = True
                        break

            if modified:
                self._replace_textbox_text(node, new_txt)
                filled_nodes.add(node)

        # Ensure templates without explicit phone/email placeholders still expose contact info.
        current_text = ''.join(t.text or '' for t in self.root.iter(f'{{{NS_W}}}t'))
        missing_contact_parts = []
        if basic.get('phone') and basic['phone'] not in current_text:
            missing_contact_parts.append(basic['phone'])
        if basic.get('email') and basic['email'] not in current_text:
            missing_contact_parts.append(basic['email'])
        if missing_contact_parts:
            contact_text = ' | '.join(missing_contact_parts)
            contact_box = None
            for box in reversed(txbxs):
                txt = box['text']
                if any(k in txt for k in ['电话', '手机', '邮箱', 'Email', '联系方式', '联系', '岁|', '期望地点', '地址']):
                    contact_box = box
                    break
            if contact_box is None:
                for box in txbxs:
                    if box['node'] not in filled_nodes and self._is_basic_info_box(box['text']):
                        contact_box = box
                        break
            if contact_box is not None:
                self._replace_textbox_text(contact_box['node'], contact_text)
                filled_nodes.add(contact_box['node'])

        # Final guard: if a grouped basic-info textbox swallowed the email run, append it to the phone line.
        final_text = ''.join(t.text or '' for t in self.root.iter(f'{{{NS_W}}}t'))
        if basic.get('email') and basic['email'] not in final_text:
            for t in self.root.iter(f'{{{NS_W}}}t'):
                if t.text and ((basic.get('phone') and basic['phone'] in t.text) or '手机' in t.text or '电话' in t.text):
                    t.text = t.text.rstrip() + ' | ' + basic['email']
                    _ensure_run_font_size(_find_parent_run(t), '16')
                    break

        self._write_output_docx(output_path)

        _cleanup_docx_preview_artifacts(output_path)
        _apply_photo_replacement_if_needed(output_path, self.data)
        return len(filled_nodes) > 0

    def _write_output_docx(self, output_path: str):
        """Save current document.xml back into a DOCX, preserving all other parts."""
        modified_xml = ET.tostring(self.root, encoding='unicode')
        buffer = io.BytesIO()
        with zipfile.ZipFile(self.template_path, 'r') as zin:
            with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data_in = zin.read(item.filename)
                    if item.filename == 'word/document.xml':
                        data_in = modified_xml.encode('utf-8')
                    zout.writestr(item, data_in)

        with open(output_path, 'wb') as f:
            f.write(buffer.getvalue())

    def _format_basic_title_line(self):
        basic = self.data.get('basicInfo', {})
        name = basic.get('name', '').strip()
        title = basic.get('title', '').strip()
        if name and title:
            return f"{name} 求职意向：{title}"
        return name or title

    def _format_contact_block(self):
        basic = self.data.get('basicInfo', {})
        parts = []
        for key in ('phone', 'email', 'wechat', 'github'):
            val = (basic.get(key) or '').strip()
            if val:
                parts.append(val)
        return '\n'.join(parts)

    def _format_basic_details_block(self):
        basic = self.data.get('basicInfo', {})
        edu = (self.data.get('education') or [{}])[0] if self.data.get('education') else {}
        lines = []
        for label, value in [
            ('学历', basic.get('degree') or edu.get('degree')),
            ('专业', basic.get('major') or edu.get('major')),
            ('学校', edu.get('school')),
            ('籍贯', basic.get('address')),
        ]:
            if value:
                lines.append(f"{label}：{value}")
        return '\n'.join(lines)

    def _format_description_lines(self, text):
        if not text:
            return ''
        parts = [p.strip() for p in re.split(r'[\n；;]+', str(text)) if p.strip()]
        return '\n'.join(('• ' + p if not p.startswith(('•', '-', '✓', '✔')) else p) for p in parts)

    def _format_entries_block(self, sec_type, max_items=2):
        items = self.data.get(sec_type, []) or []
        blocks = []
        for item in items[:max_items]:
            if sec_type == 'education':
                head = '    '.join(p for p in [item.get('date', ''), item.get('school', ''), ' '.join(p for p in [item.get('major', ''), f"({item.get('degree')})" if item.get('degree') else ''] if p)] if p)
                desc = self._format_description_lines(item.get('description', ''))
            elif sec_type == 'experience':
                head = '    '.join(p for p in [item.get('date', ''), item.get('company', ''), item.get('role', '')] if p)
                desc = self._format_description_lines(item.get('description', ''))
            elif sec_type == 'projects':
                head = '    '.join(p for p in [item.get('date', ''), item.get('name', ''), item.get('role', '')] if p)
                desc = self._format_description_lines(item.get('description', ''))
            else:
                head = '    '.join(p for p in [item.get('date', ''), item.get('organization', ''), item.get('role', '')] if p)
                desc = self._format_description_lines(item.get('description', ''))
            block = head
            if desc:
                block = (block + '\n' if block else '') + desc
            if block:
                blocks.append(block)
        return '\n\n'.join(blocks)

    def _format_honors_or_skills_block(self):
        honors = self.data.get('honors') or []
        skills = self.data.get('skills') or []
        if honors:
            return '\n'.join(('• ' + h if not h.startswith(('•', '-', '*')) else h) for h in honors)
        if skills:
            return '\n'.join(('• ' + s if not s.startswith(('•', '-', '*')) else s) for s in skills)
        return ''

    def _fill_template_specific(self, txbxs) -> bool:
        """High-confidence repairs for templates whose visible text boxes need whole-block replacement.

        These templates use duplicated VML/DrawingML text boxes.  Keyword-level
        replacement can leave dates, age/address defaults, or long placeholder
        paragraphs visible.  Replacing the whole semantic text box gives a much
        closer Word result and makes visual validation meaningful.
        """
        if self.base_name not in {'文艺单页03', '文艺单页04'}:
            return False

        basic = self.data.get('basicInfo', {})
        summary = (basic.get('summary') or self.data.get('summary') or '').strip()
        changed = False

        for box in txbxs:
            txt = box['text']
            node = box['node']
            replacement = None

            if self.base_name == '文艺单页03':
                if '钟小艾' in txt:
                    replacement = basic.get('name', '')
                elif txt.startswith('求职意向'):
                    title = basic.get('title', '').strip()
                    replacement = f"求职意向：{title}" if title else ''
                elif '出生日期' in txt or 'Xiaowangzi' in txt or '180-5505-0900' in txt:
                    replacement = self._format_contact_block()
                elif txt in {'教育背景', '实习经历', '获奖证书', '自我评价'}:
                    replacement = None
                elif '华南师范' in txt or '2012.09-2016.05' in txt:
                    replacement = self._format_entries_block('education', 1)
                elif '英语培训机构' in txt or '2014.07-2015.09' in txt:
                    replacement = self._format_entries_block('experience', 1)
                elif '通过CET6' in txt or '国家奖学金' in txt:
                    replacement = self._format_honors_or_skills_block()
                elif '尊敬他人' in txt or '团队精神' in txt:
                    replacement = summary

            elif self.base_name == '文艺单页04':
                if '乔 彬' in txt or '求职意向：财务会计' in txt:
                    replacement = self._format_basic_title_line()
                elif txt in {'联系方式', '基本资料', '关于我', '教育背景', '工作经验'}:
                    replacement = None
                elif '21岁' in txt or '138-8888-8888' in txt or '13888123@qq.com' in txt:
                    replacement = self._format_contact_block()
                elif '性别：' in txt and '籍贯' in txt:
                    replacement = self._format_basic_details_block()
                elif '个人方面' in txt or '工作态度' in txt:
                    replacement = summary
                elif '湖北十堰大学' in txt or '毕业院校' in txt or '专业课程' in txt:
                    replacement = self._format_entries_block('education', 1)
                elif '深圳科技网络公司' in txt or '产品运营总监' in txt or txt.startswith('时间：2013.8'):
                    replacement = self._format_entries_block('experience', 2)

            if replacement is not None:
                self._replace_textbox_text(node, replacement)
                changed = True

        return changed

    def _replace_textbox_text(self, txbx_node, value):
        """Replace all text in a textbox with value, preserving line breaks without empty bullet paragraphs."""
        t_nodes = list(tbx_node_iter for tbx_node_iter in txbx_node.iter(f'{{{NS_W}}}t'))
        if not t_nodes:
            return

        first_t = t_nodes[0]
        first_para = first_t.getparent()
        while first_para is not None and first_para.tag != f'{{{NS_W}}}p':
            first_para = first_para.getparent()

        if first_para is not None:
            for p in list(txbx_node.findall(f'{{{NS_W}}}p')):
                if p is not first_para:
                    txbx_node.remove(p)
            t_nodes = list(first_para.iter(f'{{{NS_W}}}t'))
            first_t = t_nodes[0] if t_nodes else first_t

        _write_text_node_with_breaks(first_t, value)
        for t in t_nodes[1:]:
            t.text = ""

    def _format_inline_section_value(self, sec_type):
        """Format a list section as a single string for inline textbox replacement."""
        items = self.data.get(sec_type, [])
        if not items:
            return ""
        lines = []
        for item in items[:2]: # Max 2 entries to fit inline textbox space
            if sec_type == 'education':
                lines.append(f"{item.get('school', '')} | {item.get('major', '')} ({item.get('degree', '')})  {item.get('date', '')}")
            elif sec_type == 'experience':
                lines.append(f"{item.get('company', '')} | {item.get('role', '')}  {item.get('date', '')}")
            elif sec_type == 'projects':
                lines.append(f"{item.get('name', '')} | {item.get('role', '')}  {item.get('date', '')}")
        return "\n".join(lines)

    def _fill_section_boxes(self, sec_type, boxes, filled_nodes):
        """Align data array entries sequentially into sorted content boxes."""
        if sec_type == 'summary':
            val = self.data.get('basicInfo', {}).get('summary', '') or self.data.get('summary', '')
            data_list = [val] if val else []
        else:
            data_list = self.data.get(sec_type, [])

        if not data_list:
            # Clear placeholder contents if user has no data for this section
            for box in boxes:
                self._replace_textbox_text(box['node'], "")
                filled_nodes.add(box['node'])
            return

        # Special simple replace for honors / skills / interests / summary (non-structural lists)
        if sec_type in ('honors', 'skills', 'interests', 'summary'):
            formatted_text = ""
            if sec_type == 'honors':
                formatted_text = '\n'.join('• ' + h if not h.startswith('•') and not h.startswith('-') else h for h in data_list)
            elif sec_type == 'skills':
                formatted_text = '；'.join(data_list)
            elif sec_type == 'summary':
                val = data_list[0]
                formatted_text = val if isinstance(val, str) else '\n'.join(val)
            else:
                formatted_text = '\n'.join(data_list)
                
            if boxes:
                # Put all text in the first box, clear rest
                self._replace_textbox_text(boxes[0]['node'], formatted_text)
                filled_nodes.add(boxes[0]['node'])
                for b in boxes[1:]:
                    self._replace_textbox_text(b['node'], "")
                    filled_nodes.add(b['node'])
            return

        # Structural sections: education, experience, projects, studentWork
        section_fields = {
            'education': ['school', 'major', 'degree', 'date'],
            'experience': ['company', 'role', 'date', 'description'],
            'projects': ['name', 'role', 'date', 'description'],
            'studentWork': ['organization', 'role', 'date', 'description']
        }
        fields_list = section_fields.get(sec_type, [])

        # We group boxes that belong to the same entry index based on Y distance
        entry_threshold = 720000 # 2 cm Y-gap
        boxes_by_y = sorted(boxes, key=lambda d: d['y'])
        
        entries_boxes = []
        current_entry = [boxes_by_y[0]]
        for box in boxes_by_y[1:]:
            if box['y'] - current_entry[-1]['y'] < entry_threshold:
                current_entry.append(box)
            else:
                entries_boxes.append(current_entry)
                current_entry = [box]
        entries_boxes.append(current_entry)

        # Map user data items into horizontal/vertical groups
        for entry_idx, user_item in enumerate(data_list):
            if entry_idx >= len(entries_boxes):
                break
            
            entry_box_group = entries_boxes[entry_idx]
            
            assigned_fields = {}  # field -> node
            unassigned_nodes = []  # list of nodes
            
            # Phase 1: Semantic identification
            for box in entry_box_group:
                node = box['node']
                txt = box['text']
                field_matched = None
                
                if sec_type == 'education':
                    if any(w in txt for w in ['大学', '学院', '学校', '吉林', '华中', '复旦', '十堰', '美院']):
                        field_matched = 'school'
                    elif any(w in txt for w in ['专业', '工程', '设计', '管理', '学制', '传播', '媒体']):
                        field_matched = 'major'
                    elif any(w in txt for w in ['本科', '硕士', '博士', '学历', '学位', '专科', '学位证']):
                        field_matched = 'degree'
                    elif any(w in txt for w in ['年', '月', '-', '201', '202', '至今']):
                        field_matched = 'date'
                elif sec_type == 'experience':
                    if any(w in txt for w in ['公司', '网络', '科技', '企业', '有限', '医院', '出版社', '单位', '传媒']):
                        field_matched = 'company'
                    elif any(w in txt for w in ['助理', '经理', '策划', '主管', '专员', '设计师', '编辑', '插画师', '实习生', '角色', '职位', '职责']):
                        field_matched = 'role'
                    elif any(w in txt for w in ['年', '月', '-', '201', '202', '至今']):
                        field_matched = 'date'
                    elif len(txt) > 20:
                        field_matched = 'description'
                elif sec_type == 'projects':
                    if any(w in txt for w in ['项目', '系统', '平台', '设计', '课题', '研究', '软件']):
                        field_matched = 'name'
                    elif any(w in txt for w in ['负责人', '核心', '开发', '研究员', '角色', '职责']):
                        field_matched = 'role'
                    elif any(w in txt for w in ['年', '月', '-', '201', '202', '至今']):
                        field_matched = 'date'
                    elif len(txt) > 20:
                        field_matched = 'description'
                elif sec_type == 'studentWork':
                    if any(w in txt for w in ['学生会', '社团', '协会', '团委', '办公室', '研究中心', '部']):
                        field_matched = 'organization'
                    elif any(w in txt for w in ['部长', '会长', '干事', '主席', '助理', '副部长', '角色', '职责']):
                        field_matched = 'role'
                    elif any(w in txt for w in ['年', '月', '-', '201', '202', '至今']):
                        field_matched = 'date'
                    elif len(txt) > 15:
                        field_matched = 'description'

                if field_matched and field_matched in fields_list and field_matched not in assigned_fields:
                    assigned_fields[field_matched] = node
                else:
                    unassigned_nodes.append(node)

            # Phase 2: Deductive / Fallback assignment
            for f in fields_list:
                if f not in assigned_fields and user_item.get(f):
                    if unassigned_nodes:
                        node = unassigned_nodes.pop(0)
                        assigned_fields[f] = node

            # Phase 3: Text replacement
            for f, node in assigned_fields.items():
                val = str(user_item.get(f, ''))
                self._replace_textbox_text(node, val)
                filled_nodes.add(node)

            # Clear remaining unassigned boxes inside the group to prevent template text leak
            for node in unassigned_nodes:
                self._replace_textbox_text(node, "")
                filled_nodes.add(node)

        # Clear remaining unused entry boxes
        for i in range(len(data_list), len(entries_boxes)):
            for box in entries_boxes[i]:
                self._replace_textbox_text(box['node'], "")
                filled_nodes.add(box['node'])


    def _apply_layout_adjustments(self, adjustments):
        """Apply frontend layout coordinates adjustments to Document XML."""
        EMU_PER_PX_X = 7560000 / 595.0
        EMU_PER_PX_Y = 10692000 / 842.0
        
        namespaces = {k: v for k, v in self.root.nsmap.items() if k is not None}
        defaults = {
            'w': NS_W,
            'mc': 'http://schemas.openxmlformats.org/markup-compatibility/2006',
            'wp': NS_WP,
            'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
            'wps': 'http://schemas.openxmlformats.org/officeWord/2010/wordprocessingShape',
            'v': NS_V,
            'o': 'urn:schemas-microsoft-com:office:office',
            'w14': 'http://schemas.microsoft.com/office/word/2010/wordml',
            'w15': 'http://schemas.microsoft.com/office/word/2012/wordml',
            'wp14': 'http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing',
            'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture',
            'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
        }
        for k, v in defaults.items():
            if k not in namespaces:
                namespaces[k] = v
        for xpath, adj in adjustments.items():
            nodes = self.root.xpath(xpath, namespaces=namespaces)
            if not nodes:
                continue
            txbx = nodes[0]
            
            # 1. Update Drawing anchor posOffset & extent if present
            parent = txbx.getparent()
            drawing_node = None
            while parent is not None:
                if parent.tag == f'{{{NS_W}}}drawing':
                    drawing_node = parent
                    break
                parent = parent.getparent()
                
            if drawing_node is not None:
                anchor = drawing_node.find(f'{{{NS_WP}}}anchor')
                if anchor is not None:
                    pos_h = anchor.find(f'{{{NS_WP}}}positionH')
                    pos_v = anchor.find(f'{{{NS_WP}}}positionV')
                    offset_h = pos_h.find(f'{{{NS_WP}}}posOffset') if pos_h is not None else None
                    offset_v = pos_v.find(f'{{{NS_WP}}}posOffset') if pos_v is not None else None
                    extent = anchor.find(f'{{{NS_WP}}}extent')
                    
                    if 'x' in adj and offset_h is not None:
                        offset_h.text = str(int(adj['x'] * EMU_PER_PX_X))
                    if 'y' in adj and offset_v is not None:
                        offset_v.text = str(int(adj['y'] * EMU_PER_PX_Y))
                    if 'w' in adj and extent is not None:
                        extent.set('cx', str(int(adj['w'] * EMU_PER_PX_X)))
                    if 'h' in adj and extent is not None:
                        extent.set('cy', str(int(adj['h'] * EMU_PER_PX_Y)))
                        
            # 2. Update VML shape style if present
            parent = txbx.getparent()
            shape_node = None
            while parent is not None:
                if parent.tag == f'{{{NS_V}}}shape':
                    shape_node = parent
                    break
                parent = parent.getparent()
                
            if shape_node is not None:
                style = shape_node.get('style', '')
                style_dict = {}
                style_keys_case = {}
                for item in style.split(';'):
                    if ':' in item:
                        parts = item.split(':', 1)
                        key = parts[0].strip()
                        val = parts[1].strip()
                        style_dict[key.lower()] = val
                        style_keys_case[key.lower()] = key
                
                if 'x' in adj:
                    pt_val = (adj['x'] * EMU_PER_PX_X) / 12700.0
                    style_dict['margin-left'] = f"{pt_val:.2f}pt"
                if 'y' in adj:
                    pt_val = (adj['y'] * EMU_PER_PX_Y) / 12700.0
                    style_dict['margin-top'] = f"{pt_val:.2f}pt"
                if 'w' in adj:
                    pt_val = (adj['w'] * EMU_PER_PX_X) / 12700.0
                    style_dict['width'] = f"{pt_val:.2f}pt"
                if 'h' in adj:
                    pt_val = (adj['h'] * EMU_PER_PX_Y) / 12700.0
                    style_dict['height'] = f"{pt_val:.2f}pt"
                
                new_style_items = []
                for k, v in style_dict.items():
                    orig_key = style_keys_case.get(k, k)
                    new_style_items.append(f"{orig_key}:{v}")
                shape_node.set('style', ";".join(new_style_items))

            # 3. Update Font Size and Color inside the textbox runs if specified
            if 'fontSize' in adj or 'color' in adj:
                for rPr in txbx.xpath('.//w:rPr', namespaces={'w': NS_W}):
                    if 'fontSize' in adj:
                        half_pts = str(int(round(adj['fontSize'] * 2.0)))
                        sz = rPr.find(f'{{{NS_W}}}sz')
                        if sz is None:
                            sz = ET.Element(f'{{{NS_W}}}sz')
                            rPr.append(sz)
                        sz.set(f'{{{NS_W}}}val', half_pts)
                        
                        szCs = rPr.find(f'{{{NS_W}}}szCs')
                        if szCs is None:
                            szCs = ET.Element(f'{{{NS_W}}}szCs')
                            rPr.append(szCs)
                        szCs.set(f'{{{NS_W}}}val', half_pts)
                        
                    if 'color' in adj:
                        hex_color = adj['color'].replace('#', '').strip()
                        color_node = rPr.find(f'{{{NS_W}}}color')
                        if color_node is None:
                            color_node = ET.Element(f'{{{NS_W}}}color')
                            rPr.append(color_node)
                        color_node.set(f'{{{NS_W}}}val', hex_color)

    def _assign_structural_section_roles(self, sec_type, boxes, assigned_nodes):
        if sec_type in ('honors', 'skills', 'interests', 'summary'):
            if boxes:
                assigned_nodes[boxes[0]['xpath']] = sec_type if sec_type != 'summary' else 'basicInfo.summary'
                for b in boxes[1:]:
                    assigned_nodes[b['xpath']] = f"{sec_type}.unused"
            return

        section_fields = {
            'education': ['school', 'major', 'degree', 'date'],
            'experience': ['company', 'role', 'date', 'description'],
            'projects': ['name', 'role', 'date', 'description'],
            'studentWork': ['organization', 'role', 'date', 'description']
        }
        fields_list = section_fields.get(sec_type, [])

        entry_threshold = 720000
        boxes_by_y = sorted(boxes, key=lambda d: d['y'])
        
        entries_boxes = []
        current_entry = [boxes_by_y[0]]
        for box in boxes_by_y[1:]:
            if box['y'] - current_entry[-1]['y'] < entry_threshold:
                current_entry.append(box)
            else:
                entries_boxes.append(current_entry)
                current_entry = [box]
        entries_boxes.append(current_entry)

        for entry_idx, entry_box_group in enumerate(entries_boxes):
            assigned_fields = {}
            unassigned_nodes = []
            
            for box in entry_box_group:
                txt = box['text']
                xpath = box['xpath']
                field_matched = None
                
                if sec_type == 'education':
                    if any(w in txt for w in ['大学', '学院', '学校', '吉林', '华中', '复旦', '十堰', '美院']):
                        field_matched = 'school'
                    elif any(w in txt for w in ['专业', '工程', '设计', '管理', '学制', '传播', '媒体']):
                        field_matched = 'major'
                    elif any(w in txt for w in ['本科', '硕士', '博士', '学历', '学位', '专科', '学位证']):
                        field_matched = 'degree'
                    elif any(w in txt for w in ['年', '月', '-', '201', '202', '至今']):
                        field_matched = 'date'
                elif sec_type == 'experience':
                    if any(w in txt for w in ['公司', '网络', '科技', '企业', '有限', '医院', '出版社', '单位', '传媒']):
                        field_matched = 'company'
                    elif any(w in txt for w in ['助理', '经理', '策划', '主管', '专员', '设计师', '编辑', '插画师', '实习生', '角色', '职位', '职责']):
                        field_matched = 'role'
                    elif any(w in txt for w in ['年', '月', '-', '201', '202', '至今']):
                        field_matched = 'date'
                    elif len(txt) > 20:
                        field_matched = 'description'
                elif sec_type == 'projects':
                    if any(w in txt for w in ['项目', '系统', '平台', '设计', '课题', '研究', '软件']):
                        field_matched = 'name'
                    elif any(w in txt for w in ['负责人', '核心', '开发', '研究员', '角色', '职责']):
                        field_matched = 'role'
                    elif any(w in txt for w in ['年', '月', '-', '201', '202', '至今']):
                        field_matched = 'date'
                    elif len(txt) > 20:
                        field_matched = 'description'
                elif sec_type == 'studentWork':
                    if any(w in txt for w in ['学生会', '社团', '协会', '团委', '办公室', '研究中心', '部']):
                        field_matched = 'organization'
                    elif any(w in txt for w in ['部长', '会长', '干事', '主席', '助理', '副部长', '角色', '职责']):
                        field_matched = 'role'
                    elif any(w in txt for w in ['年', '月', '-', '201', '202', '至今']):
                        field_matched = 'date'
                    elif len(txt) > 15:
                        field_matched = 'description'

                if field_matched and field_matched in fields_list and field_matched not in assigned_fields:
                    assigned_fields[field_matched] = xpath
                else:
                    unassigned_nodes.append(xpath)

            # Deductive / Fallback assignment for this entry
            for f in fields_list:
                if f not in assigned_fields:
                    if unassigned_nodes:
                        xpath = unassigned_nodes.pop(0)
                        assigned_fields[f] = xpath

            for f, xpath in assigned_fields.items():
                assigned_nodes[xpath] = f"{sec_type}.{entry_idx}.{f}"
                
            for xpath in unassigned_nodes:
                assigned_nodes[xpath] = f"{sec_type}.{entry_idx}.unused"

    def _analyze_roles(self, txbxs):
        """Analyze semantic roles for each textbox using layout structure and placeholder text."""
        columns = self._cluster_columns(txbxs)
        assigned_nodes = {}
        
        for col in columns:
            sorted_boxes = sorted(col, key=lambda d: d['y'])
            current_section = None
            section_boxes = []
            
            for box in sorted_boxes:
                full_txt = box['text']
                xpath = box['xpath']
                
                is_header = False
                for sec_type, patterns in SECTION_PATTERNS.items():
                    if full_txt in patterns and len(full_txt) < 15:
                        current_section = sec_type
                        section_boxes = []
                        is_header = True
                        assigned_nodes[xpath] = f"header.{sec_type}"
                        break
                        
                if is_header:
                    continue
                    
                if self._is_basic_info_box(full_txt):
                    continue
                    
                sec_type, pat, rest = self._parse_inline_header(full_txt)
                if sec_type:
                    if current_section and section_boxes:
                        self._assign_structural_section_roles(current_section, section_boxes, assigned_nodes)
                    assigned_nodes[xpath] = f"{sec_type}.0.inline"
                    current_section = None
                    section_boxes = []
                    continue
                
                if current_section:
                    section_boxes.append(box)
                    
            if current_section and section_boxes:
                self._assign_structural_section_roles(current_section, section_boxes, assigned_nodes)

        label_prefixes = {
            '姓名': 'name', '名字': 'name', 'Name': 'name',
            '手机': 'phone', '电话': 'phone', '电话号码': 'phone', 'Phone': 'phone',
            '邮箱': 'email', 'Email': 'email', 'E-mail': 'email', '邮箱地址': 'email',
            '微信': 'wechat', 'WeChat': 'wechat', 'QQ': 'wechat',
            '地址': 'address', 'Address': 'address',
            '求职意向': 'title', '目标职位': 'title', '应聘职位': 'title', 'Job Target': 'title',
        }

        for box in txbxs:
            xpath = box['xpath']
            if xpath in assigned_nodes:
                continue
                
            txt = box['text']
            
            if re.search(r'1[3-9]\d{8,9}', txt.replace(' ', '')):
                assigned_nodes[xpath] = "basicInfo.phone"
                continue
                
            if re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', txt):
                assigned_nodes[xpath] = "basicInfo.email"
                continue
                
            has_name = False
            for name in self.known_names:
                if name in txt:
                    assigned_nodes[xpath] = "basicInfo.name"
                    has_name = True
                    break
            if has_name:
                continue

            has_title = False
            for title in ['平面设计', '网页设计师', '美术主编', 'UI设计师', '销售员岗位']:
                if title in txt:
                    assigned_nodes[xpath] = "basicInfo.title"
                    has_title = True
                    break
            if has_title:
                continue
                
            has_prefix = False
            for prefix, field in label_prefixes.items():
                prefix_pat = r'\s*'.join(list(prefix))
                if re.search(r'(' + prefix_pat + r')\s*[：:]', txt):
                    assigned_nodes[xpath] = f"basicInfo.{field}"
                    has_prefix = True
                    break
            if has_prefix:
                continue
                
            if any(w in txt for w in ['自我评价', '个人评价', '关于我', '自我介绍']):
                assigned_nodes[xpath] = "basicInfo.summary"
                continue
                
        for box in txbxs:
            box['role'] = assigned_nodes.get(box['xpath'], None)

    def export_layout(self) -> dict:
        """Export coordinates and texts in pixel scale (A4: 595 x 842)."""
        txbxs = self._extract_textboxes()
        self._analyze_roles(txbxs)
        EMU_PER_PX_X = 7560000 / 595.0
        EMU_PER_PX_Y = 10692000 / 842.0
        
        pages_layout = []
        for box in txbxs:
            pages_layout.append({
                'id': box['xpath'],
                'x': int(round(box['x'] / EMU_PER_PX_X)),
                'y': int(round(box['y'] / EMU_PER_PX_Y)),
                'w': int(round(box['w'] / EMU_PER_PX_X)),
                'h': int(round(box['h'] / EMU_PER_PX_Y)),
                'text': box['text'],
                'role': box['role'],
                'fontSize': box['fontSize'],
                'color': box['color'],
                'bold': box['bold'],
                'align': box['align']
            })
        return {
            'width': 595,
            'height': 842,
            'elements': pages_layout
        }


def fill_spatial(template_path: str, data: dict, output_path: str, layout_adjustments: dict = None) -> bool:
    """Convenience endpoint for spatial filling."""
    filler = SpatialFiller(template_path, data)
    return filler.fill(output_path, layout_adjustments)


if __name__ == '__main__':
    import json
    if len(sys.argv) > 2 and sys.argv[1] == '--export-layout':
        template_path = sys.argv[2]
        try:
            filler = SpatialFiller(template_path, {})
            layout_data = filler.export_layout()
            print(json.dumps(layout_data, ensure_ascii=False))
        except Exception as e:
            print(json.dumps({"error": str(e)}))
