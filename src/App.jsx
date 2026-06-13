import React, { useState, useEffect, useCallback } from 'react';
import confetti from 'canvas-confetti';
import { Bell, Settings, PenLine, FileText, LayoutTemplate } from 'lucide-react';
import EditorPanel from './components/EditorPanel';
import PreviewPanel from './components/PreviewPanel';
import TemplatePanel from './components/TemplatePanel';
import UpdateNotification from './components/UpdateNotification';
import ApiConfigModal from './components/ApiConfigModal';
import { DEFAULT_RESUME_DATA } from './utils/aiParser';
import { getWebLatexTemplates, renderLatexSourceWeb } from './utils/webLatexFallback';

export default function App() {
  const [resumeData, setResumeData] = useState(DEFAULT_RESUME_DATA);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [templateList, setTemplateList] = useState([]);
  const [previewDocxBase64, setPreviewDocxBase64] = useState('');
  const [previewImageBase64, setPreviewImageBase64] = useState('');
  const [previewPdfBase64, setPreviewPdfBase64] = useState('');
  const [previewTexSource, setPreviewTexSource] = useState('');
  const [previewMessage, setPreviewMessage] = useState('');
  const [manualLatexPreview, setManualLatexPreview] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [notification, setNotification] = useState(null);
  const [showApiConfig, setShowApiConfig] = useState(false);
  const [templateEngineType, setTemplateEngineType] = useState('yaml');
  const [isDesensitized, setIsDesensitized] = useState(false);
  const [layoutAdjustments, setLayoutAdjustments] = useState({});
  const previewTimerRef = React.useRef(null);
  const previewRequestIdRef = React.useRef(0);
  const isElectronRuntime = Boolean(window.electronAPI);
  const [mobileView, setMobileView] = useState('edit');

  // Deep clone and obfuscate personal data fields for desensitized outputs
  const getDesensitizedData = (data) => {
    const copy = JSON.parse(JSON.stringify(data));
    if (copy.basicInfo) {
      const rawName = copy.basicInfo.name || '';
      copy.basicInfo.name = rawName.length > 1 ? `${rawName[0]}${'*'.repeat(rawName.length - 1)}` : '求职者';
      if (copy.basicInfo.phone) {
        copy.basicInfo.phone = copy.basicInfo.phone.replace(/(\d{3})\d{4}(\d{4})/, '$1****$2');
      }
      if (copy.basicInfo.email) {
        copy.basicInfo.email = copy.basicInfo.email.replace(/(.{2}).*(@.*)/, '$1***$2');
      }
      if (copy.basicInfo.wechat) {
        copy.basicInfo.wechat = '***';
      }
      copy.basicInfo.photo = '';
    }
    return copy;
  };

  const loadTemplates = useCallback(() => {
    if (window.electronAPI) {
      window.electronAPI.getTemplateList().then(list => {
        setTemplateList(list);
        if (list.length > 0 && !selectedTemplate) {
          setSelectedTemplate(list[0]);
        }
      });
    } else {
      const list = getWebLatexTemplates();
      setTemplateList(list);
      if (list.length > 0 && !selectedTemplate) {
        setSelectedTemplate(list[0]);
      }
    }
  }, [selectedTemplate]);

  useEffect(() => {
    loadTemplates();
  }, []);

  useEffect(() => {
    if (!selectedTemplate) {
      setTemplateEngineType('latex');
      setPreviewDocxBase64('');
      setPreviewImageBase64('');
      setPreviewPdfBase64('');
      setPreviewTexSource('');
      setPreviewMessage('');
      return;
    }

    if (!window.electronAPI) {
      setTemplateEngineType('latex');
      setPreviewDocxBase64('');
      setPreviewImageBase64('');
      setPreviewPdfBase64('');
      setPreviewTexSource('');
      setPreviewMessage('移动/Web 预览模式：可生成 .tex 源码；PDF 编译请在桌面版或 Overleaf 中完成。');
      setLayoutAdjustments({});
      setManualLatexPreview(false);
      return;
    }

    let cancelled = false;
    const immediateEngineType = selectedTemplate.engineType || (selectedTemplate.kind === 'latex' ? 'latex' : 'yaml');
    // Reset immediately so a previous template cannot leak stale DOCX/PNG preview
    // into the newly-selected engine while config loads.
    setTemplateEngineType(immediateEngineType);
    setPreviewDocxBase64('');
    setPreviewImageBase64('');
    setPreviewPdfBase64('');
    setPreviewTexSource('');
    setPreviewMessage('');
    setLayoutAdjustments({});
    setManualLatexPreview(false);

    window.electronAPI.checkTemplateConfig(selectedTemplate.path)
      .then(res => {
        if (!cancelled) setTemplateEngineType(res.engineType || immediateEngineType || 'yaml');
      })
      .catch(err => {
        console.error('Template config check error:', err);
        if (!cancelled) setTemplateEngineType(immediateEngineType || 'yaml');
      });

    return () => { cancelled = true; };
  }, [selectedTemplate?.name, selectedTemplate?.path, selectedTemplate?.engineType, selectedTemplate?.kind]);

  useEffect(() => {
    if (!selectedTemplate || manualLatexPreview) {
      if (manualLatexPreview) return;
      previewRequestIdRef.current += 1;
      setPreviewDocxBase64('');
      setPreviewImageBase64('');
      setPreviewPdfBase64('');
      setPreviewTexSource('');
      setPreviewMessage('');
      setPreviewLoading(false);
      return;
    }

    if (!window.electronAPI) {
      if (previewTimerRef.current) {
        clearTimeout(previewTimerRef.current);
      }
      const requestId = previewRequestIdRef.current + 1;
      previewRequestIdRef.current = requestId;
      previewTimerRef.current = setTimeout(() => {
        if (requestId !== previewRequestIdRef.current) return;
        const rawData = JSON.parse(JSON.stringify(resumeData));
        const dataForWeb = isDesensitized ? getDesensitizedData(rawData) : rawData;
        const texSource = renderLatexSourceWeb(dataForWeb, selectedTemplate, layoutAdjustments);
        setPreviewDocxBase64('');
        setPreviewImageBase64('');
        setPreviewPdfBase64('');
        setPreviewTexSource(texSource);
        setPreviewMessage('移动/Web 预览模式：已生成 LaTeX 源码，可下载 .tex；PDF 编译在桌面版执行。');
        setPreviewLoading(false);
      }, 300);
      return () => {
        if (previewTimerRef.current) clearTimeout(previewTimerRef.current);
      };
    }

    if (previewTimerRef.current) {
      clearTimeout(previewTimerRef.current);
    }

    const requestId = previewRequestIdRef.current + 1;
    previewRequestIdRef.current = requestId;
    previewTimerRef.current = setTimeout(() => {
      setPreviewLoading(true);
      const rawData = JSON.parse(JSON.stringify(resumeData));
      const dataForIpc = isDesensitized ? getDesensitizedData(rawData) : rawData;
      window.electronAPI.renderPreview(selectedTemplate.name, dataForIpc, layoutAdjustments)
        .then(result => {
          if (requestId !== previewRequestIdRef.current) return;
          if (result.success) {
            setPreviewDocxBase64(result.docxBase64 || '');
            setPreviewImageBase64(result.previewImageBase64 || '');
            setPreviewPdfBase64(result.previewPdfBase64 || '');
            setPreviewTexSource(result.texSource || '');
            setPreviewMessage(result.message || '');
          } else {
            console.error('Preview error:', result.error);
            setPreviewMessage(result.error || '预览渲染失败');
            showNotification({ type: 'warning', message: `预览渲染失败: ${result.error}` });
          }
          setPreviewLoading(false);
        })
        .catch(err => {
          if (requestId !== previewRequestIdRef.current) return;
          console.error('Preview IPC error:', err);
          setPreviewMessage(err.message || '预览 IPC 错误');
          showNotification({ type: 'warning', message: `预览 IPC 错误: ${err.message}` });
          setPreviewLoading(false);
        });
    }, 1500);
    return () => {
      if (previewTimerRef.current) clearTimeout(previewTimerRef.current);
    };
  }, [resumeData, selectedTemplate, templateEngineType, isDesensitized, layoutAdjustments, manualLatexPreview]);

  const showNotification = useCallback(({ type, message }) => {
    setNotification({ type, message });
    if (type === 'success' && message.includes('成功')) {
      confetti({ particleCount: 140, spread: 80, origin: { y: 0.6 } });
    }
    setTimeout(() => setNotification(null), 4500);
  }, []);

  const mobileTabs = [
    { key: 'edit', label: '填写', icon: PenLine },
    { key: 'preview', label: '预览', icon: FileText },
    { key: 'templates', label: '模板', icon: LayoutTemplate },
  ];

  const mobilePanelClass = (key) => `mobile-panel ${mobileView === key ? 'mobile-panel-active' : ''}`;

  return (
    <div className={`workspace-container ${isElectronRuntime ? 'desktop-runtime' : 'mobile-runtime'}`}>
      {!isElectronRuntime && (
        <div className="mobile-app-shell print-hide">
          <div>
            <div className="mobile-app-kicker">LaTeX Resume Studio</div>
            <div className="mobile-app-title">手机端 .tex 简历生成器</div>
          </div>
          <button
            className="mobile-primary-action"
            onClick={() => setMobileView('preview')}
          >
            生成预览
          </button>
        </div>
      )}
      {isElectronRuntime && (
        <div className="desktop-app-chrome print-hide">
          <div className="desktop-brand-mark" aria-hidden="true">TeX</div>
          <div className="desktop-brand-copy">
            <div className="desktop-brand-kicker">LaTeX Resume Studio</div>
            <div className="desktop-brand-title">LaTeX 简历工坊</div>
          </div>
          <div className="desktop-status-strip">
            <span>{templateList.length || 0} 套 LaTeX 模板</span>
            <span>{selectedTemplate?.displayName || selectedTemplate?.name || '未选择模板'}</span>
            <span>{templateEngineType === 'latex' ? 'PDF / .tex 工作流' : '模板检测中'}</span>
          </div>
          <button
            className="desktop-config-button"
            onClick={() => setShowApiConfig(true)}
            title="AI 接口配置"
          >
            <Settings size={15} /> AI 设置
          </button>
        </div>
      )}
      {notification && (
        <div className="print-hide" style={{
          position: 'fixed', top: '20px', left: '50%', transform: 'translateX(-50%)',
          zIndex: 9999, padding: '12px 24px', borderRadius: '10px',
          backdropFilter: 'blur(20px)',
          background: notification.type === 'success' ? 'rgba(16,185,129,0.25)' :
            notification.type === 'warning' ? 'rgba(245,158,11,0.25)' : 'rgba(59,130,246,0.25)',
          border: `1px solid ${notification.type === 'success' ? 'rgba(16,185,129,0.4)' :
            notification.type === 'warning' ? 'rgba(245,158,11,0.4)' : 'rgba(59,130,246,0.4)'}`,
          boxShadow: '0 10px 40px rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center',
          gap: '10px', color: '#fff', fontSize: '13.5px', fontWeight: 600,
          animation: 'slideDown 0.3s cubic-bezier(0.16,1,0.3,1) forwards'
        }}>
          <Bell size={16} /><span>{notification.message}</span>
        </div>
      )}

      <div className={mobilePanelClass('edit')}>
        <EditorPanel
          resumeData={resumeData}
          setResumeData={setResumeData}
          onNotification={showNotification}
          onOpenApiConfig={() => setShowApiConfig(true)}
          engineType={templateEngineType}
        />
      </div>

      <div className={mobilePanelClass('preview')}>
        <PreviewPanel
          previewDocxBase64={previewDocxBase64}
          previewImageBase64={previewImageBase64}
          previewPdfBase64={previewPdfBase64}
          previewTexSource={previewTexSource}
          previewMessage={previewMessage}
          setPreviewMessage={setPreviewMessage}
          setPreviewImageBase64={setPreviewImageBase64}
          setPreviewPdfBase64={setPreviewPdfBase64}
          setPreviewTexSource={setPreviewTexSource}
          manualLatexPreview={manualLatexPreview}
          setManualLatexPreview={setManualLatexPreview}
          previewLoading={previewLoading}
          setPreviewLoading={setPreviewLoading}
          onNotification={showNotification}
          selectedTemplate={selectedTemplate}
          resumeData={resumeData}
          setResumeData={setResumeData}
          engineType={templateEngineType}
          isDesensitized={isDesensitized}
          setIsDesensitized={setIsDesensitized}
          layoutAdjustments={layoutAdjustments}
          setLayoutAdjustments={setLayoutAdjustments}
        />
      </div>

      <div className={mobilePanelClass('templates')}>
        <TemplatePanel
          templateList={templateList}
          selectedTemplate={selectedTemplate}
          setSelectedTemplate={(template) => {
            setSelectedTemplate(template);
            if (!isElectronRuntime) setMobileView('preview');
          }}
          onReloadTemplates={loadTemplates}
          resumeData={resumeData}
        />
      </div>

      <UpdateNotification />

      {showApiConfig && (
        <ApiConfigModal onClose={() => setShowApiConfig(false)} onNotification={showNotification} />
      )}

      {!isElectronRuntime && (
        <nav className="mobile-tabbar print-hide" aria-label="移动端导航">
          {mobileTabs.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              className={mobileView === key ? 'active' : ''}
              onClick={() => setMobileView(key)}
            >
              <Icon size={18} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
      )}

      <style>{`
        @keyframes slideDown {
          from { transform: translate(-50%, -30px); opacity: 0; }
          to { transform: translate(-50%, 0); opacity: 1; }
        }
      `}</style>
    </div>
  );
}
