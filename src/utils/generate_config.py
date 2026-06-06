"""Generate YAML configs for resume templates based on analysis of their document.xml structure."""

import zipfile
from lxml import etree as ET
import os
import re
import yaml
import sys

NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

# All known placeholder names across templates
ALL_KNOWN_NAMES = [
    '宋艾嘉', '肖颖馨', '韩志弘', '李自强', '张三', '李四', '王五',
    '赵六', '关睢尔', '陈小明', '刘小红', '周洁', '吴芳',
    '白晓云', '王若琳', '沈慧美', '林晓歌', '林月明', '柳云萧',
    '苏语凝', '钟小艾', '冯青', '张小泉', '云海', '陈知页',
    '孟子君', '孟晓思', '关月兰', '陈韵竹', '林悦然', '周子琪',
    '张雨涵', '李明轩', '王思远', '刘子涵', '赵雨萱', '孙梦琪',
    '周雅婷', '吴晓峰', '郑思远', '黄子轩', '林雅琪', '陈思远',
    '张雅婷', '李雨涵', '王梦琪', '刘子轩', '赵雅婷', '孙雨涵',
    '周子轩', '吴雅琪', '郑雨萱', '黄梦琪', '林子轩', '陈雅婷',
    '张思远', '李雅琪', '王雨萱', '刘梦琪', '赵子轩', '孙雅婷',
    '周雨涵', '吴思远', '郑雅婷', '黄雨涵', '林梦琪', '陈子轩',
    '张子涵', '李子轩', '王雅婷', '刘雅琪', '赵思远', '孙子轩',
    '周梦琪', '吴子涵', '郑子轩', '黄雅婷', '林雨涵', '陈雨萱',
    # Names from template scanning
    '林宇凡', '赵晓', '梁静', '刘璇凯', '杨阳', '雅丹',
    '张韵艺', '林萧', '张全峰', '王宇凡', '艾明远', '柳元青',
    '王菲', '陆然', '刘明', '宇帆', '林博文', '高凌云',
    '张悦然', '张晓轩', '王灵筠', '张筱婕', '顾元昊', '王晓峰',
    '刘诗芸', '李小冉', '林晓云', '文如菁', '郭昀芸', '周芳',
    '黄怡', '向薇尔', '田筱雨', '朗云', '陈洁', '新月',
    '语敏', '林丹阳', '李思宇', '李元茹', '张筱', '方文',
    '明小', '林云', '张璐瑶', '陈露露', '郭洁',
]

SECTION_HEADERS = [
    '教育背景', '教育经历', '教育经验', '工作经验', '工作经历', '实习经历', '实践经历',
    '项目经历', '项目经验', '校内实践', '校园经历', '在校经历', '社团经历', '学生工作',
    '荣誉证书', '荣誉奖项', '个人荣誉', '获奖经历', '证书奖励', '奖项荣誉', '资格证书',
    '荣誉奖励', '获得荣誉', '获奖情况', '所获证书', '证书奖项', '技能奖项',
    '自我评价', '个人介绍', '个人总结', '自我介绍', '个人陈述', '个人简介',
    '掌握技能', '专业技能', '职业技能', '技能特长', '技能证书', '技能',
    '个人技能', '工作技能', '软件技能', '外语技能', '职场技能', '商务技能',
    '基本信息', '个人信息', '求职意向', '联系方式', '兴趣爱好', '其他信息',
    '个人特性', '工作描述', '实习经验', '培训经历', '个人资料', '基本资料', '基础信息',
    '个人简历', '求职简历', '实习实践', '工作实践', '校内活动', '实践活动',
    '竞赛经历', '奖学金', '优势特长', '技能评价', '个人评价', '自我总结',
    # Bilingual headers
    'PRACTICAL', 'EDUCATION', 'EXPERIENCE', 'SKILLS', 'AWARDS', 'INTRODUCTION',
    'RESUME', 'JOB', 'TRAINING', 'PERSONAL', 'PROFILE', 'ABOUT', 'CONTACT',
    '荣誉AWARDS', '技能SKILLS', '教育背景EDUCATION',
    '实践经历PRACTICAL EXPERIENCE', '实习经历JOB EXPERIENCE',
]

LABEL_PATTERNS = {
    'phone': ['电话', '手机', 'Phone', 'phone', 'TEL', 'Tel'],
    'email': ['邮箱', 'Email', 'email', 'E-mail', 'MAIL'],
    'name': ['姓名'],
    'title': ['求职意向', '职位', '岗位'],
    'school': ['学校', '院校', '毕业院校'],
    'major': ['专业'],
    'degree': ['学历', '学位'],
}

