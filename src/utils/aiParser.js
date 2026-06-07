const EMPTY_SECTIONS = {
  education: [],
  experience: [],
  projects: [],
  research: [],
  studentWork: [],
  honors: [],
  skills: []
};

export const DEFAULT_RESUME_DATA = {
  basicInfo: {
    name: "",
    title: "",
    phone: "",
    email: "",
    wechat: "",
    github: "",
    summary: "",
    photo: ""
  },
  ...EMPTY_SECTIONS
};

async function parseWithLLM(text, config) {
  const { apiUrl, apiKey, modelName } = config;

  const systemPrompt = `你是一个专业的 HR 助手和简历结构化抽取专家。你的任务是把用户输入的杂乱无章的、AI 生成的简历文本转化为标准的 JSON 数据。
不要包含任何 markdown 标记、解释或多余的文字，必须只返回纯 JSON 格式的字符串。
必须严格遵循以下 JSON 数据格式，不允许添加额外的根节点属性：

{
  "basicInfo": {
    "name": "姓名",
    "title": "求职意向/专业岗位名",
    "phone": "手机号",
    "email": "电子邮箱",
    "wechat": "微信",
    "github": "Github链接或个人主页",
    "summary": "个人总结或自我评价，段落在一页纸内应言简意赅",
    "photo": "头像/照片 data URL；AI 解析时请留空字符串"
  },
  "education": [
    {
      "school": "学校名称",
      "major": "专业名称",
      "degree": "学历（如本科、硕士）",
      "date": "起止时间（如 2020.09 - 2024.06）",
      "description": "教育背景描述，如主修课程、荣誉奖项等"
    }
  ],
  "experience": [
    {
      "company": "公司名称",
      "role": "岗位角色/职务",
      "date": "起止时间（如 2023.07 - 2024.12 或 至今）",
      "description": "工作职责和业绩，使用换行符 \\n 分割多个要点"
    }
  ],
  "projects": [
    {
      "name": "项目名称",
      "role": "项目中的角色",
      "date": "起止时间",
      "description": "项目介绍、职责和技术栈业绩，使用换行符 \\n 分割要点"
    }
  ],
  "research": [
    {
      "name": "科研项目/课题名称",
      "role": "角色（如项目负责人、核心成员）",
      "date": "起止时间",
      "description": "研究内容、方法和成果，使用换行符 \\n 分割要点"
    }
  ],
  "studentWork": [
    {
      "organization": "组织/社团/部门名称",
      "role": "职务",
      "date": "起止时间",
      "description": "工作职责和活动描述"
    }
  ],
  "honors": [
    "荣誉称号或奖项1",
    "荣誉称号或奖项2"
  ],
  "skills": [
    "技能组1（例如：熟练掌握 React, JavaScript, ES6）",
    "技能组2（例如：掌握 Node.js, Python, PostgreSQL）"
  ]
}

要求：
1. 语言：统一使用简体中文。
2. 保持经历的简洁性，以匹配保持在一页内的约束。
3. 如果某些字段在输入中不存在，请留空串 "" 或空数组 []，不要随便虚构。`;

  function normalizeUrl(url) {
    if (!url) return '';
    url = url.replace(/\/+$/, '');
    if (url.includes('/chat/completions') || url.match(/\/v\d+\/chat\/completions$/)) return url;
    if (url.includes('api.openai.com')) return url + '/v1/chat/completions';
    if (url.includes('api.deepseek.com')) return url + '/chat/completions';
    if (url.startsWith('http://127.0.0.1') || url.startsWith('http://localhost')) {
      return url + '/v1/chat/completions';
    }
    return url + '/chat/completions';
  }

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);

    const response = await fetch(normalizeUrl(apiUrl), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${apiKey}`
      },
      body: JSON.stringify({
        model: modelName || "deepseek-chat",
        messages: [
          { role: "system", content: systemPrompt },
          { role: "user", content: text }
        ],
        temperature: 0.1
      }),
      signal: controller.signal
    });

    clearTimeout(timeout);

    if (!response.ok) {
      const errBody = await response.text().catch(() => '');
      throw new Error(`API 请求失败: ${response.status} ${errBody.slice(0, 200)}`);
    }

    const data = await response.json();
    let jsonStr = data.choices?.[0]?.message?.content || '';

    jsonStr = jsonStr.replace(/^```json\s*/i, "").replace(/```$/, "").trim();

    const parsed = JSON.parse(jsonStr);

    return sanitizeParsedData(parsed);
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new Error('API 请求超时（30秒）');
    }
    console.error("AI 接口解析失败，将使用本地备用解析器:", err);
    throw err;
  }
}

function sanitizeParsedData(data) {
  const result = {
    basicInfo: { name: "", title: "", phone: "", email: "", wechat: "", github: "", summary: "", photo: "" },
    education: [],
    experience: [],
    projects: [],
    research: [],
    studentWork: [],
    honors: [],
    skills: []
  };

  if (data.basicInfo) {
    result.basicInfo = { ...result.basicInfo, ...data.basicInfo };
  }
  const mapArray = (arr, fields) => {
    if (!Array.isArray(arr)) return [];
    return arr.map(item => {
      const obj = {};
      fields.forEach(f => { obj[f] = item[f] || ""; });
      return obj;
    });
  };
  result.education = mapArray(data.education, ['school', 'major', 'degree', 'date', 'description']);
  result.experience = mapArray(data.experience, ['company', 'role', 'date', 'description']);
  result.projects = mapArray(data.projects, ['name', 'role', 'date', 'description']);
  result.research = mapArray(data.research, ['name', 'role', 'date', 'description']);
  result.studentWork = mapArray(data.studentWork, ['organization', 'role', 'date', 'description']);
  if (Array.isArray(data.honors)) {
    result.honors = data.honors.filter(s => typeof s === "string" && s.trim() !== "");
  } else if (typeof data.honors === "object" && data.honors !== null) {
    result.honors = Object.values(data.honors).map(val => String(val));
  }
  if (Array.isArray(data.skills)) {
    result.skills = data.skills.filter(s => typeof s === "string" && s.trim() !== "");
  } else if (typeof data.skills === "object" && data.skills !== null) {
    result.skills = Object.values(data.skills).map(val => String(val));
  }

  return result;
}

export function parseWithLocalRules(text) {
  const rawLines = text.split("\n");
  const lineEntries = rawLines
    .map((raw, idx) => ({
      raw,
      clean: raw.replace(/^\*+\s*/, '').replace(/\*+$/, '').trim()
    }))
    .filter(e => e.clean !== "");

  const result = {
    basicInfo: { name: "", title: "", phone: "", email: "", wechat: "", github: "", summary: "", photo: "" },
    education: [],
    experience: [],
    projects: [],
    research: [],
    studentWork: [],
    honors: [],
    skills: []
  };

  const phoneRegex = /(1[3-9]\d{9})/;
  const phoneMatch = text.match(phoneRegex);
  if (phoneMatch) result.basicInfo.phone = phoneMatch[1];

  const emailRegex = /([a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+\.[a-zA-Z]{2,6})/;
  const emailMatch = text.match(emailRegex);
  if (emailMatch) result.basicInfo.email = emailMatch[1];

  const sectionHeaders = ["教育背景", "教育经历", "学历教育", "科研经历", "科研项目", "实习经历", "工作经历", "实践经历", "学生工作", "社会实践", "学生活动", "项目经验", "专业技能", "个人技能", "掌握技能", "核心技能", "技能特长", "荣誉奖励", "获奖情况", "所获荣誉", "荣誉奖项", "自我评价", "个人总结", "个人简介"];
  const nameBlacklist = ["求职", "简历", "意向", "电话", "邮箱", "自我", "评价", "总结", "个人", "基本", "信息", "姓名", ...sectionHeaders];
  result.basicInfo.name = text.match(/姓名[：:]\s*([\u4e00-\u9fa5]{2,4})/)?.[1] || "";
  if (!result.basicInfo.name && lineEntries[0]) {
    const firstParts = lineEntries[0].clean.split(/[|｜]/).map(s => s.trim()).filter(Boolean);
    const candidate = firstParts[0] || "";
    if (/^[\u4e00-\u9fa5]{2,4}$/.test(candidate) && !nameBlacklist.some(b => candidate.includes(b))) {
      result.basicInfo.name = candidate;
    }
  }
  if (!result.basicInfo.name) {
    for (let i = 0; i < Math.min(lineEntries.length, 5); i++) {
      const line = lineEntries[i].clean;
      if (/^[\u4e00-\u9fa5]{2,4}$/.test(line) && !nameBlacklist.some(b => line.includes(b))) {
        result.basicInfo.name = line;
        break;
      }
    }
  }
  if (!result.basicInfo.name && lineEntries[0] && lineEntries[0].clean.length < 8 && !lineEntries[0].clean.includes(":") && !lineEntries[0].clean.includes("：") && !nameBlacklist.some(b => lineEntries[0].clean.includes(b))) {
    result.basicInfo.name = lineEntries[0].clean;
  }

  const titleRegex = /(意向|求职意向|期望职位|岗位|职务|职位|方向)[：:]?\s*([^\n,，|]+)/i;
  const titleMatch = text.match(titleRegex);
  if (titleMatch) {
    result.basicInfo.title = titleMatch[2].trim();
  } else {
    const jobKeywords = ["工程师", "开发", "设计师", "运营", "经理", "产品", "文秘", "选调生", "专员", "教师", "预防医学", "临床", "药学", "护理", "数据", "研究", "分析"];
    for (const e of lineEntries.slice(0, 12)) {
      const line = e.clean;
      const matched = jobKeywords.find(key => line === key || line.startsWith(key) || line.includes(key + '·') || line.includes(key + ' ') || line.includes(key + '（'));
      if (matched && line.length < 30 && !line.includes("经历") && !line.includes("项目") && !line.includes("科研") && !line.includes("教育") && !line.includes("荣誉") && !line.includes("课程") && !line.includes("核心")) {
        result.basicInfo.title = matched;
        break;
      }
    }
  }

  const wechatMatch = text.match(/(?:微信|WeChat)[：:]\s*(\S+)/i);
  if (wechatMatch) result.basicInfo.wechat = wechatMatch[1];
  const githubMatch = text.match(/(?:GitHub|Github|github)[：:]\s*(\S+)/i);
  if (githubMatch) result.basicInfo.github = githubMatch[1];

  const skillLines = [];
  let inSkillSection = false;
  lineEntries.forEach(e => {
    const line = e.clean;
    if (/^(专业技能|个人技能|掌握技能|核心技能|技能特长)/.test(line) && line.length < 10) {
      inSkillSection = true;
      return;
    }
    if (inSkillSection) {
      if (/^(科研|实习|工作|项目|学生工作|荣誉|教育|社会实践|科研经历|实习经历|工作经历|项目经验|学生工作|荣誉奖励|教育背景)/.test(line) && line.length < 10) {
        inSkillSection = false;
        return;
      }
      const cleaned = line.replace(/^[-•·*\d]+[.、\s)]*/, "").trim();
      if (cleaned) {
        const parts = cleaned.split(/[,，、;；]/).map(s => s.trim()).filter(s => s && (s.length > 1 || s === 'R'));
        parts.forEach(p => {
          if (!skillLines.some(existing => existing.includes(p))) skillLines.push(p);
        });
      }
    }
  });
  if (skillLines.length > 0) {
    result.skills = skillLines.slice(0, 8);
  }

  let currentSection = "";
  let currentEdu = null;
  let currentExp = null;
  let currentProj = null;
  let currentResearch = null;
  let currentSW = null;
  let currentHonors = [];
  let summaryLines = [];

  const datePattern = /(\d{4}[.\-/]\d{1,2}\s*[-~—至]\s*(?:\d{4}[.\-/]\d{1,2}|至今|毕业)|\d{4}\s*[-~—至]\s*(?:\d{4}|至今))/;

  function extractDate(line) {
    return line.match(datePattern)?.[1]?.replace(/\s+/g, '') || "";
  }

  function stripDate(line) {
    return line.replace(datePattern, '').replace(/[（）()]/g, ' ').trim();
  }

  function parseStudentWorkLine(line) {
    const date = extractDate(line);
    const lineWithoutDate = stripDate(line).replace(/["“”]/g, '').trim();
    let org = lineWithoutDate, role = "";
    const roleWords = ["项目组织部部长", "调研专报部研究助理", "权益部副部长", "优秀志愿者", "副部长", "部长", "研究助理", "助理", "主席", "干事", "部员", "副主任", "主任", "志愿者"];
    const roleWord = roleWords.find(rw => lineWithoutDate.endsWith(rw) || lineWithoutDate.includes(rw));
    if (roleWord) {
      role = roleWord;
      org = lineWithoutDate.replace(roleWord, '').replace(/[、，,|｜]+$/, '').trim();
    }
    if (!role) role = "成员";
    return {
      organization: (org || line).replace(/^[\d]+[.、\s)]*/, "").trim(),
      role: role.trim() || "",
      date,
      description: ""
    };
  }

  function detectSection(line) {
    if (line.length >= 12) return "";
    const cleaned = line.replace(/^\*+/, '').replace(/\*+$/, '').trim();
    if (/^(教育背景|教育经历|学历教育)/.test(cleaned)) return "edu";
    if (/^(科研经历|科研项目)/.test(cleaned)) return "research";
    if (/^(实习经历)/.test(cleaned)) return "exp";
    if (/^(工作经历|实践经历)/.test(cleaned)) return "exp";
    if (/^(学生工作|社会实践|学生活动)/.test(cleaned)) return "sw";
    if (/^(项目经验)/.test(cleaned)) return "proj";
    if (/^(专业技能|掌握技能|核心技能|技能特长)/.test(cleaned)) return "reset";
    if (/^(荣誉奖励|获奖情况|所获荣誉|荣誉奖项|荣誉)/.test(cleaned)) return "honors";
    if (/^(自我评价|个人总结|个人简介)/.test(cleaned)) return "summary";
    if (/^教育/.test(cleaned) && cleaned.length < 6) return "edu";
    if (/^工作/.test(cleaned) && cleaned.length < 6) return "exp";
    if (/^项目/.test(cleaned) && cleaned.length < 6) return "proj";
    if (/^科研/.test(cleaned) && cleaned.length < 6) return "research";
    if (/^学生/.test(cleaned) && cleaned.length < 6) return "sw";
    return "";
  }

  function pushCurrent() {
    if (currentEdu) result.education.push(currentEdu);
    if (currentExp) result.experience.push(currentExp);
    if (currentProj) result.projects.push(currentProj);
    if (currentResearch) result.research.push(currentResearch);
    if (currentSW) result.studentWork.push(currentSW);
    currentEdu = null; currentExp = null; currentProj = null;
    currentResearch = null; currentSW = null;
  }

  lineEntries.forEach(e => {
    const line = e.clean;
    const section = detectSection(e.raw);
    if (section === "reset") {
      pushCurrent();
      currentSection = "";
      return;
    }
    if (section) {
      pushCurrent();
      currentSection = section;
      return;
    }

    if (currentSection === "edu") {
      if ((line.includes("大学") || line.includes("学院")) && line.length < 60 && !/^(交流|交换|访学|暑期)/.test(line) && !line.includes("暑期学校")) {
        if (currentEdu) result.education.push(currentEdu);
        let degree = "本科";
        if (line.includes("硕士") || line.includes("研究生")) degree = "硕士";
        else if (line.includes("博士")) degree = "博士";
        else if (line.includes("大专") || line.includes("专科")) degree = "大专";
        const date = extractDate(line);
        let school = "", major = "";
        if (line.includes("|")) {
          const parts = line.split("|").map(s => s.trim());
          school = parts.find(p => p.includes("大学") || p.includes("学院")) || parts[0] || "";
          const rest = stripDate(parts.filter(p => p !== school && !/^\d{4}/.test(p)).join(" "));
          const mm = rest.match(/^([^\s·（（]+)/);
          major = mm ? mm[1] : "";
        } else {
          const withoutDate = stripDate(line);
          const degreeMatch = withoutDate.match(/[（(](本科|硕士|博士|大专|专科|研究生)[）)]/);
          if (degreeMatch) degree = degreeMatch[1] === '研究生' ? '硕士' : degreeMatch[1];
          const parts = withoutDate.replace(/[（(](本科|硕士|博士|大专|专科|研究生)[）)]/g, ' ').split(/[\s,，|]+/).filter(p => p !== "");
          school = parts.find(p => p.includes("大学") || p.includes("学院")) || parts[0] || "";
          major = parts.find(p => !p.includes("大学") && !p.includes("学院") && !/^(硕士|本科|博士|大专|专科)$/.test(p) && !/^\d{4}/.test(p) && p.length < 10) || "";
        }
        currentEdu = { school, major, degree, date, description: "" };
      } else if (currentEdu) {
        currentEdu.description += (currentEdu.description ? "\n" : "") + line;
      }
    }
    else if (currentSection === "exp") {
      const pipeParts = line.split("|").map(s => s.trim());
      const hasDate = /\d{4}[.\-/]/.test(line);
      const hasInstitution = /(公司|集团|中心|医院|局|疾控|大学|学院|机构|署|办)/.test(line);
      if (pipeParts.length >= 2 && (hasDate || hasInstitution || pipeParts[0].length < 20)) {
        if (currentExp) result.experience.push(currentExp);
        const dateMatch = line.match(datePattern);
        currentExp = {
          company: pipeParts[0].replace(/^[\d]+[.、\s)]*/, "").trim() || "",
          role: pipeParts[1] || "",
          date: dateMatch ? dateMatch[1] : "",
          description: ""
        };
      } else if (hasInstitution && line.length < 40) {
        if (currentExp) result.experience.push(currentExp);
        const dateMatch = line.match(datePattern);
        const parts = line.split(/[\s,，|]+/).filter(p => p !== "");
        const company = (parts.find(p => /(公司|集团|中心|医院|局|疾控|大学|学院|机构|署|办)/.test(p)) || parts[0] || "").replace(/^[\d]+[.、\s)]*/, "").trim();
        const role = parts.find(p => !/(公司|集团|中心|医院|局|疾控|大学|学院|机构|署|办)/.test(p) && !p.includes("至今") && !/^\d{4}/.test(p) && !/^[.\-/]/.test(p)) || "";
        currentExp = { company, role, date: dateMatch ? dateMatch[1] : "", description: "" };
      } else if (currentExp) {
        currentExp.description += (currentExp.description ? "\n" : "") + line;
      }
    }
    else if (currentSection === "proj") {
      const pipeParts = line.split("|").map(s => s.trim());
      const hasDate = /\d{4}[.\-/]/.test(line);
      if (pipeParts.length >= 2 && (hasDate || pipeParts[0].length < 30)) {
        if (currentProj) result.projects.push(currentProj);
        const dateMatch = line.match(datePattern);
        currentProj = {
          name: pipeParts[0] || "",
          role: pipeParts.length >= 3 ? pipeParts[1] : (line.includes("负责人") ? "项目负责人" : "核心成员"),
          date: dateMatch ? dateMatch[1] : "",
          description: ""
        };
      } else if ((line.includes("项目") || line.includes("系统") || line.includes("平台") || line.includes("应用")) && line.length < 40) {
        if (currentProj) result.projects.push(currentProj);
        const dateMatch = line.match(datePattern);
        const parts = line.split(/[\s,，|]+/).filter(p => p !== "");
        const name = parts.find(p => p.includes("项目") || p.includes("系统") || p.includes("平台") || p.includes("应用")) || parts[0] || "";
        const role = parts.find(p => p !== name && !p.includes("至今") && !/^\d{4}/.test(p) && !/^[.\-/]/.test(p)) || "核心成员";
        currentProj = { name, role, date: dateMatch ? dateMatch[1] : "", description: "" };
      } else if (currentProj) {
        currentProj.description += (currentProj.description ? "\n" : "") + line;
      }
    }
    else if (currentSection === "research") {
      const pipeParts = line.split("|").map(s => s.trim());
      const hasDate = /\d{4}[.\-/]/.test(line);
      if (pipeParts.length >= 2 && (hasDate || pipeParts[0].length < 30)) {
        if (currentResearch) result.research.push(currentResearch);
        const dateMatch = line.match(datePattern);
        currentResearch = {
          name: pipeParts[0].replace(/^[\d]+[.、\s)]*/, "").trim() || "",
          role: pipeParts.length >= 3 ? pipeParts[1] : (line.includes("负责人") ? "项目负责人" : "核心成员"),
          date: dateMatch ? dateMatch[1] : "",
          description: ""
        };
      } else if (currentResearch) {
        const hasDate = /(?:19|20)\d{2}[-/.]\d{1,2}/.test(line);
        if (hasDate && line.length < 40) {
          if (currentResearch) result.research.push(currentResearch);
          const dateMatch = line.match(datePattern);
          currentResearch = {
            name: line.replace(/^[\d]+[.、\s)]*/, "").trim(),
            role: "核心成员",
            date: dateMatch ? dateMatch[1] : "",
            description: ""
          };
        } else {
          currentResearch.description += (currentResearch.description ? "\n" : "") + line;
        }
      }
    }
    else if (currentSection === "sw") {
      const hasOrg = line.includes("学生") || line.includes("社团") || line.includes("会") || line.includes("中心") || line.includes("大学");
      const hasRoleKW = line.includes("部长") || line.includes("副部长") || line.includes("助理") || line.includes("主席") || line.includes("干事") || line.includes("研究") || line.includes("志愿者");
      if (hasOrg && hasRoleKW && line.length < 80) {
        if (currentSW) result.studentWork.push(currentSW);
        if (line.includes('、') && !extractDate(line)) {
          const parts = line.split('、').map(part => part.trim()).filter(Boolean);
          if (parts.length > 1 && parts.every(part => /部长|助理|主席|干事|志愿者/.test(part))) {
            parts.forEach(part => result.studentWork.push(parseStudentWorkLine(part)));
            currentSW = null;
            return;
          }
        }
        currentSW = parseStudentWorkLine(line);
      } else if (currentSW) {
        currentSW.description += (currentSW.description ? "\n" : "") + line;
      }
    }
    else if (currentSection === "honors") {
      const cleaned = line.replace(/^[-•·*\d]+[.、\s)]*/, "").trim();
      if (cleaned && cleaned.length > 1) {
        currentHonors.push(cleaned);
      }
    }
    else if (currentSection === "summary") {
      summaryLines.push(line);
    }
  });

  pushCurrent();

  result.honors = currentHonors;
  if (summaryLines.length > 0) result.basicInfo.summary = summaryLines.join("\n");
  if (!result.basicInfo.summary) {
    const summaryPrefix = text.match(/(已获保研资格|保研|推免|推研)/);
    if (summaryPrefix) result.basicInfo.summary = summaryPrefix[1];
  }

  result.projects.forEach(p => { p.name = p.name.replace(/^[\d]+[.、\s)]*/, "").trim(); });
  result.experience.forEach(e => { e.company = e.company.replace(/^[\d]+[.、\s)]*/, "").trim(); });
  result.research.forEach(r => { r.name = r.name.replace(/^[\d]+[.、\s)]*/, "").trim(); });
  result.studentWork.forEach(s => { s.organization = s.organization.replace(/^[\d]+[.、\s)]*/, "").trim(); });

  return result;
}

export async function parseResumeText(text, config) {
  if (!text || text.trim() === "") {
    return { data: DEFAULT_RESUME_DATA, source: 'empty' };
  }

  if (config && config.apiUrl && config.apiKey) {
    try {
      const data = await parseWithLLM(text, config);
      return { data, source: 'api' };
    } catch (err) {
      console.warn("大模型解析出错，降级使用本地解析器:", err.message);
      const data = parseWithLocalRules(text);
      return { data, source: 'fallback', error: err.message };
    }
  } else {
    return { data: parseWithLocalRules(text), source: 'local' };
  }
}

export async function polishText(text, apiConfig, mode = 'professional') {
  const { apiUrl, apiKey, modelName } = apiConfig;
  if (!apiUrl || !apiKey) {
    throw new Error("请先在左侧配置 AI API 的 Base URL 和 API Key！");
  }
  
  function normalizeUrl(url) {
    if (!url) return '';
    url = url.replace(/\/+$/, '');
    if (url.includes('/chat/completions') || url.match(/\/v\d+\/chat\/completions$/)) return url;
    if (url.includes('api.openai.com')) return url + '/v1/chat/completions';
    if (url.includes('api.deepseek.com')) return url + '/chat/completions';
    if (url.startsWith('http://127.0.0.1') || url.startsWith('http://localhost')) {
      return url + '/v1/chat/completions';
    }
    return url + '/chat/completions';
  }

  let systemPrompt = '';
  if (mode === 'star') {
    systemPrompt = `你是一个专业的简历内容润色和 STAR 原则改写专家。
请帮我将输入的简历文案重构为符合 STAR 原则（Situation-情境, Task-任务, Action-行动, Result-结果）的高水平量化描述。
要求：
1. 语言干练，突出技术深度或业务贡献。
2. 尽量补充和突出量化数据和具体指标（如性能提升xx%，研发周期缩短xx%，若原句无具体数字则合理估算或使用百分比占位符如 xx%）。
3. 结构必须遵循：【S/T-背景任务】面临何种架构/业务挑战 ➔ 【A-行动】使用何种方案/技术栈进行开发重构 ➔ 【R-结果】最终取得的性能提升或业务成果。
4. ⚠️ 必须只返回重写后的文案内容本身，禁止返回任何多余的客套话或前缀介绍。
5. 统一使用简体中文。`;
  } else if (mode === 'shorten') {
    systemPrompt = `你是一个简历排版精简专家。
请帮我把输入的简历经历文案在“保留核心工作要点和业绩”的前提下，进行大幅度缩短精炼，以解决简历页面排版溢出的痛点。
要求：
1. 保留关键技术名词与核心量化成果。
2. 剔除多余的辅助描述词、主语及修饰性字眼，只留最干练的骨架。
3. ⚠️ 必须只返回精简后的文案本身，绝对禁止返回任何多余的解释。
4. 统一使用简体中文。`;
  } else {
    systemPrompt = `你是一个专业的简历内容润色和优化专家。
请帮我优化润色输入的这句简历文案，使其显得更专业、用词更具书面语与 HR 敏感度。
要求：
1. 表达干练精简，避免口语化和冗余。
2. 保持与原文案语义高度一致，不要随意虚构工作事实或学历背景。
3. ⚠️ 必须只返回润色后的文案内容本身，不要返回任何解释和套话。
4. 统一使用简体中文。`;
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);

  const response = await fetch(normalizeUrl(apiUrl), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${apiKey}`
    },
    body: JSON.stringify({
      model: modelName || "deepseek-chat",
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: text }
      ],
      temperature: 0.3
    }),
    signal: controller.signal
  });

  clearTimeout(timeout);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API 错误 (HTTP ${response.status}): ${errorText}`);
  }

  const result = await response.json();
  return result.choices[0].message.content.trim();
}
