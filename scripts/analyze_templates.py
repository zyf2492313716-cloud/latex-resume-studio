"""Analyze all 10 resume template DOCX structures for YAML config generation."""
import zipfile
import xml.etree.ElementTree as ET
import re
import os

NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

TEMPLATE_NAMES = [
    "简约单页01", "稳重单页01", "知页简历01", "知页简历02",
    "文艺单页01", "文艺单页20", "极简单页01", "极简单页02",
    "活泼单页06", "稳重单页02",
]

TEMPLATES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'templates'))

SECTION_HEADERS = [
    '教育背景', '工作经历', '自我评价', '基本信息', '个人信息',
    '专业技能', '荣誉奖项', '证书奖励', '工作经验', '教育经历',
    '在校经历', '实习经历', '实践经历', '联系方式', '掌握技能',
    '个人资料', '个人介绍', '兴趣爱好', '职业技能', '校内实践',
    '获奖经历', '资格证书', '奖项荣誉', '任职参考',
    '教育背景EDUCATION', '实习经历JOB EXPERIENCE',
    '荣誉AWARDS', '荣誉证书',
]

def get_own_text_nodes(para):
    """Get direct w:t children (not from nested paragraphs)."""
    result = []
    for child in para:
        if child.tag == f'{{{NS}}}r':
            for t in child.findall(f'{{{NS}}}t'):
                result.append(t)
    return result

def get_all_text_nodes(para):
    """Get all w:t elements in a paragraph, in document order."""
    return list(para.iter(f'{{{NS}}}t'))

def has_tab(para):
    """Check if paragraph has w:tab elements."""
    for tab in para.iter(f'{{{NS}}}tab'):
        return True
    return False

def get_para_text(para):
    """Get full text of a paragraph with tab handling."""
    texts = []
    for elem in para.iter():
        tag = elem.tag
        if tag == f'{{{NS}}}t' and elem.text:
            texts.append(elem.text)
        elif tag == f'{{{NS}}}tab':
            texts.append(' ')
    return ''.join(texts)

def count_nested_paragraphs(para):
    """Count nested w:p elements within a paragraph (for giant para detection)."""
    return len(list(para.iter(f'{{{NS}}}p')))

def analyze_template(template_path, name):
    print(f"\n{'='*80}")
    print(f"ANALYZING: {name}")
    print(f"{'='*80}")

    with zipfile.ZipFile(template_path, 'r') as z:
        doc_xml = z.read('word/document.xml').decode('utf-8')

    root = ET.fromstring(doc_xml.encode('utf-8'))
    body = root.find(f'{{{NS}}}body')

    # Get all paragraphs (direct children of body)
    all_paras = list(body.iter(f'{{{NS}}}p'))

    print(f"Total paragraphs (including nested): {len(all_paras)}")

    # Get direct body children in order
    direct_children = [c for c in body if c.tag == f'{{{NS}}}p']
    print(f"Direct body child paragraphs: {len(direct_children)}")

    # Detect giant paragraphs using the new algorithm
    giant_paras = []
    for pi, para in enumerate(direct_children):
        nested_count = len(list(para.iter(f'{{{NS}}}p')))
        if nested_count > 3:
            giant_paras.append((pi, nested_count))
            print(f"  GIANT PARA p{pi}: {nested_count} nested paragraphs")

    # Print all direct child paragraphs and their content
    print(f"\n--- Direct Body Paragraphs ---")
    for pi, para in enumerate(direct_children):
        own_nodes = get_own_text_nodes(para)
        all_nodes = get_all_text_nodes(para)
        para_text = get_para_text(para)
        has_tab_elem = has_tab(para)

        text_preview = para_text[:100] if para_text else "(empty)"
        text_preview = text_preview.replace('\n', '\\n')

        # Detect headers
        is_header = any(h in text_preview for h in SECTION_HEADERS)
        header_markers = [h for h in SECTION_HEADERS if h in text_preview]

        print(f"  p{pi}: |own={len(own_nodes)} total_nodes={len(all_nodes)}| tab={has_tab_elem}| {text_preview}")
        if header_markers:
            print(f"    => HEADERS: {header_markers}")

        # Show individual w:t node texts for detailed analysis
        if own_nodes and len(own_nodes) <= 8:
            node_texts = [f"[{i}]\"{(n.text or '')}\"" for i, n in enumerate(own_nodes)]
            print(f"    nodes: {', '.join(node_texts)}")

    print(f"\n--- Giant Paragraph Analysis ---")
    for pi, para in enumerate(direct_children):
        if pi in [g[0] for g in giant_paras]:
            own_nodes = get_own_text_nodes(para)
            print(f"  Giant p{pi} own nodes: {len(own_nodes)}")
            # Show the text content of the giant paragraph
            for i, n in enumerate(own_nodes[:20]):
                txt = (n.text or '')[:60]
                if txt:
                    print(f"    [{i}] \"{txt}\"")
            if len(own_nodes) > 20:
                print(f"    ... and {len(own_nodes) - 20} more nodes")

    # Find text box content (w:txbxContent)
    print(f"\n--- Text Boxes in Giant Paragraphs ---")
    for pi, para in enumerate(direct_children):
        if pi in [g[0] for g in giant_paras]:
            txbx_count = len(list(para.iter(f'{{{NS}}}txbxContent')))
            if txbx_count > 0:
                print(f"  Giant p{pi}: {txbx_count} txbxContent elements")
                # Show sub-paragraphs in text boxes
                sub_paras = list(para.iter(f'{{{NS}}}p'))
                print(f"    Sub-paragraphs: {len(sub_paras)}")
                for spi, sp in enumerate(sub_paras[:30]):
                    sp_text = get_para_text(sp)[:80]
                    if sp_text:
                        is_sub_header = [h for h in SECTION_HEADERS if h in sp_text]
                        marker = f" HEADER:{is_sub_header}" if is_sub_header else ""
                        print(f"    sub[{spi}]: \"{sp_text}\"{marker}")

    print(f"\n--- Section Header Detection ---")
    for pi, para in enumerate(direct_children):
        para_text = get_para_text(para)
        for h in SECTION_HEADERS:
            if h in para_text and para_text.strip() == h:
                print(f"  p{pi}: EXACT header \"{h}\"")
            elif h in para_text:
                print(f"  p{pi}: CONTAINS header \"{h}\" in \"{para_text.strip()[:60]}\"")

    print(f"\n--- w:tab Detection ---")
    for pi, para in enumerate(direct_children):
        if has_tab(para):
            para_text = get_para_text(para)[:100]
            print(f"  p{pi}: has w:tab -> \"{para_text}\"")

analyze_template(os.path.join(TEMPLATES_DIR, "简约单页01.docx"), "简约单页01")