# Common text that's NOT a placeholder name
NON_NAME_TEXT = {
    '男', '女', '本科', '硕士', '博士', '电话', '手机', '邮箱', '地址',
    '姓名', '性别', '年龄', '籍贯', '政治面貌', '民族', '生日', '现居',
    '求职意向', '教育背景', '工作经验', '自我评价', '个人介绍', '基本信息',
    '个人信息', '掌握技能', '职业技能', '专业技能', '兴趣爱好', '荣誉证书',
    '个人荣誉', '技能特长', '城市', '学历', '学位', '专业', '学校',
    '毕业院校', '院校', '岗位', '职位', '行业', '工作年限', '身高',
    '关于我', '联系方式', '奖项荣誉', '获奖', '证书', '年限', '籍贯',
    '政治', '民族', '生日', '年龄', '学历', '现居', '城市',
    '教育', '工作', '实习', '实践', '项目', '经历', '荣誉', '技能',
    '自我', '评价', '介绍', '总结', '意向', '基本', '个人', '掌握',
    '职业', '兴趣', '爱好', '证书', '奖项', '资格', '在校', '校内',
    '社团', '学生', '培训', '其他', '信息', '特性', '描述',
}


def get_para_texts(para):
    """Get direct w:t children of a paragraph."""
    result = []
    for r in para.findall(f'{{{NS}}}r'):
        for t in r.findall(f'{{{NS}}}t'):
            txt = (t.text or '').strip()
            if txt:
                result.append(txt)
    return result


def get_full_text(para):
    """Get concatenated text of paragraph."""
    texts = []
    for t in para.iter(f'{{{NS}}}t'):
        if t.text:
            texts.append(t.text)
    return ''.join(texts).strip()


def is_chinese_name(text):
    """Check if text looks like a Chinese placeholder name (2-4 chars, all Chinese)."""
    if len(text) < 2 or len(text) > 4:
        return False
    if not all('\u4e00' <= c <= '\u9fff' for c in text):
        return False
    if text in NON_NAME_TEXT:
        return False
    return True


def analyze_template(path):
    """Analyze a template's document.xml structure."""
    with zipfile.ZipFile(path, 'r') as z:
        doc_xml = z.read('word/document.xml').decode('utf-8')
    root = ET.fromstring(doc_xml.encode('utf-8'))
    paras = list(root.iter(f'{{{NS}}}p'))

    analysis = {
        'total_paras': len(paras),
        'sections': [],
        'name_locations': [],
        'phone_label': None,
        'phone_value': None,
        'phone_dashed': None,
        'phone_intl': None,
        'email_label': None,
        'email_value': None,
        'phone_mode': None,
        'email_mode': None,
    }

    for pi, p in enumerate(paras):
        texts = get_para_texts(p)
        full = get_full_text(p)
        if not texts and not full:
            continue

        full_clean = full.replace('|', '').replace('\u3000', ' ')

                # Detect section headers
        for kw in SECTION_HEADERS:
            if kw in full_clean and len(full_clean) < 60:
                header_text = kw
                for t in texts:
                    if kw in t.replace('|', ''):
                        header_text = t
                        break
                # Normalize: remove spaces between Chinese chars only
                header_text = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', header_text)
                analysis['sections'].append((pi, header_text))
                break

        # Detect phone
        phone_match = re.search(r'1[3-9]\d{8,9}', full.replace('-', '').replace(' ', ''))
        if phone_match and not analysis['phone_value']:
            analysis['phone_value'] = phone_match.group()
        dashed_match = re.search(r'1[3-9]\d-\d{4}-\d{4}', full)
        if dashed_match and not analysis['phone_dashed']:
            analysis['phone_dashed'] = dashed_match.group()
        intl_match = re.search(r'\+86\s*1[3-9]\d\s*\d{4}\s*\d{4}', full)
        if intl_match and not analysis['phone_intl']:
            analysis['phone_intl'] = intl_match.group()

        # Detect phone labels
        for label in LABEL_PATTERNS['phone']:
            if label in full_clean and not analysis['phone_label']:
                analysis['phone_label'] = (pi, label)
                break

        # Detect email (ASCII only - \w matches Chinese in Python)
        email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]*\.[a-zA-Z]{2,}', full)
        if email_match and not analysis['email_value']:
            analysis['email_value'] = email_match.group()

        # Detect email labels
        for label in LABEL_PATTERNS['email']:
            if label in full and not analysis['email_label']:
                analysis['email_label'] = (pi, label)
                break

    # Detect placeholder names: find 2-4 char Chinese text near personal info labels
    personal_info_paras = set()
    for pi, p in enumerate(paras):
        full = get_full_text(p).replace('|', '')
        if any(label in full for label in ['电话', '手机', '邮箱', 'Email', '姓名', '个人信息', '基本信息', '联系方式', '求职意向', '职位', '岗位']):
            personal_info_paras.add(pi)
            for offset in [-3, -2, -1, 1, 2, 3]:
                adj = pi + offset
                if 0 <= adj < len(paras):
                    personal_info_paras.add(adj)

    name_candidates = []
    for pi in sorted(personal_info_paras):
        if pi >= len(paras):
            continue
        p = paras[pi]
        texts = get_para_texts(p)
        for t in texts:
            if is_chinese_name(t):
                name_candidates.append((pi, t))

    if name_candidates:
        analysis['name_locations'] = name_candidates

    # Determine phone fill mode
    if analysis['phone_label'] and analysis['phone_value']:
        label_pi = analysis['phone_label'][0]
        para_full = get_full_text(paras[label_pi])
        if analysis['phone_value'] in para_full.replace('-', '').replace(' ', ''):
            analysis['phone_mode'] = 'label_inline'
        else:
            analysis['phone_mode'] = 'label_adjacent'
    elif analysis['phone_value']:
        analysis['phone_mode'] = 'keyword_scan'

    # Determine email fill mode
    if analysis['email_label'] and analysis['email_value']:
        label_pi = analysis['email_label'][0]
        para_full = get_full_text(paras[label_pi])
        if analysis['email_value'] in para_full:
            analysis['email_mode'] = 'label_inline'
        else:
            analysis['email_mode'] = 'label_adjacent'
    elif analysis['email_value']:
        analysis['email_mode'] = 'keyword_scan'

    return analysis


