import React, { useState, useEffect } from 'react';
import { Layers, FileText, RefreshCw } from 'lucide-react';

const STYLE_GROUPS = [
  { key: '极简', label: '极简单页', icon: '◻' },
  { key: '稳重', label: '稳重单页', icon: '◆' },
  { key: '简约', label: '简约单页', icon: '○' },
  { key: '活泼', label: '活泼单页', icon: '◇' },
  { key: '文艺', label: '文艺单页', icon: '♢' },
  { key: '知页', label: '知页简历', icon: '▣' },
];

export default function TemplatePanel({
  templateList,
  selectedTemplate,
  setSelectedTemplate,
  onReloadTemplates
}) {
  const [configStatus, setConfigStatus] = useState({});

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
    if (s.engineType === 'spatial') {
      return (
        <span 
          title="🎨 自由精雕模板：支持可视化画布拖拽、AI改写、全局字号颜色间距微调" 
          style={{ 
            color: '#3b82f6', 
            background: 'rgba(59,130,246,0.12)',
            border: '1px solid rgba(59,130,246,0.3)',
            borderRadius: '3px',
            padding: '1px 4px',
            fontSize: '9px',
            fontWeight: 700,
            marginLeft: 'auto'
          }}
        >
          🎨 自由精雕
        </span>
      );
    }
    if (s.engineType === 'docxtpl') {
      return (
        <span 
          title="📄 智能分页模板：支持多页自动延展，适合内容丰富的简历" 
          style={{ 
            color: '#10b981', 
            background: 'rgba(16,185,129,0.12)',
            border: '1px solid rgba(16,185,129,0.3)',
            borderRadius: '3px',
            padding: '1px 4px',
            fontSize: '9px',
            fontWeight: 700,
            marginLeft: 'auto'
          }}
        >
          📄 智能分页
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
    if (t.kind === 'latex' || t.engineType === 'latex') {
      group = t.group || 'LaTeX 模板';
    } else {
      for (const g of STYLE_GROUPS) {
        if (t.name.startsWith(g.key)) { group = g.label; break; }
      }
    }
    if (!grouped[group]) grouped[group] = [];
    grouped[group].push(t);
  });

  const handleSelectDir = async () => {
    if (!window.electronAPI) return;
    const result = await window.electronAPI.selectTemplateDir();
    if (result.success && onReloadTemplates) {
      onReloadTemplates();
    }
  };

  return (
    <div className="glass-panel template-panel" style={{ color: '#f3f4f6' }}>
      <div style={{
        padding: '16px 18px', borderBottom: '1px solid var(--border-glass)',
        fontSize: '14px', fontWeight: 700, display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', background: 'rgba(0,0,0,0.1)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Layers size={16} style={{ color: 'var(--color-accent)' }} /> 选择模板 ({templateList.length})
        </div>
        <button onClick={handleSelectDir} title="选择模板文件夹" style={{
          background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.12)',
          borderRadius: '4px', padding: '3px 8px', cursor: 'pointer',
          color: 'var(--color-text-muted)', fontSize: '11px', display: 'flex',
          alignItems: 'center', gap: '4px'
        }}>
          <RefreshCw size={11} /> 更换
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
            <div>未找到模板文件</div>
            <button onClick={handleSelectDir} style={{
              padding: '8px 16px', background: 'rgba(59,130,246,0.15)',
              border: '1px solid rgba(59,130,246,0.3)', borderRadius: '6px',
              color: '#93c5fd', cursor: 'pointer', fontSize: '12px', fontWeight: 600
            }}>
              选择模板文件夹
            </button>
          </div>
        ) : (
          Object.entries(grouped).map(([group, templates]) => (
            <div key={group}>
              <div style={{
                fontSize: '11px', fontWeight: 700, color: 'var(--color-text-muted)',
                marginBottom: '6px', paddingLeft: '8px',
                borderLeft: '2px solid var(--color-accent)'
              }}>
                {group} ({templates.length})
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                {templates.map(t => {
                  const isSelected = selectedTemplate?.name === t.name;
                  const isLatex = t.kind === 'latex' || t.engineType === 'latex';
                  const tags = (t.tags || []).slice(0, 4);
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
          ))
        )}
      </div>
    </div>
  );
}
