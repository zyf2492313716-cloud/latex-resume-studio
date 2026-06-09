import { Capacitor } from '@capacitor/core';
import { Directory, Encoding, Filesystem } from '@capacitor/filesystem';
import { Share } from '@capacitor/share';

const TEMPLATE_GROUPS = {
  'academic-profile': '学术与科研',
  'altacv-sidebar': '照片侧栏',
  'awesome-accent': '现代视觉',
  'creative-card': '创意展示',
  'deedy-two-column': '双栏高密度',
  'jakes-ats': 'ATS 简洁',
  'modern-clean': '现代简洁',
  'timeline-compact': '紧凑时间线',
  'word-blue-sidebar-01': 'Word 风格复刻',
  'word-literary-01': 'Word 风格复刻',
  'word-minimal-01': 'Word 风格复刻',
  'word-steady-01': 'Word 风格复刻',
  'word-zhiyue-02': 'Word 风格复刻',
};

const TEMPLATE_NAMES = {
  'academic-profile': 'Academic Profile 学术档案 LaTeX',
  'altacv-sidebar': 'Alta Sidebar 照片侧栏 LaTeX',
  'awesome-accent': 'Awesome Accent 彩色强调 LaTeX',
  'creative-card': 'Creative Card 创意名片 LaTeX',
  'deedy-two-column': 'Deedy Two Column 双栏 LaTeX',
  'jakes-ats': 'Jake ATS 极简 LaTeX',
  'modern-clean': 'Modern Clean 现代简洁 LaTeX',
  'timeline-compact': 'Timeline Compact 紧凑时间线 LaTeX',
  'word-blue-sidebar-01': 'Word Blue Sidebar 深蓝双栏 LaTeX',
  'word-literary-01': 'Word Literary 文艺复刻 LaTeX',
  'word-minimal-01': 'Word Minimal 极简复刻 LaTeX',
  'word-steady-01': 'Word Steady 稳重复刻 LaTeX',
  'word-zhiyue-02': 'Word Zhiyue 知页复刻 LaTeX',
};

export function getWebLatexTemplates() {
  return Object.keys(TEMPLATE_NAMES).map((name) => ({
    name,
    id: name,
    displayName: TEMPLATE_NAMES[name],
    kind: 'latex',
    engineType: 'latex',
    group: TEMPLATE_GROUPS[name] || 'LaTeX 模板',
    tags: ['Web/Android', 'LaTeX', 'tex-only'],
    path: `web://${name}`,
  }));
}