def detect_style_group(name):
    """Detect style group from template name."""
    if '文艺' in name:
        return '文艺'
    elif '极简' in name:
        return '极简'
    elif '活泼' in name:
        return '活泼'
    elif '知页' in name:
        return '知页'
    elif '稳重' in name:
        return '稳重'
    elif '简约' in name:
        return '简约'
    return '其他'


def generate_config(name, path, analysis):
    """Generate YAML config based on template analysis."""
    style = detect_style_group(name)
    config = {
        'version': '1.0',
        'template_name': name,
        'style_group': style,
        'fallback': False,
        'basic_info': {'fields': {}},
        'sections': {},
    }

    # --- Name ---
    if analysis['name_locations']:
        first_name = analysis['name_locations'][0][1]
        config['basic_info']['fields']['name'] = {
            'type': 'keyword_scan',
            'keywords': [first_name],
            'value_scope': 'full_node',
        }
    else:
        # No name detected - use keyword_scan with ALL_KNOWN_NAMES
        config['basic_info']['fields']['name'] = {
            'type': 'keyword_scan',
            'keywords': ALL_KNOWN_NAMES,
            'value_scope': 'full_node',
        }

    # --- Title ---
    # Use placeholder keyword scan; template_engine also has runtime label fallback.
    config['basic_info']['fields']['title'] = {
        'type': 'keyword_scan',
        'keywords': ['求职意向', '目标职位', '应聘职位', '应聘岗位', '意向岗位', '平面设计', '网页设计师', '美术主编', 'UI设计师', '销售员岗位'],
        'value_scope': 'keyword_substring',
    }

    # --- Phone ---
    if analysis['phone_mode'] == 'label_inline':
        config['basic_info']['fields']['phone'] = {
            'type': 'label_inline',
            'pattern': analysis['phone_label'][1],
        }
    elif analysis['phone_mode'] == 'label_adjacent':
        config['basic_info']['fields']['phone'] = {
            'type': 'label_adjacent',
            'pattern': analysis['phone_label'][1],
        }
    elif analysis['phone_mode'] == 'keyword_scan' and analysis['phone_value']:
        # Use label_inline with detected label instead of template-specific phone number
        if analysis['phone_label']:
            config['basic_info']['fields']['phone'] = {
                'type': 'label_inline',
                'pattern': analysis['phone_label'][1],
            }
        else:
            # No label - use regex pattern matching
            config['basic_info']['fields']['phone'] = {
                'type': 'pattern_match',
                'pattern_type': 'phone',
            }
    elif analysis.get('phone_dashed'):
        if analysis['phone_label']:
            config['basic_info']['fields']['phone'] = {
                'type': 'label_inline',
                'pattern': analysis['phone_label'][1],
            }
        else:
            config['basic_info']['fields']['phone'] = {
                'type': 'pattern_match',
                'pattern_type': 'phone',
            }
    elif analysis.get('phone_intl'):
        if analysis['phone_label']:
            config['basic_info']['fields']['phone'] = {
                'type': 'label_inline',
                'pattern': analysis['phone_label'][1],
            }
        else:
            config['basic_info']['fields']['phone'] = {
                'type': 'pattern_match',
                'pattern_type': 'phone',
            }
    else:
        config['basic_info']['fields']['phone'] = {
            'type': 'pattern_match',
            'pattern_type': 'phone',
        }

    # --- Email ---
    if analysis['email_mode'] == 'label_inline':
        config['basic_info']['fields']['email'] = {
            'type': 'label_inline',
            'pattern': analysis['email_label'][1],
        }
    elif analysis['email_mode'] == 'label_adjacent':
        config['basic_info']['fields']['email'] = {
            'type': 'label_adjacent',
            'pattern': analysis['email_label'][1],
        }
    elif analysis['email_mode'] == 'keyword_scan' and analysis['email_value']:
        # Use label_inline with detected label instead of template-specific email
        if analysis['email_label']:
            config['basic_info']['fields']['email'] = {
                'type': 'label_inline',
                'pattern': analysis['email_label'][1],
            }
        else:
            # No label - use regex pattern matching
            config['basic_info']['fields']['email'] = {
                'type': 'pattern_match',
                'pattern_type': 'email',
            }
    else:
        config['basic_info']['fields']['email'] = {
            'type': 'pattern_match',
            'pattern_type': 'email',
        }

    # --- Summary (in basic_info, not sections) ---
    # Look for summary section header
    summary_headers = ['自我评价', '个人介绍', '个人总结', '自我介绍', '个人陈述', '个人特性',
                       '个人简介', '个人评价', '自我总结']
    summary_found = False
    for pi, header in analysis['sections']:
        header_clean = header.replace('|', '')
        if any(kw in header_clean for kw in summary_headers):
            config['basic_info']['fields']['summary'] = {
                'type': 'section_replace',
                'section': header,
            }
            summary_found = True
            break

    # --- Sections ---
    section_map = {}
    for pi, header in analysis['sections']:
        if header not in section_map:
            section_map[header] = pi

    SECTION_TYPE_MAP = {
        '教育背景': 'education', '教育经历': 'education', '教育经验': 'education',
        '工作经验': 'experience', '工作经历': 'experience', '实习经历': 'experience',
        '实践经历': 'experience', '实习经验': 'experience',
        '项目经历': 'experience', '项目经验': 'experience',
        '实习实践': 'experience', '工作实践': 'experience',
        '培训经历': 'experience',
        '校内实践': 'studentWork', '校园经历': 'studentWork', '在校经历': 'studentWork',
        '社团经历': 'studentWork', '学生工作': 'studentWork', '校内活动': 'studentWork',
        '实践活动': 'studentWork', '竞赛经历': 'studentWork',
        '荣誉证书': 'honors', '荣誉奖项': 'honors', '个人荣誉': 'honors',
        '获奖经历': 'honors', '证书奖励': 'honors', '奖项荣誉': 'honors',
        '资格证书': 'honors', '奖项证书': 'honors',
        '荣誉奖励': 'honors', '获得荣誉': 'honors', '获奖情况': 'honors',
        '所获证书': 'honors', '证书奖项': 'honors', '技能奖项': 'honors',
        '奖学金': 'honors',
        '掌握技能': 'skills', '专业技能': 'skills', '职业技能': 'skills',
        '技能特长': 'skills', '技能证书': 'skills', '技能': 'skills',
        '个人技能': 'skills', '工作技能': 'skills', '软件技能': 'skills',
        '外语技能': 'skills', '职场技能': 'skills', '商务技能': 'skills',
        '优势特长': 'skills', '技能评价': 'skills',
        '兴趣爱好': 'interests',
        '个人特性': 'skills',
        '自我评价': 'summary', '个人介绍': 'summary', '个人总结': 'summary',
        '自我介绍': 'summary', '个人陈述': 'summary', '个人简介': 'summary',
        '个人评价': 'summary', '自我总结': 'summary',
        '基本信息': 'basic', '个人信息': 'basic', '联系方式': 'basic',
        '个人资料': 'basic', '基本资料': 'basic', '基础信息': 'basic',
        '求职意向': 'basic',
        '个人简历': 'basic', '求职简历': 'basic',
    }

    added_sections = set()
    for header, pi in section_map.items():
        sec_type = None
        for kw, stype in SECTION_TYPE_MAP.items():
            if kw in header.replace('|', ''):
                sec_type = stype
                break
        if not sec_type or sec_type in added_sections:
            continue

        if sec_type == 'education':
            config['sections']['education'] = {
                'header': header,
                'entry_schema': {
                    'school': {
                        'type': 'keyword_scan',
                        'keywords': ['大学', '学院', '学校'],
                        'value_scope': 'keyword_substring',
                    },
                    'major': {
                        'type': 'keyword_scan',
                        'keywords': ['专业', '工程', '管理', '设计'],
                        'value_scope': 'keyword_substring',
                    },
                    'degree': {
                        'type': 'keyword_scan',
                        'keywords': ['本科', '硕士', '博士', '学士'],
                        'value_scope': 'keyword_substring',
                    },
                },
                'item_separator': 'paragraph',
            }
            added_sections.add(sec_type)

        elif sec_type == 'experience':
            config['sections']['experience'] = {
                'header': header,
                'entry_schema': {
                    'company': {
                        'type': 'keyword_scan',
                        'keywords': ['公司', '科技', '企业', '集团', '有限', '研究院', '医院', '银行'],
                        'value_scope': 'keyword_substring',
                    },
                    'role': {
                        'type': 'keyword_scan',
                        'keywords': ['经理', '助理', '总监', '专员', '工程师', '实习', '主管'],
                        'value_scope': 'keyword_substring',
                    },
                },
                'item_separator': 'paragraph',
            }
            added_sections.add(sec_type)

        elif sec_type == 'honors':
            config['sections']['honors'] = {
                'header': header,
                'type': 'section_replace',
            }
            added_sections.add(sec_type)

        elif sec_type == 'skills':
            config['sections']['skills'] = {
                'header': header,
                'type': 'section_replace',
            }
            added_sections.add(sec_type)

        elif sec_type == 'studentWork':
            config['sections']['studentWork'] = {
                'header': header,
                'entry_schema': {
                    'organization': {
                        'type': 'keyword_scan',
                        'keywords': ['学生会', '社团', '协会', '中心', '组织'],
                        'value_scope': 'keyword_substring',
                    },
                    'role': {
                        'type': 'keyword_scan',
                        'keywords': ['部长', '副部', '主席', '副主席', '助理', '干事', '成员'],
                        'value_scope': 'keyword_substring',
                    },
                },
                'item_separator': 'paragraph',
            }
            added_sections.add(sec_type)

        elif sec_type == 'interests':
            config['sections']['interests'] = {
                'header': header,
                'type': 'section_replace',
            }
            added_sections.add(sec_type)

    return config


