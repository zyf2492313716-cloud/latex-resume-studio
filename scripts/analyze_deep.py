"""Deep analysis of all 10 templates - nested paragraphs."""
import zipfile
import xml.etree.ElementTree as ET
import os
import re

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
    '获奖经历', '资格证书', '奖项荣誉',
    '教育背景EDUCATION', '实习经历JOB EXPERIENCE',
    '荣誉AWARDS', '荣誉证书',
]

# Chinese characters that are common surname beginnings
SURNAMES_SET = set('赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯昝管卢莫经房裘缪干解应宗丁宣贲邓郁单杭洪包诸左石崔吉钮龚程嵇邢滑裴陆荣翁荀羊於惠甄曲家封芮羿储靳汲邴糜松井段富巫乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武符刘景詹束龙叶幸司韶郜黎蓟薄印宿白怀蒲邰从鄂索咸籍赖卓蔺屠蒙池乔阴鬱胥能苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍郤璩桑桂濮牛寿通边扈燕冀郏浦尚农温别庄晏柴瞿阎充慕连茹习宦艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广禄阙东欧殳沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公')

def get_text_node_details(para):
    """Get detailed w:t node info for a paragraph."""
    results = []
    for elem in para.iter():
        if elem.tag == f'{{{NS}}}t':
            rPr = elem.getparent() if hasattr(elem, 'getparent') else None
            if rPr is not None:
                for parent in para.iter():
                    found = False
                    for child in parent:
                        if child is elem:
                            rPr = parent
                            found = True
                            break
                    if found:
                        break
            results.append({
                'text': elem.text or '',
                'elem': elem,
            })
        elif elem.tag == f'{{{NS}}}tab':
            if results:
                results[-1].setdefault('tabs_after', 0)
                results[-1]['tabs_after'] += 1
            else:
                results.append({'text': '[TAB]', 'elem': elem, 'is_tab': True})
    return results

def get_para_text(para):
    texts = []
    for elem in para.iter():
        if elem.tag == f'{{{NS}}}t' and elem.text:
            texts.append(elem.text)
        elif elem.tag == f'{{{NS}}}tab':
            texts.append(' ')
    return ''.join(texts)

def has_tab(para):
    return len(list(para.iter(f'{{{NS}}}tab'))) > 0

def analyze_all():
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

        # Get ALL paragraphs (including nested ones in text boxes)
        all_paras = list(body.iter(f'{{{NS}}}p'))
        direct_paras = [c for c in body if c.tag == f'{{{NS}}}p']

        # For each paragraph, analyze and print
        print(f"Total nested paragraphs: {len(all_paras)}")
        print(f"Direct body paragraphs: {len(direct_paras)}")

        # Classify paragraphs: giant vs normal
        giant_indices = set()
        for pi, para in enumerate(direct_paras):
            nested_count = len(list(para.iter(f'{{{NS}}}p')))
            if nested_count > 3:
                giant_indices.add(pi)

        # Print all paragraphs with content
        print(f"\n--- All Paragraphs (non-giant + sub-paragraphs) ---")
        seen_section_headers = set()
        label_inline_fields = {}
        label_adjacent_fields = {}
        field_counts = {}

        for pi, para in enumerate(all_paras):
            txt = get_para_text(para).strip()
            if not txt:
                continue
            if len(txt) > 150:
                txt = txt[:150] + "..."

            tab_mark = " [TAB]" if has_tab(para) else ""

            # Get own text nodes detail
            t_nodes = list(para.iter(f'{{{NS}}}t'))
            t_texts = [(t.text or '') for t in t_nodes]

            print(f"  p{pi}: \"{txt}\"{tab_mark}")

            # Show t nodes if few
            if len(t_texts) <= 6:
                node_details = ' | '.join(f"[{i}]\"{t}\"" for i, t in enumerate(t_texts))
                print(f"    nodes: {node_details}")

            # Detect section headers
            for h in SECTION_HEADERS:
                if txt == h:
                    print(f"    => SECTION HEADER: \"{h}\"")
                    seen_section_headers.add(h)

            # Detect label_inline patterns (label:value)
            for label in ['姓名', '名字', '电话', '手机', '邮箱', 'Email', '地址',
                          '求职意向', '目标职位', '应聘职位', '微信', 'WeChat',
                          '个人总结', '自我评价', '个人简介']:
                if txt.startswith(label) and ('：' in txt or ':' in txt):
                    val = re.split(r'[：:]', txt, maxsplit=1)[1].strip()
                    print(f"    => label_inline: \"{label}\" = \"{val}\"")
                    key = f"label_inline:{label}"
                    if key not in field_counts:
                        field_counts[key] = []
                    field_counts[key].append((pi, val))
                    break

            # Detect label_adjacent patterns
            for label in ['姓名', '电话', '手机', '邮箱', 'Email', '微信', '地址', '院校', '专业', '学历']:
                if txt == label:
                    # Look ahead for value in same paragraph
                    own_t = [t for t in t_texts if t.strip()]
                    if len(own_t) >= 2:
                        val_idx = own_t.index(label) + 1
                        if val_idx < len(own_t):
                            val = own_t[val_idx]
                            print(f"    => label_adjacent (same para): \"{label}\" = \"{val}\"")

        print(f"\n--- Summary ---")
        print(f"  Section headers found: {seen_section_headers}")

analyze_all()
