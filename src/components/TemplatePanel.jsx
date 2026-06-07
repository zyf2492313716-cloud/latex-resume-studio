import React, { useState, useEffect } from 'react';
import { Layers, FileText, RefreshCw } from 'lucide-react';

export default function TemplatePanel({
  templateList,
  selectedTemplate,
  setSelectedTemplate,
  onReloadTemplates,
  resumeData
}) {
  const [configStatus, setConfigStatus] = useState({});

  const hasItems = (key) => Array.isArray(resumeData?.[key]) && resumeData[key].length > 0;

  const getResumeNeeds = () => ([
    { key: 'basic', label: '基本信息', active: Boolean(resumeData?.basicInfo?.name || resumeData?.basicInfo?.phone || resumeData?.basicInfo?.email) },
    { key: 'photo', label: '照片', active: Boolean(resumeData?.basicInfo?.photo) },
    { key: 'summary', label: '个人总结', active: Boolean(resumeData?.basicInfo?.summary) },
    { key: 'education', label: '教育', active: hasItems('education') },
    { key: 'experience', label: '工作', active: hasItems('experience') },
    { key: 'projects', label: '项目', active: hasItems('projects') },
    { key: 'research', label: '科研', active: hasItems('research') },
    { key: 'studentWork', label: '学生工作', active: hasItems('studentWork') },
    { key: 'skills', label: '技能', active: hasItems('skills') },
    { key: 'honors', label: '荣誉', active: hasItems('honors') },
  ].filter(item => item.active));

  const LATEX_CAPABILITIES = {
    'academic-profile': ['basic', 'photo', 'summary', 'education', 'experience', 'projects', 'research', 'studentWork', 'skills', 'honors'],
    'altacv-sidebar': ['basic', 'photo', 'summary', 'education', 'experience', 'projects', 'research', 'studentWork', 'skills', 'honors'],
    'timeline-compact': ['basic', 'photo', 'summary', 'education', 'experience', 'projects', 'research', 'studentWork', 'skills', 'honors'],
    'creative-card': ['basic', 'photo', 'summary', 'education', 'experience', 'projects', 'research', 'studentWork', 'skills', 'honors'],
    'awesome-accent': ['basic', 'summary', 'education', 'experience', 'projects', 'research', 'studentWork', 'skills', 'honors'],
    'deedy-two-column': ['basic', 'summary', 'education', 'experience', 'projects', 'research', 'studentWork', 'skills', 'honors'],
    'jakes-ats': ['basic', 'summary', 'education', 'experience', 'projects', 'research', 'studentWork', 'skills', 'honors'],
    'modern-clean': ['basic', 'summary', 'education', 'experience', 'projects', 'research', 'studentWork', 'skills', 'honors'],
    'word-minimal-01': ['basic', 'photo', 'summary', 'education', 'experience', 'projects', 'research', 'studentWork', 'skills', 'honors'],
    'word-steady-01': ['basic', 'photo', 'summary', 'education', 'experience', 'projects', 'research', 'studentWork', 'skills', 'honors'],
    'word-literary-01': ['basic', 'photo', 'summary', 'education', 'experience', 'projects', 'research', 'studentWork', 'skills', 'honors'],
    'word-zhiyue-02': ['basic', 'photo', 'summary', 'education', 'experience', 'projects', 'research', 'studentWork', 'skills', 'honors'],
    'word-blue-sidebar-01': ['basic', 'photo', 'summary', 'education', 'experience', 'projects', 'research', 'studentWork', 'skills', 'honors'],
  };

  const getCoverageMatch = (template) => {
    const needs = getResumeNeeds();
    if (!needs.length) return { score: 100, missing: [], covered: [] };
    const caps = new Set(LATEX_CAPABILITIES[template.name] || []);
    const covered = needs.filter(item => caps.has(item.key));
    const missing = needs.filter(item => !caps.has(item.key));
    return {
      score: Math.round((covered.length / needs.length) * 100),
      missing,
      covered,
    };
  };

  const getTemplateMatch = (template) => {
    const isLatex = template.kind === 'latex' || template.engineType === 'latex';
    const name = template.name || '';
    const displayName = template.displayName || name;
    const hasPhoto = Boolean(resumeData?.basicInfo?.photo);

    if (isLatex) {
      const coverage = getCoverageMatch(template);
      const missingText = coverage.missing.map(item => item.label).join('、');
      const fullReason = `已覆盖当前填写的 ${coverage.covered.length} 个核心板块：${coverage.covered.map(item => item.label).join('、')}。`;
      if (coverage.score === 100) {
        const labelMap = {
          'academic-profile': '100 分科研首推',
          'altacv-sidebar': hasPhoto ? '100 分照片首推' : '100 分侧栏推荐',
          'timeline-compact': '100 分紧凑高密度',
          'creative-card': '100 分视觉展示',
          'word-minimal-01': '100 分极简复刻',
          'word-steady-01': '100 分稳重复刻',
          'word-literary-01': '100 分文艺复刻',
          'word-zhiyue-02': '100 分知页复刻',
          'word-blue-sidebar-01': '100 分蓝栏复刻',
        };
        return {
          score: 100,
          label: labelMap[name] || '100 分完整匹配',
          reason: fullReason
        };
      }
      return {
        score: coverage.score,
        label: '部分匹配',
        reason: `已覆盖 ${coverage.covered.length}/${coverage.covered.length + coverage.missing.length} 个当前板块；缺少：${missingText || '无'}。`
      };
    }

    return {
      score: 0,
      label: '已隐藏',
      reason: '当前版本专做 LaTeX 模板。'
    };
  };

  useEffect(() => {
    if (!window.electronAPI?.checkTemplateConfig || !templateList.length) return;
    const check = async () => {
      const status = {};
      for (const t of templateList) {
        try {
          const result = await window.electronAPI.checkTemplateConfig(t.path);
          status[t.name] = result;
        } catch (e) {
          status[t.name] = { hasConfig: false, fallback: false };
        }
      }
      setConfigStatus(status);
    };
    check();
  }, [templateList]);

  const getStatusIcon = (name) => {
    const s = configStatus[name];
    if (!s) return null;
    if (s.engineType === 'latex') {
      return (
        <span
          title="TeX 模板：支持导出 .tex；检测到 LaTeX 编译器后可编译 PDF"
          style={{
            color: '#c4b5fd',
            background: 'rgba(139,92,246,0.14)',
            border: '1px solid rgba(139,92,246,0.32)',
            borderRadius: '3px',
            padding: '1px 4px',
            fontSize: '9px',
            fontWeight: 800,
            marginLeft: 'auto'
          }}
        >
          TeX
        </span>
      );
    }
    if (s.hasConfig && !s.fallback) return <span title="YAML 配置已加载" style={{ color: 'rgba(255,255,255,0.3)', fontSize: '10px', marginLeft: 'auto' }}>✓</span>;
    if (s.hasConfig && s.fallback) return <span title="YAML + v2 兜底" style={{ color: '#fb923c', fontSize: '10px', fontWeight: 700, marginLeft: 'auto' }}>○</span>;
    return <span title="v2 填充" style={{ color: '#6b7280', fontSize: '10px', marginLeft: 'auto' }}>—</span>;
  };
  const grouped = {};
  templateList.forEach(t => {
    let group = '其他';
    if (t.kind === 'latex' || t.engineType === 'latex') group = t.group || 'LaTeX 模板';
    if (!grouped[group]) grouped[group] = [];
    grouped[group].push(t);
  });

  const recommendedTemplates = [...templateList]
    .map(t => ({ template: t, match: getTemplateMatch(t) }))
    .sort((a, b) => b.match.score - a.match.score)
    .slice(0, 3);

  const handleSelectDir = async () => {
    if (onReloadTemplates) onReloadTemplates();
  };

  return (
    <div className="glass-panel template-panel" style={{ color: '#f3f4f6' }}>
      <div style={{
        padding: '16px 18px', borderBottom: '1px solid var(--border-glass)',
        fontSize: '14px', fontWeight: 700, display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', background: 'rgba(0,0,0,0.1)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Layers size={16} style={{ color: 'var(--color-accent)' }} /> LaTeX 模板 ({templateList.length})
        </div>
        <button onClick={handleSelectDir} title="刷新 LaTeX 模板" style={{
          background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.12)',
          borderRadius: '4px', padding: '3px 8px', cursor: 'pointer',
          color: 'var(--color-text-muted)', fontSize: '11px', display: 'flex',
          alignItems: 'center', gap: '4px'
        }}>
          <RefreshCw size={11} /> 刷新
        </button>
      </div>

      <div style={{
        flex: 1, overflowY: 'auto', padding: '12px',
        display: 'flex', flexDirection: 'column', gap: '12px'
      }}>
        {templateList.length === 0 ? (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            justifyContent: 'center', height: '100%', gap: '12px',
            color: 'var(--color-text-muted)', fontSize: '13px', textAlign: 'center', padding: '20px'
          }}>
            <FileText size={32} style={{ opacity: 0.4 }} />
            <div>未找到 LaTeX 模板</div>
            <button onClick={handleSelectDir} style={{
              padding: '8px 16px', background: 'rgba(59,130,246,0.15)',
              border: '1px solid rgba(59,130,246,0.3)', borderRadius: '6px',
              color: '#93c5fd', cursor: 'pointer', fontSize: '12px', fontWeight: 600
            }}>
              刷新模板
            </button>
          </div>
        ) : (
          <>
            {recommendedTemplates.length > 0 && (
              <div style={{
                padding: '10px', borderRadius: '10px',
                background: 'linear-gradient(135deg, rgba(124,58,237,0.16), rgba(14,165,233,0.10))',
                border: '1px solid rgba(196,181,253,0.22)'
              }}>
                <div style={{ fontSize: '11px', fontWeight: 800, color: '#ddd6fe', marginBottom: '8px' }}>
                  根据当前内容推荐
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {recommendedTemplates.map(({ template, match }) => (
                    <button
                      key={template.name}
                      onClick={() => setSelectedTemplate(template)}
                      title={match.reason}
                      style={{
                        textAlign: 'left', padding: '8px', borderRadius: '8px', cursor: 'pointer',
                        background: selectedTemplate?.name === template.name ? 'rgba(59,130,246,0.22)' : 'rgba(255,255,255,0.06)',
                        border: selectedTemplate?.name === template.name ? '1px solid #60a5fa' : '1px solid rgba(255,255,255,0.10)',
                        color: '#f8fafc'
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center' }}>
                        <span style={{ fontSize: '12px', fontWeight: 800 }}>{template.displayName}</span>
                        <span style={{ fontSize: '10px', color: '#a7f3d0', fontWeight: 800 }}>{match.score}%</span>
                      </div>
                      <div style={{ marginTop: '3px', fontSize: '10px', color: '#cbd5e1', lineHeight: 1.35 }}>
                        {match.label}：{match.reason}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {Object.entries(grouped).map(([group, templates]) => (
            <div key={group}>
              <div style={{
                fontSize: '11px', fontWeight: 700, color: 'var(--color-text-muted)',
                marginBottom: '6px', paddingLeft: '8px',
                borderLeft: '2px solid var(--color-accent)'
              }}>
                {group} ({templates.length})
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                {[...templates].sort((a, b) => getTemplateMatch(b).score - getTemplateMatch(a).score).map(t => {
                  const isSelected = selectedTemplate?.name === t.name;
                  const isLatex = t.kind === 'latex' || t.engineType === 'latex';
                  const tags = (t.tags || []).slice(0, 4);
                  const match = getTemplateMatch(t);
                  return (
                    <div key={t.name}
                      onClick={() => { setSelectedTemplate(t); }}
                      style={{
                        padding: '8px 10px', borderRadius: '6px', cursor: 'pointer',
                        background: isSelected ? 'rgba(59,130,246,0.15)' : 'transparent',
                        border: isSelected ? '1px solid var(--color-accent)' : '1px solid transparent',
                        fontSize: '12px', fontWeight: isSelected ? 600 : 400,
                        color: isSelected ? '#fff' : 'var(--color-text-muted)',
                        transition: 'all 0.15s'
                      }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', width: '100%' }}>
                        <FileText size={12} style={{ flexShrink: 0, color: isLatex ? '#c4b5fd' : undefined }} />
                        <span>{t.displayName}</span>
                        {match.score >= 90 && (
                          <span title={match.reason} style={{
                            fontSize: '9px', lineHeight: 1,
                            color: '#a7f3d0', background: 'rgba(16,185,129,0.12)',
                            border: '1px solid rgba(16,185,129,0.28)',
                            borderRadius: '999px', padding: '3px 5px', fontWeight: 800
                          }}>
                            {match.label}
                          </span>
                        )}
                        {getStatusIcon(t.name)}
                      </div>
                      {isLatex && tags.length > 0 && (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginTop: '6px', paddingLeft: '18px' }}>
                          {tags.map(tag => (
                            <span key={tag} style={{
                              fontSize: '9px', lineHeight: 1,
                              color: tag.includes('ATS') ? '#86efac' : tag.includes('视觉') ? '#fda4af' : '#ddd6fe',
                              background: 'rgba(255,255,255,0.06)',
                              border: '1px solid rgba(255,255,255,0.10)',
                              borderRadius: '999px', padding: '3px 5px'
                            }}>
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