def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    template_dir = sys.argv[1] if len(sys.argv) > 1 else "/Users/zhouyufeng/Downloads/1 单页简历/"
    output_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(repo_root, "templates")

    existing = [
        '简约单页01', '稳重单页01', '文艺单页01', '文艺单页20',
        '活泼单页06', '稳重单页02', '极简单页01', '极简单页02',
        '知页简历01', '知页简历02',
    ]

    generated = 0
    skipped = 0
    errors = []

    for fname in sorted(os.listdir(template_dir)):
        if not fname.endswith('.docx'):
            continue
        name = fname.replace('.docx', '')
        if name in existing:
            skipped += 1
            continue

        path = os.path.join(template_dir, fname)
        try:
            analysis = analyze_template(path)
            config = generate_config(name, path, analysis)

            out_path = os.path.join(output_dir, f"{name}.yaml")
            with open(out_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

            generated += 1
            sections = list(config.get('sections', {}).keys())
            name_cfg = config['basic_info']['fields'].get('name', {})
            phone_cfg = config['basic_info']['fields'].get('phone', {})
            summary_cfg = config['basic_info']['fields'].get('summary', {})
            print(f"  {name}: sections={sections} name={name_cfg.get('type')} phone={phone_cfg.get('type')} summary={'yes' if summary_cfg else 'no'}")
        except Exception as e:
            errors.append((name, str(e)))
            print(f"  {name}: ERROR - {e}")

    print(f"\nGenerated: {generated}, Skipped: {skipped}, Errors: {len(errors)}")
    if errors:
        print("Errors:")
        for name, err in errors:
            print(f"  {name}: {err}")


if __name__ == '__main__':
    main()