const escapeTex = (value) => String(value || '')
  .replace(/\\/g, '\\textbackslash{}')
  .replace(/([#$%&_{}])/g, '\\$1')
  .replace(/~/g, '\\textasciitilde{}')
  .replace(/\^/g, '\\textasciicircum{}');

const lines = (value) => String(value || '')
  .split(/\r?\n/)
  .map((item) => item.trim())
  .filter(Boolean);

const section = (title, body) => body.trim()
  ? `\\section{${escapeTex(title)}}\n${body.trim()}\n\n`
  : '';

const bullets = (value) => {
  const items = lines(value);
  if (!items.length) return '';
  return `\\begin{itemize}\n${items.map((item) => `  \\item ${escapeTex(item)}`).join('\n')}\n\\end{itemize}`;
};

const entry = ({ title, subtitle, date, description }) => {
  const head = [title, subtitle].filter(Boolean).map(escapeTex).join(' \\textbar{} ');
  const dateText = date ? `\\hfill ${escapeTex(date)}` : '';
  const body = bullets(description);
  return [
    `\\textbf{${head || '经历'}}${dateText}\\par`,
    body,
  ].filter(Boolean).join('\n');
};

export function renderLatexSourceWeb(resumeData = {}, template = {}, layoutAdjustments = {}) {
  const basic = resumeData.basicInfo || {};
  const accent = String(layoutAdjustments.accentColor || '#244A6A').replace('#', '').slice(0, 6) || '244A6A';
  const contact = [basic.phone, basic.email, basic.wechat, basic.github].filter(Boolean).map(escapeTex).join(' \\quad ');

  const education = (resumeData.education || []).map((item) => entry({
    title: item.school,
    subtitle: [item.major, item.degree].filter(Boolean).join(' '),
    date: item.date,
    description: item.description,
  })).join('\n\\vspace{0.35em}\n');

  const experience = (resumeData.experience || []).map((item) => entry({
    title: item.company,
    subtitle: item.role,
    date: item.date,
    description: item.description,
  })).join('\n\\vspace{0.35em}\n');

  const projects = [...(resumeData.projects || []), ...(resumeData.research || [])].map((item) => entry({
    title: item.name,
    subtitle: item.role,
    date: item.date,
    description: item.description,
  })).join('\n\\vspace{0.35em}\n');

  const studentWork = (resumeData.studentWork || []).map((item) => entry({
    title: item.organization,
    subtitle: item.role,
    date: item.date,
    description: item.description,
  })).join('\n\\vspace{0.35em}\n');

  const skills = (resumeData.skills || []).map((item) => `\\textbullet{} ${escapeTex(item)}`).join('\\quad ');
  const honors = (resumeData.honors || []).map((item) => `\\textbullet{} ${escapeTex(item)}`).join('\\quad ');

  return `% Web/Android fallback generated source\n% Template target: ${template.displayName || template.name || 'LaTeX'}\n\\documentclass[10pt,a4paper]{ctexart}\n\\usepackage[margin=1.35cm]{geometry}\n\\usepackage{xcolor}\n\\usepackage{hyperref}\n\\definecolor{accent}{HTML}{${accent}}\n\\setlength{\\parindent}{0pt}\n\\newcommand{\\sectionrule}{\\vspace{0.25em}{\\color{accent}\\hrule height 0.8pt}\\vspace{0.55em}}\n\\renewcommand{\\section}[1]{\\vspace{0.75em}{\\large\\bfseries\\color{accent}#1}\\sectionrule}\n\\begin{document}\n{\\Huge\\bfseries ${escapeTex(basic.name || '姓名')}}\\par\n\\vspace{0.25em}\n{\\large\\color{accent}${escapeTex(basic.title || '求职意向')}}\\par\n\\vspace{0.35em}\n${contact ? `{\\small ${contact}}\\par` : ''}\n${basic.summary ? `\\vspace{0.6em}{\\small ${escapeTex(basic.summary)}}\\par` : ''}\n\n${section('教育背景', education)}${section('项目与科研经历', projects)}${section('实习经历', experience)}${section('学生工作', studentWork)}${section('专业技能', skills)}${section('荣誉奖励', honors)}\\end{document}\n`;
}

export function downloadTextFile(filename, content, mimeType = 'application/x-tex') {
  const blob = new Blob([content], { type: `${mimeType};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export async function saveTextFileMobile(filename, content, mimeType = 'application/x-tex') {
  if (!Capacitor.isNativePlatform()) {
    downloadTextFile(filename, content, mimeType);
    return { native: false, path: filename };
  }

  const safeName = String(filename || 'resume.tex').replace(/[\\/:*?"<>|]+/g, '_');
  const path = `latex-resume-studio/${safeName}`;
  const writeResult = await Filesystem.writeFile({
    path,
    data: content,
    directory: Directory.Documents,
    encoding: Encoding.UTF8,
    recursive: true,
  });

  const uriResult = await Filesystem.getUri({
    path,
    directory: Directory.Documents,
  });
  const fileUri = uriResult.uri || writeResult.uri;

  try {
    const canShare = await Share.canShare();
    if (canShare?.value && fileUri) {
      await Share.share({
        title: '导出 LaTeX 简历源码',
        text: 'LaTeX 简历工坊已生成 .tex 源文件，可发送到文件管理器、网盘或 Overleaf。',
        files: [fileUri],
        dialogTitle: '保存或分享 .tex 源文件',
      });
    }
  } catch (err) {
    console.warn('Native share failed, file was still saved:', err);
  }

  return { native: true, path, uri: fileUri };
}
