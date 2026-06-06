"""Analyze all 10 target templates in detail."""
import zipfile
import xml.etree.ElementTree as ET
import os
import json

NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

TEMPLATES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'templates'))

TEMPLATES = [
    "简约单页01", "稳重单页01", "知页简历01", "知页简历02",
    "文艺单页01", "文艺单页20", "极简单页01", "极简单页02",
    "活泼单页06", "稳重单页02",
]

SECTION_HEADERS = [
    '教育背景', '工作经历', '自我评价', '基本信息', '个人信息',
    '专业技能', '荣誉奖项', '证书奖励', '工作经验', '教育经历',
    '在校经历', '实习经历', '实践经历', '联系方式', '掌握技能',
    '个人资料', '个人介绍', '兴趣爱好', '职业技能', '校内实践',
    '获奖经历', '资格证书', '奖项荣誉', '任职参考',
    '教育背景EDUCATION', '实习经历JOB EXPERIENCE',
    '荣誉AWARDS', '荣誉证书',
]

# Known labels for basic info
BASIC_LABELS = ['姓名', '名字', '电话', '手机', '邮箱', 'Email', '地址',
                '求职意向', '目标职位', '应聘职位', '微信', 'WeChat',
                '个人总结', '自我评价', '个人简介', '关于我', '个人介绍']

def get_own_text_nodes(para):
    result = []
    for child in para:
        if child.tag == f'{{{NS}}}r':
            for t in child.findall(f'{{{NS}}}t'):
                result.append(t)
    return result

def get_all_text_nodes(para):
    return list(para.iter(f'{{{NS}}}t'))

def get_para_text(para):
    texts = []
    for elem in para.iter():
        tag = elem.tag
        if tag == f'{{{NS}}}t' and elem.text:
            texts.append(elem.text)
        elif tag == f'{{{NS}}}tab':
            texts.append('[TAB]')
    return ''.join(texts)

def has_tab(para):
    for tab in para.iter(f'{{{NS}}}tab'):
        return True
    return False

def count_nested_paras(para):
    return len(list(para.iter(f'{{{NS}}}p')))

for tname in TEMPLATES:
    template_path = os.path.join(TEMPLATES_DIR, f"{tname}.docx")
    if not os.path.exists(template_path):
        print(f"SKIP: {tname}.docx not found")
        continue

    print(f"\n{'='*80}")
    print(f"TEMPLATE: {tname}")
    print(f"{'='*80}")

    with zipfile.ZipFile(template_path, 'r') as z:
        doc_xml = z.read('word/document.xml').decode('utf-8')

    root = ET.fromstring(doc_xml.encode('utf-8'))
    body = root.find(f'{{{NS}}}body')

    direct_paras = [c for c in body if c.tag == f'{{{NS}}}p']
    all_paras = list(body.iter(f'{{{NS}}}p'))

    print(f"Direct body paras: {len(direct_paras)}, Total nested: {len(all_paras)}")

    # Giant paragraph detection
    for pi, para in enumerate(direct_paras):
        nested_count = count_nested_paras(para)
        if nested_count > 3:
            print(f"  Giant p{pi}: {nested_count} nested paras, {len(get_own_text_nodes(para))} own t nodes")
        else:
            # Normal paragraph - show content
            txt = get_para_text(para)[:120]
            own_nodes = get_own_text_nodes(para)
            all_nodes = get_all_text_nodes(para)
            has_tab_elem = has_tab(para)
            tab_mark = " [HAS_TAB]" if has_tab_elem else ""
            print(f"  p{pi}: own={len(own_nodes)} total={len(all_nodes)}{tab_mark} \"{txt}\"")

    # Find section headers in non-giant paragraphs
    print(f"\n  --- Section Headers ---")
    for pi, para in enumerate(direct_paras):
        if count_nested_paras(para) <= 3:
            txt = get_para_text(para).strip()
            for h in SECTION_HEADERS:
                if txt == h:
                    print(f"    p{pi}: EXACT \"{h}\"")

    # Look for basic info fields
    print(f"\n  --- Basic Info Detection ---")
    for pi, para in enumerate(direct_paras):
        if count_nested_paras(para) <= 3:
            txt = get_para_text(para).strip()
            if not txt:
                continue
            # Check label_inline pattern (label:value)
            for label in BASIC_LABELS:
                if txt.startswith(label) and ('：' in txt or ':' in txt):
                    val = txt.split('：' if '：' in txt else ':')[1].strip()
                    print(f"    p{pi}: label_inline \"{label}:{val}\"")
                    break
                if txt == label:
                    # Check adjacent for value
                    print(f"    p{pi}: label_exact \"{label}\"")
                    break

    # Find name patterns
    print(f"\n  --- Name Detection ---")
    for pi, para in enumerate(direct_paras):
        if count_nested_paras(para) <= 3:
            own_nodes = get_own_text_nodes(para)
            txts = [(n.text or '').strip() for n in own_nodes]
            non_empty = [t for t in txts if t]
            if non_empty:
                joined = ''.join(non_empty)
                # Check if any are known placeholder names or look like names
                for t in non_empty:
                    if len(t) >= 2 and len(t) <= 4 and any(c in t for c in '赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨'):
                        print(f"    p{pi}: possible_name \"{t}\"")
                    elif t in ['肖颖馨', '韩志弘', '李自强', '关睢尔', '陈小明', '刘小红',
                               '周洁', '吴芳', '白晓云', '王若琳', '沈慧美', '林晓歌',
                               '林月明', '柳云萧', '苏语凝', '钟小艾', '冯青', '张小泉',
                               '云海', '陈知页', '孟子君', '孟晓思', '关月兰', '刘璇凯',
                               '张全峰', '王菲', '宋艾嘉']:
                        print(f"    p{pi}: known_name \"{t}\"")
                    elif t in ['宋', ' 艾 嘉']:
                        rest = non_empty[non_empty.index(t)+1:] if non_empty.index(t) < len(non_empty)-1 else []
                        if rest:
                            print(f"    p{pi}: split_name_parts \"{t}\" + \"{rest[0]}\"")
                        else:
                            print(f"    p{pi}: split_name_part \"{t}\"")

    print()
