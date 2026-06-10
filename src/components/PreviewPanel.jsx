import React, { useState, useEffect } from 'react';
import { Printer, FileText, Loader, Eye, EyeOff, Palette, Type, Space, Camera, Sparkles } from 'lucide-react';
import { renderAsync } from 'docx-preview';
import { polishText, suggestLatexAdjustments } from '../utils/aiParser';
import { canUseNativeTectonic, getNativeTectonicStatus } from '../utils/mobileTectonic';
import { saveTextFileMobile } from '../utils/webLatexFallback';
import SnapshotModal from './SnapshotModal';
import InteractiveCanvas from './InteractiveCanvas';

export default function PreviewPanel({
  previewDocxBase64,
  previewImageBase64,
  previewPdfBase64,
  previewTexSource,
  previewMessage,
  setPreviewMessage,
  setPreviewImageBase64,
  setPreviewPdfBase64,
  setPreviewTexSource,
  manualLatexPreview,
  setManualLatexPreview,
  previewLoading,
  setPreviewLoading,
  onNotification,
  selectedTemplate,
  resumeData,
  setResumeData,
  engineType,
  isDesensitized,
  setIsDesensitized,
  layoutAdjustments,
  setLayoutAdjustments
}) {
  const [canvasScale, setCanvasScale] = useState(0.7);

  // Advanced Layout Control States (Used for spatial templates coordinate rewrites on the backend)
  const [themeColor, setThemeColor] = useState('');
  const [fontSizeOffset, setFontSizeOffset] = useState(0);
  const [spacingOffset, setSpacingOffset] = useState(0);
  const [showSnapshotModal, setShowSnapshotModal] = useState(false);

  // AI Content Polish floating bubble state for flow layouts
  const [polishState, setPolishState] = useState(null); // { id, x, y, text }
  const [polishing, setPolishing] = useState(false);

  const docxContainerRef = React.useRef(null);
  const docxRenderRequestRef = React.useRef(0);
  const hasElectronApi = Boolean(window.electronAPI);
  const isLatex = engineType === 'latex' || selectedTemplate?.kind === 'latex' || selectedTemplate?.engineType === 'latex';
  const isSpatial = engineType === 'spatial';
  const [latexCompilerStatus, setLatexCompilerStatus] = useState(null);
  const [showLatexEditor, setShowLatexEditor] = useState(false);
  const [showLatexSourceMode, setShowLatexSourceMode] = useState(false);
  const [latexDraftSource, setLatexDraftSource] = useState('');
  const [latexEditCompiling, setLatexEditCompiling] = useState(false);
  const [aiLatexAdjusting, setAiLatexAdjusting] = useState(false);
  const [nativeTectonicChecking, setNativeTectonicChecking] = useState(false);
  const [nativeTectonicStatus, setNativeTectonicStatus] = useState(null);
  const latexVisual = {
    accentColor: '#2563EB',
    fontScale: 1,
    spacingScale: 1,
    photoScale: 1,
    photoPosition: 'right',
    photoShape: 'rounded',
    showPhoto: true,
    compactMode: false,
    ...(layoutAdjustments || {})
  };

  const handleCheckNativeTectonic = async () => {
    if (!canUseNativeTectonic()) {
      onNotification({ type: 'warning', message: '当前不是 Android 原生环境，无法检测内置 Tectonic。' });
      return;
    }
    if (nativeTectonicChecking) return;

    setNativeTectonicChecking(true);
    try {
      const status = await getNativeTectonicStatus();
      setNativeTectonicStatus(status);
      if (status.available) {
        const version = status.stdout || 'Tectonic 已可执行';
        setPreviewMessage(`Android 内置 Tectonic 健康检查通过：${version}`);
        onNotification({ type: 'success', message: `Android 内置 Tectonic 可执行：${version}` });
      } else {
        const message = status.error || status.stderr || '当前 APK 未内置可执行 Tectonic 引擎。';
        setPreviewMessage(`Android 内置 Tectonic 暂不可用：${message}`);
        onNotification({ type: 'warning', message: `Android 内置 Tectonic 暂不可用：${message}` });
      }
    } catch (err) {
      const message = err?.message || String(err);
      setNativeTectonicStatus({ available: false, error: message });
      setPreviewMessage(`Android 内置 Tectonic 检测失败：${message}`);
      onNotification({ type: 'warning', message: `Android 内置 Tectonic 检测失败：${message}` });
    } finally {
      setNativeTectonicChecking(false);
    }
  };

  const updateLatexVisual = (patch) => {
    setManualLatexPreview(false);
    setLayoutAdjustments(prev => ({ ...(prev || {}), ...patch }));
  };

  const updateBasicFromPreview = (field, value) => {
    setManualLatexPreview(false);
    setResumeData(prev => ({
      ...prev,
      basicInfo: {
        ...(prev.basicInfo || {}),
        [field]: value
      }
    }));
  };

  const handleAILatexAdjust = async () => {
    if (!isLatex || !selectedTemplate || aiLatexAdjusting) return;
    setManualLatexPreview(false);
    setAiLatexAdjusting(true);
    try {
      const config = window.electronAPI?.getApiConfig ? await window.electronAPI.getApiConfig() : {};
      onNotification({ type: 'info', message: config?.apiUrl ? 'AI 正在分析当前 LaTeX 版式...' : '未配置 AI，正在使用本地规则调版...' });
      const suggestion = await suggestLatexAdjustments(
        isDesensitized ? getDesensitizedData(resumeData) : resumeData,
        selectedTemplate,
        layoutAdjustments || {},
        config || {}
      );
      setLayoutAdjustments(prev => ({ ...(prev || {}), ...(suggestion.adjustments || {}) }));
      setPreviewMessage(`已应用${suggestion.source === 'api' ? 'AI' : '本地'} LaTeX 调版建议：${suggestion.rationale || '已优化当前模板视觉参数。'}`);
      onNotification({
        type: suggestion.source === 'api' ? 'success' : 'info',
        message: `${suggestion.source === 'api' ? 'AI' : '本地规则'}调版已应用：${suggestion.rationale || '已优化当前 LaTeX 版式'}`
      });
    } catch (err) {
      onNotification({ type: 'warning', message: `AI LaTeX 调版失败: ${err.message}` });
    } finally {
      setAiLatexAdjusting(false);
    }
  };

  // Automatically trigger backend re-rendering when adjustments change in spatial mode
  useEffect(() => {
    if (engineType === 'spatial' && selectedTemplate) {
      // Pack global adjustments into layoutAdjustments state map
      setLayoutAdjustments({
        __global_color__: themeColor || null,
        __global_font_size__: fontSizeOffset || 0,
        __global_spacing__: spacingOffset || 0
      });
    }
  }, [themeColor, fontSizeOffset, spacingOffset, selectedTemplate?.name, engineType]);

  useEffect(() => {
    // Reset layout adjustments when the template changes
    setLayoutAdjustments({});
    setThemeColor('');
    setFontSizeOffset(0);
    setSpacingOffset(0);
    setPolishState(null);
  }, [selectedTemplate?.name]);

  useEffect(() => {
    if (!window.electronAPI) return;

    const cleanups = [
      window.electronAPI.onWordSaved((msg) => onNotification({ type: 'success', message: msg })),
      window.electronAPI.onWordFailed((msg) => onNotification({ type: 'warning', message: msg })),
      window.electronAPI.onPdfSaved((msg) => onNotification({ type: 'success', message: msg })),
      window.electronAPI.onPdfFailed((msg) => onNotification({ type: 'warning', message: msg })),
    ];

    if (window.electronAPI.onLatexTexSaved) {
      cleanups.push(window.electronAPI.onLatexTexSaved((msg) => onNotification({ type: 'success', message: msg })));
    }
    if (window.electronAPI.onLatexTexFailed) {
      cleanups.push(window.electronAPI.onLatexTexFailed((msg) => onNotification({ type: 'warning', message: msg })));
    }
    if (window.electronAPI.onLatexPdfSaved) {
      cleanups.push(window.electronAPI.onLatexPdfSaved((msg) => onNotification({ type: 'success', message: msg })));
    }
    if (window.electronAPI.onLatexPdfFailed) {
      cleanups.push(window.electronAPI.onLatexPdfFailed((msg) => onNotification({ type: 'warning', message: msg })));
    }

    return () => cleanups.forEach(fn => fn && fn());
  }, [onNotification]);

  useEffect(() => {
    if (!isLatex || !window.electronAPI?.getLatexCompilerStatus) {
      setLatexCompilerStatus(null);
      return;
    }

    let cancelled = false;
    setLatexCompilerStatus(null);
    window.electronAPI.getLatexCompilerStatus()
      .then(status => {
        if (!cancelled) setLatexCompilerStatus(status);
      })
      .catch(err => {
        if (!cancelled) {
          setLatexCompilerStatus({
            success: false,
            compiler: {
              available: false,
              message: `无法检测 LaTeX 编译器：${err.message}`
            }
          });
        }
      });

    return () => { cancelled = true; };
  }, [isLatex, selectedTemplate?.name]);

  useEffect(() => {
    if (!manualLatexPreview) setLatexDraftSource(previewTexSource || '');
  }, [previewTexSource, manualLatexPreview]);

  // 1:1 High fidelity render of docx in preview container via docx-preview
  useEffect(() => {
    if (!previewDocxBase64 || previewImageBase64 || !docxContainerRef.current || isSpatial) return;

    const requestId = docxRenderRequestRef.current + 1;
    docxRenderRequestRef.current = requestId;
    const visibleContainer = docxContainerRef.current;
    let cancelled = false;

    // docx-preview's stable public API renders into a real DOM element. Rendering
    // into a detached/off-DOM staging node can lose styles/text in packaged
    // Electron, so keep the official direct-container pattern and use request IDs
    // only to ignore stale completions/notifications.
    visibleContainer.removeEventListener('dblclick', handleDocxDblClick);
    visibleContainer.innerHTML = "";

    // Base64 to ArrayBuffer conversion
    const binaryString = atob(previewDocxBase64);
    const len = binaryString.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    const arrayBuffer = bytes.buffer;

    renderAsync(arrayBuffer, visibleContainer, null, {
      className: "docx",
      inWrapper: false,
      ignoreWidth: true, // Let the layout fill parent container to prevent horizontal clipping
      ignoreHeight: false
    }).then(() => {
      if (cancelled || requestId !== docxRenderRequestRef.current || !docxContainerRef.current) return;
      visibleContainer.addEventListener('dblclick', handleDocxDblClick);
    }).catch(err => {
      if (cancelled || requestId !== docxRenderRequestRef.current) return;
      console.error("docx-preview render error:", err);
      onNotification({ type: 'warning', message: `Word 高清预览渲染失败: ${err.message}` });
    });

    return () => {
      cancelled = true;
      docxRenderRequestRef.current += 1;
      visibleContainer.removeEventListener('dblclick', handleDocxDblClick);
    };
  }, [previewDocxBase64, previewImageBase64, isSpatial]);

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

  // Heuristic Semantic Source Sync Algorithm (Traverses and replaces matching nodes in resumeData)
  const syncSemanticText = (data, oldText, newText) => {
    const cleanOld = oldText.trim();
    const cleanNew = newText.trim();
    if (!cleanOld || cleanOld === cleanNew) return data;

    const copy = JSON.parse(JSON.stringify(data));
    let replaced = false;

    const isMatch = (valStr, targetStr) => {
      const v = valStr.trim();
      const t = targetStr.trim();
      if (!v || !t) return false;
      return v === t || v.includes(t) || t.includes(v);
    };

    const traverse = (obj) => {
      if (replaced) return;
      for (const key in obj) {
        if (replaced) return;
        const val = obj[key];

        if (typeof val === 'string') {
          if (isMatch(val, cleanOld)) {
            if (val.includes(cleanOld)) {
              obj[key] = val.replace(cleanOld, cleanNew);
            } else {
              obj[key] = cleanNew;
            }
            replaced = true;
            return;
          }
        } else if (Array.isArray(val)) {
          for (let i = 0; i < val.length; i++) {
            if (replaced) return;
            if (typeof val[i] === 'string') {
              if (isMatch(val[i], cleanOld)) {
                if (val[i].includes(cleanOld)) {
                  val[i] = val[i].replace(cleanOld, cleanNew);
                } else {
                  val[i] = cleanNew;
                }
                replaced = true;
                return;
              }
            } else if (typeof val[i] === 'object' && val[i] !== null) {
              traverse(val[i]);
            }
          }
        } else if (typeof val === 'object' && val !== null) {
          traverse(val);
        }
      }
    };

    traverse(copy);
    return copy;
  };

  // Handle Double Click to edit non-spatial template text node on screen
  const handleDocxDblClick = (e) => {
    const target = e.target;
    if (!target) return;

    // Filter out structural nodes to prevent overall paragraph edit blocks
    const structuralContainers = new Set(['TABLE', 'TBODY', 'TR', 'THEAD', 'SECTION', 'ARTICLE']);
    if (structuralContainers.has(target.tagName)) return;

    const oldText = target.innerText.trim();
    if (!oldText) return;

    target.setAttribute('data-editing', 'true');
    target.id = 'temp_editing_node';

    target.contentEditable = true;
    target.focus();
    
    target.style.outline = '1.5px dashed #3b82f6';
    target.style.cursor = 'text';

    // Toggle floating AI polish menu
    const container = document.querySelector('.a4-container');
    if (container) {
      const containerRect = container.getBoundingClientRect();
      const targetRect = target.getBoundingClientRect();
      const relativeX = (targetRect.left + targetRect.width / 2 - containerRect.left) / canvasScale;
      const relativeY = (targetRect.top - containerRect.top) / canvasScale;

      setPolishState({
        id: 'temp_editing_node',
        x: relativeX,
        y: relativeY - 15,
        text: oldText
      });
    }

    const handleBlur = () => {
      setTimeout(() => {
        target.contentEditable = false;
        target.style.outline = 'none';
        target.style.cursor = 'default';
        target.removeAttribute('data-editing');
        target.removeAttribute('id');

        const newText = target.innerText.trim();
        if (newText && newText !== oldText) {
          const updated = syncSemanticText(resumeData, oldText, newText);
          setResumeData(updated);
          onNotification({ type: 'success', message: '已实时同步修改至简历数据！' });
        }
      }, 250);
    };

    target.addEventListener('blur', handleBlur, { once: true });
  };

  // AI Content Polish for flow layout template text
  const handleAIPolish = async (mode) => {
    if (!polishState || polishing || !window.electronAPI) return;
    
    setPolishing(true);
    try {
      const config = await window.electronAPI.getApiConfig();
      if (!config.apiUrl || !config.apiKey) {
        onNotification({ type: 'warning', message: '⚠️ 请先配置 AI 大模型 API！点击左上角设置。' });
        setPolishing(false);
        return;
      }
      
      onNotification({ type: 'info', message: `✨ AI 正在处理 (${mode === 'star' ? 'STAR改写' : mode === 'shorten' ? '精简篇幅' : '专业润色'})...` });
      const polishedResult = await polishText(polishState.text, config, mode);
      
      // Update targeted node in docx-preview DOM
      const targetNode = document.getElementById('temp_editing_node');
      if (targetNode) {
        targetNode.innerText = polishedResult;
        const updated = syncSemanticText(resumeData, polishState.text, polishedResult);
        setResumeData(updated);
      }
      
      onNotification({ type: 'success', message: '✨ AI 内容重塑完成并自动保存！' });
      setPolishState(null);
    } catch (e) {
      console.error("AI Flow Polish error:", e);
      onNotification({ type: 'warning', message: `润色失败: ${e.message}` });
    } finally {
      setPolishing(false);
    }
  };

  // 100% "What You See Is What You Get" high-fidelity PDF printing for DOCX,
  // or backend LaTeX PDF compilation when a LaTeX template is selected.
  const handlePrint = () => {
    if (isLatex) {
      if (!selectedTemplate) {
        onNotification({ type: 'warning', message: '请先选择 LaTeX 模板' });
        return;
      }
      if (!window.electronAPI) {
        onNotification({ type: 'warning', message: '移动/Web 版本暂不内置 LaTeX 编译器；请先导出 .tex 后用桌面版或 Overleaf 编译 PDF。' });
        return;
      }
      if (latexCompilerStatus?.compiler && !latexCompilerStatus.compiler.available) {
        onNotification({
          type: 'warning',
          message: latexCompilerStatus.compiler.message || '未检测到 LaTeX 编译器；当前可先导出 .tex。'
        });
        return;
      }
      const dataToExport = isDesensitized ? getDesensitizedData(resumeData) : resumeData;
      onNotification({ type: 'info', message: '正在使用 LaTeX 编译 PDF...' });
      window.electronAPI.exportLatexPdf(selectedTemplate.name, dataToExport, layoutAdjustments);
      return;
    }

    let htmlContent = '';
    const sourceNode = previewImageBase64
      ? docxContainerRef.current
      : (isSpatial ? document.querySelector('.a4-sheet') : docxContainerRef.current);

    if (sourceNode) {
      const clone = sourceNode.cloneNode(true);
      clone.querySelectorAll('[contenteditable]').forEach(el => el.removeAttribute('contenteditable'));
      clone.querySelectorAll('[data-editing]').forEach(el => el.removeAttribute('data-editing'));
      htmlContent = clone.outerHTML;
    }

    if (!htmlContent) {
      onNotification({ type: 'warning', message: '生成打印文件内容为空，请稍后' });
      return;
    }

    const dataToExport = isDesensitized ? getDesensitizedData(resumeData) : resumeData;
    const defaultName = `${dataToExport.basicInfo.name || '我的'}_求职简历.pdf`;
    
    if (window.electronAPI) {
      onNotification({ type: 'info', message: '正在生成高保真 PDF...' });
      window.electronAPI.printToPdf(defaultName, htmlContent);
    } else {
      onNotification({ type: 'success', message: '当前处于网页端，请使用浏览器打印' });
      window.print();
    }
  };

  const handleExportWord = () => {
    if (!window.electronAPI || !selectedTemplate) {
      onNotification({ type: 'warning', message: '请先选择模板' });
      return;
    }
    if (isLatex) {
      onNotification({ type: 'warning', message: 'LaTeX 模板不支持 Word 导出，请使用“导出 .tex”或“编译 PDF”。' });
      return;
    }
    const dataToExport = isDesensitized ? getDesensitizedData(resumeData) : resumeData;
    onNotification({ type: 'info', message: `正在导出到 "${selectedTemplate.name}"...` });
    window.electronAPI.exportToWord(selectedTemplate.name, dataToExport, layoutAdjustments);
  };

  const handleExportLatexTex = async () => {
    if (!selectedTemplate || !isLatex) {
      onNotification({ type: 'warning', message: '请先选择 LaTeX 模板' });
      return;
    }
    if (!window.electronAPI) {
      if (!previewTexSource?.trim()) {
        onNotification({ type: 'warning', message: '当前还没有生成 LaTeX 源码，请稍后再试。' });
        return;
      }
      const safeName = `${resumeData?.basicInfo?.name || 'resume'}_${selectedTemplate?.name || 'latex'}`.replace(/[\\/:*?"<>|\s]+/g, '_');
      try {
        const result = await saveTextFileMobile(`${safeName}.tex`, previewTexSource);
        onNotification({
          type: 'success',
          message: result.native
            ? '已保存到 Android 文档目录，并已打开系统分享面板'
            : '已在当前设备下载 .tex 源文件'
        });
      } catch (err) {
        onNotification({ type: 'warning', message: `保存 .tex 失败：${err.message}` });
      }
      return;
    }
    const dataToExport = isDesensitized ? getDesensitizedData(resumeData) : resumeData;
    onNotification({ type: 'info', message: '正在生成 LaTeX 源文件...' });
    window.electronAPI.exportLatexTex(selectedTemplate.name, dataToExport, layoutAdjustments);
  };

  const handleApplyLatexSourcePreview = async () => {
    if (!isLatex) {
      onNotification({ type: 'warning', message: '当前模板不是 LaTeX 模板' });
      return;
    }
    if (!window.electronAPI?.renderLatexSourcePreview) {
      if (latexDraftSource.trim()) {
        setManualLatexPreview(true);
        setPreviewTexSource(latexDraftSource);
        setPreviewImageBase64('');
        if (setPreviewPdfBase64) setPreviewPdfBase64('');
        setPreviewMessage('移动/Web 源码编辑已保存；PDF 重编译请在桌面版或 Overleaf 中完成。');
        onNotification({ type: 'success', message: 'LaTeX 源码修改已保存到当前预览' });
        return;
      }
      onNotification({ type: 'warning', message: '当前环境不支持 LaTeX 源码重编译预览' });
      return;
    }
    if (!latexDraftSource.trim()) {
      onNotification({ type: 'warning', message: 'LaTeX 源码为空，无法预览' });
      return;
    }

    setManualLatexPreview(true);
    setLatexEditCompiling(true);
    setPreviewLoading(true);
    setPreviewMessage('正在根据手动修改重新编译 LaTeX 预览...');
    try {
      const result = await window.electronAPI.renderLatexSourcePreview(
        latexDraftSource,
        `${resumeData?.basicInfo?.name || 'resume'}_${selectedTemplate?.name || 'latex'}_edited`,
        isDesensitized ? getDesensitizedData(resumeData) : resumeData
      );
      setPreviewTexSource(result.texSource || latexDraftSource);
      if (result.success && result.previewImageBase64) {
        setPreviewImageBase64(result.previewImageBase64);
        if (setPreviewPdfBase64) setPreviewPdfBase64('');
        setPreviewMessage(result.message || '已根据手动修改重新生成 LaTeX 预览。');
        onNotification({ type: 'success', message: 'LaTeX 源码修改已重新编译为预览' });
      } else if (result.success && result.previewPdfBase64) {
        setPreviewImageBase64('');
        if (setPreviewPdfBase64) setPreviewPdfBase64(result.previewPdfBase64);
        setPreviewMessage(result.message || '已根据手动修改重新生成 PDF 预览。');
        onNotification({ type: 'success', message: 'LaTeX 源码修改已重新编译为 PDF 预览' });
      } else {
        setPreviewMessage(result.error || result.message || 'LaTeX 源码编译失败，请检查语法。');
        onNotification({ type: 'warning', message: result.error || 'LaTeX 源码编译失败，请检查语法。' });
      }
    } catch (err) {
      setPreviewMessage(err.message || 'LaTeX 源码预览失败');
      onNotification({ type: 'warning', message: `LaTeX 源码预览失败: ${err.message}` });
    } finally {
      setLatexEditCompiling(false);
      setPreviewLoading(false);
    }
  };

  const handleRestoreAutoLatexPreview = () => {
    setManualLatexPreview(false);
    setPreviewMessage('已恢复按表单内容自动生成 LaTeX 预览。');
    onNotification({ type: 'info', message: '已恢复 LaTeX 自动预览' });
  };

  const handleApplySnapshot = (snappedData, snappedLayout) => {
    setResumeData(snappedData);
    setLayoutAdjustments(snappedLayout);
  };

  return (
    <div className="preview-panel">
      
      {/* Primary Export and Sizing Toolbar */}
      <div className="print-hide" style={{
        width: '100%', maxWidth: '850px',
        background: 'var(--bg-glass)', border: '1px solid var(--border-glass)',
        backdropFilter: 'blur(10px)', borderRadius: '12px',
        padding: '12px 18px', display: 'flex', justifyContent: 'space-between',
        alignItems: 'center', boxShadow: '0 4px 20px rgba(0,0,0,0.2)', zIndex: 100
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {isLatex ? (
            <>
              <button onClick={handleExportLatexTex} style={{
                padding: '8px 14px', background: 'linear-gradient(135deg, #8b5cf6, #6d28d9)',
                color: '#fff', border: 'none', borderRadius: '6px', fontWeight: 700,
                cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px',
                fontSize: '12px', boxShadow: '0 4px 12px rgba(139,92,246,0.25)'
              }}>
                <FileText size={14} /> 导出 .tex
              </button>
              <button onClick={() => setShowLatexEditor(!showLatexEditor)} style={{
                padding: '8px 14px', background: showLatexEditor ? 'rgba(20,184,166,0.18)' : 'rgba(255,255,255,0.06)',
                color: showLatexEditor ? '#5eead4' : '#d1d5db', border: `1px solid ${showLatexEditor ? 'rgba(20,184,166,0.35)' : 'rgba(255,255,255,0.12)'}`,
                borderRadius: '6px', fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px',
                fontSize: '12px'
              }}>
                <FileText size={14} /> 预览内编辑
              </button>
              <button onClick={handleAILatexAdjust} disabled={aiLatexAdjusting} style={{
                padding: '8px 14px', background: aiLatexAdjusting ? 'rgba(99,102,241,0.18)' : 'linear-gradient(135deg, #8b5cf6, #2563eb)',
                color: '#fff', border: 'none', borderRadius: '6px', fontWeight: 800,
                cursor: aiLatexAdjusting ? 'wait' : 'pointer', display: 'flex', alignItems: 'center', gap: '6px',
                fontSize: '12px', boxShadow: '0 4px 12px rgba(99,102,241,0.22)', opacity: aiLatexAdjusting ? 0.75 : 1
              }}>
                {aiLatexAdjusting ? <Loader size={14} className="animate-spin" /> : <Sparkles size={14} />} AI 调版
              </button>
            </>
          ) : (
            <button onClick={handleExportWord} style={{
              padding: '8px 14px', background: 'linear-gradient(135deg, #3b82f6, #1d4ed8)',
              color: '#fff', border: 'none', borderRadius: '6px', fontWeight: 700,
              cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px',
              fontSize: '12px', boxShadow: '0 4px 12px rgba(59,130,246,0.25)'
            }}>
              <FileText size={14} /> 导出 Word
            </button>
          )}
          <button onClick={handlePrint} style={{
            padding: '8px 14px', background: isLatex ? 'linear-gradient(135deg, #14b8a6, #0f766e)' : 'linear-gradient(135deg, #10b981, #059669)',
            color: '#fff', border: 'none', borderRadius: '6px', fontWeight: 700,
            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px',
            fontSize: '12px', boxShadow: '0 4px 12px rgba(16,185,129,0.25)'
          }}>
            <Printer size={14} /> {isLatex ? '编译 PDF' : '导出 PDF'}
          </button>

          {isLatex && !hasElectronApi && canUseNativeTectonic() && (
            <button onClick={handleCheckNativeTectonic} disabled={nativeTectonicChecking} style={{
              padding: '8px 14px', background: nativeTectonicStatus?.available ? 'linear-gradient(135deg, #22c55e, #15803d)' : 'linear-gradient(135deg, #f59e0b, #b45309)',
              color: '#fff', border: 'none', borderRadius: '6px', fontWeight: 800,
              cursor: nativeTectonicChecking ? 'wait' : 'pointer', display: 'flex', alignItems: 'center', gap: '6px',
              fontSize: '12px', boxShadow: '0 4px 12px rgba(245,158,11,0.22)', opacity: nativeTectonicChecking ? 0.75 : 1
            }}>
              {nativeTectonicChecking ? <Loader size={14} className="animate-spin" /> : <FileText size={14} />}
              检测本机 Tectonic
            </button>
          )}

          <div style={{ width: '1px', height: '20px', background: 'rgba(255,255,255,0.1)', margin: '0 4px' }} />

          {/* Privacy Desensitization Toggle */}
          <button onClick={() => setIsDesensitized(!isDesensitized)} style={{
            padding: '7px 12px', background: isDesensitized ? 'rgba(16,185,129,0.15)' : 'rgba(255,255,255,0.05)',
            border: `1px solid ${isDesensitized ? 'rgba(16,185,129,0.3)' : 'rgba(255,255,255,0.1)'}`,
            color: isDesensitized ? '#34d399' : '#d1d5db', borderRadius: '6px', cursor: 'pointer',
            fontSize: '12px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '5px',
            transition: 'all 0.2s'
          }}>
            {isDesensitized ? <EyeOff size={13} /> : <Eye size={13} />}
            隐私打码 {isDesensitized ? '已开' : '已关'}
          </button>

          {/* Snapshots Button */}
          <button onClick={() => setShowSnapshotModal(true)} style={{
            padding: '7px 12px', background: 'rgba(59,130,246,0.15)',
            border: '1px solid rgba(59,130,246,0.3)',
            color: '#60a5fa', borderRadius: '6px', cursor: 'pointer',
            fontSize: '12px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '5px',
            transition: 'all 0.2s'
          }}>
            <Camera size={13} /> 历史快照
          </button>

          <div style={{ width: '1px', height: '20px', background: 'rgba(255,255,255,0.1)', margin: '0 4px' }} />

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>缩放:</span>
            <input type="range" min="0.4" max="1.2" step="0.05" value={canvasScale}
              onChange={(e) => setCanvasScale(parseFloat(e.target.value))}
              style={{ width: '70px', height: '4px', cursor: 'pointer' }} />
            <span style={{ fontSize: '11px', fontWeight: 700, minWidth: '35px' }}>
              {Math.round(canvasScale * 100)}%
            </span>
          </div>
        </div>

        {selectedTemplate?.name && (
          <div style={{
            fontSize: '11px', color: 'var(--color-text-muted)',
            background: 'rgba(255,255,255,0.04)', padding: '4px 8px',
            borderRadius: '4px', maxWidth: '200px', overflow: 'hidden',
            textOverflow: 'ellipsis', whiteSpace: 'nowrap'
          }}>
            {selectedTemplate.name.replace('.docx', '')}
          </div>
        )}
      </div>

      {isLatex && (
        <div className="print-hide" style={{
          width: '100%', maxWidth: '850px', marginTop: '10px',
          background: !hasElectronApi ? 'rgba(59,130,246,0.10)' : (latexCompilerStatus?.compiler?.available ? 'rgba(20,184,166,0.10)' : 'rgba(245,158,11,0.10)'),
          border: `1px solid ${!hasElectronApi ? 'rgba(59,130,246,0.25)' : (latexCompilerStatus?.compiler?.available ? 'rgba(20,184,166,0.25)' : 'rgba(245,158,11,0.25)')}`,
          color: !hasElectronApi ? '#93c5fd' : (latexCompilerStatus?.compiler?.available ? '#5eead4' : '#fbbf24'),
          borderRadius: '10px', padding: '9px 12px', fontSize: '12px', lineHeight: 1.5
        }}>
          <strong>LaTeX 模板：</strong>
          {!hasElectronApi
            ? (nativeTectonicStatus?.available
              ? `Android 内置 Tectonic 可执行：${nativeTectonicStatus.stdout || 'version ok'}。当前先启用健康检查，PDF 编译入口待沙盒运行验证后开放。`
              : '移动/Web 预览模式已启用：当前可生成并下载 .tex；可检测 APK 是否内置 Android Tectonic 引擎。')
            : latexCompilerStatus?.compiler?.available
            ? `已检测到 ${latexCompilerStatus.compiler.name}，可编译 PDF；也可导出 .tex 到 Overleaf/本地继续调整。`
            : (latexCompilerStatus?.compiler?.message || '正在检测 LaTeX 编译器；即使没有编译器，也可以先导出 .tex。')}
        </div>
      )}

      {isLatex && (
        <div className="print-hide" style={{
          width: '100%', maxWidth: '850px', marginTop: '10px',
          background: 'rgba(15,23,42,0.72)', border: '1px solid rgba(148,163,184,0.16)',
          borderRadius: '12px', padding: '12px 14px', display: 'grid',
          gridTemplateColumns: '1.2fr 1fr 1fr', gap: '12px', alignItems: 'center'
        }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '7px' }}>
            <div style={{ fontSize: '11px', color: '#c4b5fd', fontWeight: 850 }}>预览可视调版</div>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              <select value={latexVisual.photoPosition} onChange={(e) => updateLatexVisual({ photoPosition: e.target.value })} style={{ background: '#0f172a', color: '#e5e7eb', border: '1px solid rgba(148,163,184,0.24)', borderRadius: '7px', padding: '6px 8px', fontSize: '11px' }}>
                <option value="right">照片右上</option>
                <option value="left">照片左上</option>
                <option value="top">照片居中</option>
                <option value="none">隐藏照片</option>
              </select>
              <select value={latexVisual.photoShape} onChange={(e) => updateLatexVisual({ photoShape: e.target.value })} style={{ background: '#0f172a', color: '#e5e7eb', border: '1px solid rgba(148,163,184,0.24)', borderRadius: '7px', padding: '6px 8px', fontSize: '11px' }}>
                <option value="rounded">卡片边框</option>
                <option value="circle">圆形头像感</option>
                <option value="square">证件照方框</option>
              </select>
              <button onClick={() => updateLatexVisual({ showPhoto: !latexVisual.showPhoto })} style={{ background: latexVisual.showPhoto ? 'rgba(20,184,166,0.16)' : 'rgba(255,255,255,0.05)', color: latexVisual.showPhoto ? '#5eead4' : '#cbd5e1', border: '1px solid rgba(148,163,184,0.22)', borderRadius: '7px', padding: '6px 8px', fontSize: '11px', cursor: 'pointer' }}>
                {latexVisual.showPhoto ? '显示照片' : '照片已隐藏'}
              </button>
            </div>
          </div>
          <div style={{ display: 'grid', gap: '8px' }}>
            <label style={{ fontSize: '11px', color: '#94a3b8', display: 'grid', gridTemplateColumns: '58px 1fr 34px', gap: '8px', alignItems: 'center' }}>
              <span>照片</span>
              <input type="range" min="0.72" max="1.35" step="0.03" value={latexVisual.photoScale} onChange={(e) => updateLatexVisual({ photoScale: parseFloat(e.target.value) })} />
              <span>{Math.round(latexVisual.photoScale * 100)}%</span>
            </label>
            <label style={{ fontSize: '11px', color: '#94a3b8', display: 'grid', gridTemplateColumns: '58px 1fr 34px', gap: '8px', alignItems: 'center' }}>
              <span>字号</span>
              <input type="range" min="0.92" max="1.12" step="0.01" value={latexVisual.fontScale} onChange={(e) => updateLatexVisual({ fontScale: parseFloat(e.target.value) })} />
              <span>{Math.round(latexVisual.fontScale * 100)}%</span>
            </label>
          </div>
          <div style={{ display: 'grid', gap: '8px' }}>
            <label style={{ fontSize: '11px', color: '#94a3b8', display: 'grid', gridTemplateColumns: '58px 1fr 34px', gap: '8px', alignItems: 'center' }}>
              <span>间距</span>
              <input type="range" min="0.82" max="1.25" step="0.02" value={latexVisual.spacingScale} onChange={(e) => updateLatexVisual({ spacingScale: parseFloat(e.target.value) })} />
              <span>{Math.round(latexVisual.spacingScale * 100)}%</span>
            </label>
            <label style={{ fontSize: '11px', color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>主题</span>
              <input type="color" value={latexVisual.accentColor} onChange={(e) => updateLatexVisual({ accentColor: e.target.value })} style={{ width: '34px', height: '24px', border: 'none', background: 'transparent', cursor: 'pointer' }} />
              <button onClick={() => updateLatexVisual({ compactMode: !latexVisual.compactMode })} style={{ marginLeft: 'auto', background: latexVisual.compactMode ? 'rgba(59,130,246,0.18)' : 'rgba(255,255,255,0.05)', color: latexVisual.compactMode ? '#93c5fd' : '#cbd5e1', border: '1px solid rgba(148,163,184,0.22)', borderRadius: '7px', padding: '5px 8px', fontSize: '11px', cursor: 'pointer' }}>
                {latexVisual.compactMode ? '紧凑已开' : '紧凑模式'}
              </button>
            </label>
          </div>
        </div>
      )}

      {/* Advanced Layout Customization Toolbar (Only visible for absolute layout spatial templates) */}
      {isSpatial && (
        <div className="print-hide" style={{
          width: '100%', maxWidth: '850px',
          background: 'rgba(23, 23, 23, 0.45)', border: '1px solid rgba(255, 255, 255, 0.05)',
          borderRadius: '8px', padding: '10px 16px', display: 'flex', gap: '15px',
          alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap',
          boxShadow: '0 4px 15px rgba(0,0,0,0.1)'
        }}>
          {/* Spacing Offset Adjuster */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '11px', color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: '3px' }}>
              <Space size={12} /> 板块间距:
            </span>
            <input type="range" min="-30" max="30" step="5" value={spacingOffset}
              onChange={(e) => setSpacingOffset(parseInt(e.target.value))}
              style={{ width: '65px', height: '3px', cursor: 'pointer' }} />
            <span style={{ fontSize: '11px', fontWeight: 700, minWidth: '32px' }}>
              {spacingOffset > 0 ? `+${spacingOffset}` : spacingOffset}px
            </span>
          </div>

          {/* FontSize Offset Adjuster */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '11px', color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: '3px' }}>
              <Type size={12} /> 全局字号:
            </span>
            <input type="range" min="-2.0" max="2.0" step="0.5" value={fontSizeOffset}
              onChange={(e) => setFontSizeOffset(parseFloat(e.target.value))}
              style={{ width: '65px', height: '3px', cursor: 'pointer' }} />
            <span style={{ fontSize: '11px', fontWeight: 700, minWidth: '32px' }}>
              {fontSizeOffset > 0 ? `+${fontSizeOffset}` : fontSizeOffset}pt
            </span>
          </div>

          {/* Global Accent Theme recoloring */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '11px', color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: '3px' }}>
              <Palette size={12} /> 主题换色:
            </span>
            <div style={{ position: 'relative', width: '18px', height: '18px', borderRadius: '50%', background: themeColor || '#3b82f6', border: '1.5px solid #fff', cursor: 'pointer', overflow: 'hidden' }}>
              <input type="color" value={themeColor || '#3b82f6'}
                onChange={(e) => setThemeColor(e.target.value)}
                style={{ position: 'absolute', inset: '-5px', width: '30px', height: '30px', cursor: 'pointer', opacity: 0 }} />
            </div>
            {themeColor && (
              <button onClick={() => setThemeColor('')} style={{ background: 'none', border: 'none', color: '#ef4444', fontSize: '10px', cursor: 'pointer', padding: 0 }}>
                清除
              </button>
            )}
          </div>
        </div>
      )}

      {/* Render final filled DOCX image first; fall back by template type only when image conversion is unavailable. */}
      {previewImageBase64 || previewPdfBase64 || !isSpatial ? (
        <div className="a4-container" style={{
          width: '794px', minHeight: '1123px',
          background: '#fff', borderRadius: '4px',
          overflow: 'hidden', position: 'relative',
          transform: `scale(${canvasScale})`, transformOrigin: 'top center',
          boxShadow: '0 8px 40px rgba(0,0,0,0.3)'
        }}>
          {previewLoading && (
            <div style={{
              position: 'absolute', inset: 0, display: 'flex', alignItems: 'center',
              justifyContent: 'center', background: 'rgba(255,255,255,0.85)', zIndex: 10
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#6b7280' }}>
                <Loader size={20} className="animate-spin" />
                <span>{isLatex ? '正在生成 LaTeX 预览...' : '正在渲染真实 Word 图片预览...'}</span>
              </div>
            </div>
          )}
          {!hasElectronApi && isLatex && previewTexSource && !showLatexEditor && !previewImageBase64 && !previewPdfBase64 && (
            <div style={{
              padding: '26px 28px', minHeight: '1123px', boxSizing: 'border-box',
              background: '#f8fafc', color: '#0f172a'
            }}>
              <div style={{
                border: '1px solid #cbd5e1', borderRadius: '12px', overflow: 'hidden',
                background: '#fff', boxShadow: '0 18px 45px rgba(15,23,42,0.08)'
              }}>
                <div style={{
                  padding: '14px 16px', background: '#0f172a', color: '#e2e8f0',
                  display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'center'
                }}>
                  <div>
                    <div style={{ fontSize: '14px', fontWeight: 850 }}>移动/Web LaTeX 源码预览</div>
                    <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '3px' }}>当前阶段生成可下载 .tex；Android 引擎包可先做 Tectonic 健康检查。</div>
                  </div>
                  <div style={{ display: 'flex', gap: '8px', flexShrink: 0 }}>
                    {canUseNativeTectonic() && (
                      <button onClick={handleCheckNativeTectonic} disabled={nativeTectonicChecking} style={{
                        padding: '7px 10px', borderRadius: '7px', border: '1px solid rgba(255,255,255,0.18)',
                        background: nativeTectonicStatus?.available ? 'rgba(34,197,94,0.22)' : 'rgba(245,158,11,0.18)',
                        color: '#f8fafc', fontSize: '11px', fontWeight: 800, cursor: nativeTectonicChecking ? 'wait' : 'pointer'
                      }}>
                        {nativeTectonicChecking ? '检测中' : '检测 Tectonic'}
                      </button>
                    )}
                    <button onClick={handleExportLatexTex} style={{
                      padding: '7px 10px', borderRadius: '7px', border: '1px solid rgba(255,255,255,0.18)',
                      background: 'rgba(255,255,255,0.08)', color: '#f8fafc', fontSize: '11px', fontWeight: 800
                    }}>
                      下载 .tex
                    </button>
                  </div>
                </div>
                <pre style={{
                  margin: 0, padding: '16px', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                  fontFamily: 'SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                  fontSize: '10.5px', lineHeight: 1.55, color: '#111827', maxHeight: '1010px', overflow: 'auto'
                }}>{previewTexSource}</pre>
              </div>
            </div>
          )}
          {isLatex && showLatexEditor && (
            <div className="print-hide" style={{
              position: 'absolute', inset: '18px', zIndex: 20,
              display: 'flex', flexDirection: 'column', borderRadius: '12px', overflow: 'hidden',
              background: 'rgba(15,23,42,0.96)', border: '1px solid rgba(20,184,166,0.35)',
              boxShadow: '0 24px 80px rgba(0,0,0,0.42)'
            }}>
              <div style={{
                display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'center',
                padding: '12px 14px', borderBottom: '1px solid rgba(148,163,184,0.18)',
                background: 'linear-gradient(135deg, rgba(20,184,166,0.18), rgba(59,130,246,0.10))'
              }}>
                <div>
                  <div style={{ color: '#f8fafc', fontSize: '13px', fontWeight: 850 }}>预览框内 LaTeX 编辑</div>
                  <div style={{ color: '#a7f3d0', fontSize: '11px', marginTop: '3px', lineHeight: 1.45 }}>
                    修改当前预览对应的 .tex 副本；应用后立即重编译并刷新这张 PDF 预览图。
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '8px', flexShrink: 0 }}>
                  {manualLatexPreview && (
                    <button onClick={handleRestoreAutoLatexPreview} disabled={latexEditCompiling} style={{
                      padding: '7px 10px', borderRadius: '6px', border: '1px solid rgba(148,163,184,0.25)',
                      background: 'rgba(255,255,255,0.06)', color: '#cbd5e1', cursor: latexEditCompiling ? 'wait' : 'pointer', fontSize: '11px', fontWeight: 700
                    }}>
                      恢复自动预览
                    </button>
                  )}
                  <button onClick={() => setShowLatexSourceMode(!showLatexSourceMode)} disabled={latexEditCompiling} style={{
                    padding: '7px 10px', borderRadius: '6px', border: '1px solid rgba(148,163,184,0.25)',
                    background: showLatexSourceMode ? 'rgba(99,102,241,0.24)' : 'rgba(255,255,255,0.06)', color: showLatexSourceMode ? '#c4b5fd' : '#cbd5e1', cursor: latexEditCompiling ? 'wait' : 'pointer', fontSize: '11px', fontWeight: 700
                  }}>
                    {showLatexSourceMode ? '可视快改' : '源码高级'}
                  </button>
                  <button onClick={() => setShowLatexEditor(false)} disabled={latexEditCompiling} style={{
                    padding: '7px 10px', borderRadius: '6px', border: '1px solid rgba(148,163,184,0.25)',
                    background: 'rgba(255,255,255,0.06)', color: '#cbd5e1', cursor: latexEditCompiling ? 'wait' : 'pointer', fontSize: '11px', fontWeight: 700
                  }}>
                    收起
                  </button>
                  {showLatexSourceMode && <button onClick={handleApplyLatexSourcePreview} disabled={latexEditCompiling || !latexDraftSource.trim()} style={{
                    padding: '7px 12px', borderRadius: '6px', border: 'none',
                    background: latexEditCompiling ? 'rgba(20,184,166,0.35)' : 'linear-gradient(135deg, #14b8a6, #0f766e)',
                    color: '#fff', cursor: latexEditCompiling ? 'wait' : 'pointer', fontSize: '11px', fontWeight: 800,
                    display: 'flex', alignItems: 'center', gap: '6px'
                  }}>
                    {latexEditCompiling && <Loader size={12} className="animate-spin" />}
                    应用并刷新预览
                  </button>}
                </div>
              </div>
              {showLatexSourceMode ? (
                <textarea
                  value={latexDraftSource}
                  onChange={(event) => setLatexDraftSource(event.target.value)}
                  spellCheck={false}
                  placeholder="等待当前 LaTeX 模板生成源码后即可编辑..."
                  style={{
                    flex: 1, width: '100%', resize: 'none', boxSizing: 'border-box',
                    background: 'rgba(2,6,23,0.98)', color: '#dbeafe', border: 'none',
                    padding: '14px 16px', fontFamily: 'SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                    fontSize: '11px', lineHeight: 1.58, outline: 'none'
                  }}
                />
              ) : (
                <div style={{
                  flex: 1, padding: '16px', display: 'grid', gridTemplateRows: 'auto auto 1fr', gap: '12px',
                  background: 'linear-gradient(180deg, rgba(2,6,23,0.96), rgba(15,23,42,0.98))', overflow: 'auto'
                }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <label style={{ display: 'grid', gap: '6px', color: '#cbd5e1', fontSize: '11px', fontWeight: 800 }}>
                      姓名
                      <input value={resumeData?.basicInfo?.name || ''} onChange={(e) => updateBasicFromPreview('name', e.target.value)} style={{ background: '#020617', color: '#f8fafc', border: '1px solid rgba(148,163,184,0.22)', borderRadius: '8px', padding: '10px 11px', outline: 'none' }} />
                    </label>
                    <label style={{ display: 'grid', gap: '6px', color: '#cbd5e1', fontSize: '11px', fontWeight: 800 }}>
                      求职意向
                      <input value={resumeData?.basicInfo?.title || ''} onChange={(e) => updateBasicFromPreview('title', e.target.value)} style={{ background: '#020617', color: '#f8fafc', border: '1px solid rgba(148,163,184,0.22)', borderRadius: '8px', padding: '10px 11px', outline: 'none' }} />
                    </label>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <label style={{ display: 'grid', gap: '6px', color: '#cbd5e1', fontSize: '11px', fontWeight: 800 }}>
                      电话
                      <input value={resumeData?.basicInfo?.phone || ''} onChange={(e) => updateBasicFromPreview('phone', e.target.value)} style={{ background: '#020617', color: '#f8fafc', border: '1px solid rgba(148,163,184,0.22)', borderRadius: '8px', padding: '10px 11px', outline: 'none' }} />
                    </label>
                    <label style={{ display: 'grid', gap: '6px', color: '#cbd5e1', fontSize: '11px', fontWeight: 800 }}>
                      邮箱
                      <input value={resumeData?.basicInfo?.email || ''} onChange={(e) => updateBasicFromPreview('email', e.target.value)} style={{ background: '#020617', color: '#f8fafc', border: '1px solid rgba(148,163,184,0.22)', borderRadius: '8px', padding: '10px 11px', outline: 'none' }} />
                    </label>
                  </div>
                  <div style={{
                    border: '1px solid rgba(20,184,166,0.20)', borderRadius: '12px', padding: '12px',
                    background: 'rgba(15,23,42,0.78)', display: 'grid', gap: '12px'
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px' }}>
                      <div>
                        <div style={{ color: '#5eead4', fontSize: '11px', fontWeight: 900 }}>版式调节</div>
                        <div style={{ color: '#94a3b8', fontSize: '10px', marginTop: '2px' }}>这些控件会同步到 LaTeX 模板参数并重编译预览。</div>
                      </div>
                      <button onClick={handleAILatexAdjust} disabled={aiLatexAdjusting} style={{ background: aiLatexAdjusting ? 'rgba(99,102,241,0.18)' : 'rgba(139,92,246,0.20)', color: '#ddd6fe', border: '1px solid rgba(139,92,246,0.32)', borderRadius: '7px', padding: '6px 8px', fontSize: '11px', cursor: aiLatexAdjusting ? 'wait' : 'pointer' }}>
                        {aiLatexAdjusting ? '调版中' : 'AI 调版'}
                      </button>
                      <button onClick={() => updateLatexVisual({ accentColor: '#2563EB', fontScale: 1, spacingScale: 1, photoScale: 1, photoPosition: 'right', photoShape: 'rounded', showPhoto: true, compactMode: false })} style={{ background: 'rgba(255,255,255,0.06)', color: '#cbd5e1', border: '1px solid rgba(148,163,184,0.22)', borderRadius: '7px', padding: '6px 8px', fontSize: '11px', cursor: 'pointer' }}>
                        重置
                      </button>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px' }}>
                      <label style={{ display: 'grid', gap: '6px', color: '#cbd5e1', fontSize: '11px', fontWeight: 800 }}>
                        照片位置
                        <select value={latexVisual.photoPosition} onChange={(e) => updateLatexVisual({ photoPosition: e.target.value })} style={{ background: '#020617', color: '#f8fafc', border: '1px solid rgba(148,163,184,0.22)', borderRadius: '8px', padding: '9px 10px', outline: 'none' }}>
                          <option value="right">右上</option>
                          <option value="left">左上</option>
                          <option value="top">居中</option>
                          <option value="none">隐藏</option>
                        </select>
                      </label>
                      <label style={{ display: 'grid', gap: '6px', color: '#cbd5e1', fontSize: '11px', fontWeight: 800 }}>
                        照片样式
                        <select value={latexVisual.photoShape} onChange={(e) => updateLatexVisual({ photoShape: e.target.value })} style={{ background: '#020617', color: '#f8fafc', border: '1px solid rgba(148,163,184,0.22)', borderRadius: '8px', padding: '9px 10px', outline: 'none' }}>
                          <option value="rounded">卡片边框</option>
                          <option value="circle">圆形头像感</option>
                          <option value="square">证件照方框</option>
                        </select>
                      </label>
                      <label style={{ display: 'grid', gap: '6px', color: '#cbd5e1', fontSize: '11px', fontWeight: 800 }}>
                        主题色
                        <input type="color" value={latexVisual.accentColor} onChange={(e) => updateLatexVisual({ accentColor: e.target.value })} style={{ width: '100%', height: '38px', border: '1px solid rgba(148,163,184,0.22)', borderRadius: '8px', background: '#020617', cursor: 'pointer' }} />
                      </label>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px' }}>
                      <label style={{ display: 'grid', gap: '6px', color: '#94a3b8', fontSize: '11px' }}>
                        <span>照片 {Math.round(latexVisual.photoScale * 100)}%</span>
                        <input type="range" min="0.72" max="1.35" step="0.03" value={latexVisual.photoScale} onChange={(e) => updateLatexVisual({ photoScale: parseFloat(e.target.value) })} />
                      </label>
                      <label style={{ display: 'grid', gap: '6px', color: '#94a3b8', fontSize: '11px' }}>
                        <span>字号 {Math.round(latexVisual.fontScale * 100)}%</span>
                        <input type="range" min="0.92" max="1.12" step="0.01" value={latexVisual.fontScale} onChange={(e) => updateLatexVisual({ fontScale: parseFloat(e.target.value) })} />
                      </label>
                      <label style={{ display: 'grid', gap: '6px', color: '#94a3b8', fontSize: '11px' }}>
                        <span>间距 {Math.round(latexVisual.spacingScale * 100)}%</span>
                        <input type="range" min="0.82" max="1.25" step="0.02" value={latexVisual.spacingScale} onChange={(e) => updateLatexVisual({ spacingScale: parseFloat(e.target.value) })} />
                      </label>
                    </div>
                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                      <button onClick={() => updateLatexVisual({ showPhoto: !latexVisual.showPhoto })} style={{ background: latexVisual.showPhoto ? 'rgba(20,184,166,0.16)' : 'rgba(255,255,255,0.05)', color: latexVisual.showPhoto ? '#5eead4' : '#cbd5e1', border: '1px solid rgba(148,163,184,0.22)', borderRadius: '7px', padding: '7px 10px', fontSize: '11px', cursor: 'pointer' }}>
                        {latexVisual.showPhoto ? '显示照片' : '照片已隐藏'}
                      </button>
                      <button onClick={() => updateLatexVisual({ compactMode: !latexVisual.compactMode })} style={{ background: latexVisual.compactMode ? 'rgba(59,130,246,0.18)' : 'rgba(255,255,255,0.05)', color: latexVisual.compactMode ? '#93c5fd' : '#cbd5e1', border: '1px solid rgba(148,163,184,0.22)', borderRadius: '7px', padding: '7px 10px', fontSize: '11px', cursor: 'pointer' }}>
                        {latexVisual.compactMode ? '紧凑已开' : '紧凑模式'}
                      </button>
                    </div>
                  </div>
                  <label style={{ display: 'grid', gridTemplateRows: 'auto 1fr', gap: '6px', color: '#cbd5e1', fontSize: '11px', fontWeight: 800 }}>
                    个人总结
                    <textarea value={resumeData?.basicInfo?.summary || ''} onChange={(e) => updateBasicFromPreview('summary', e.target.value)} style={{ minHeight: '180px', resize: 'vertical', background: '#020617', color: '#f8fafc', border: '1px solid rgba(148,163,184,0.22)', borderRadius: '8px', padding: '11px', outline: 'none', lineHeight: 1.6 }} />
                  </label>
                </div>
              )}
              <div style={{
                padding: '8px 14px', borderTop: '1px solid rgba(148,163,184,0.16)',
                color: manualLatexPreview ? '#5eead4' : '#94a3b8', fontSize: '11px', lineHeight: 1.45,
                background: 'rgba(15,23,42,0.92)'
              }}>
                {manualLatexPreview
                  ? '当前为手动 LaTeX 源码模式；左侧表单不会覆盖这次源码修改，除非恢复自动预览。'
                  : '可视快改会写回结构化简历数据，并自动重新生成 LaTeX 源码与 PDF 预览；源码高级模式适合精修命令。'}
              </div>
            </div>
          )}
          {previewImageBase64 ? (
            <div
              ref={docxContainerRef}
              className="preview-docx-container preview-image-container"
              style={{ padding: '0', width: '100%', minHeight: '1123px', display: 'flex', justifyContent: 'center', alignItems: 'flex-start' }}
            >
              <img
                src={`data:image/png;base64,${previewImageBase64}`}
                alt="简历预览"
                style={{ width: '100%', height: 'auto', display: 'block', background: '#fff' }}
              />
            </div>
          ) : previewPdfBase64 ? (
            <iframe
              title="LaTeX PDF 预览"
              src={`data:application/pdf;base64,${previewPdfBase64}`}
              style={{ width: '100%', minHeight: '1123px', border: 'none', background: '#fff' }}
            />
          ) : previewDocxBase64 ? (
            <div
              ref={docxContainerRef}
              className="preview-docx-container"
              style={{ padding: '0', width: '100%', minHeight: '1123px' }}
            />
          ) : !hasElectronApi && isLatex && previewTexSource ? null : (
            <div style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              justifyContent: 'center', height: '1123px', color: '#9ca3af', gap: '10px'
            }}>
              <FileText size={32} />
              <div style={{ fontSize: '14px' }}>{isLatex ? 'LaTeX PDF 预览暂未生成' : '请先在左侧编辑简历数据，右侧选择模板'}</div>
              <div style={{ fontSize: '12px', maxWidth: '520px', textAlign: 'center', lineHeight: 1.6 }}>
                {isLatex
                  ? (previewMessage || (hasElectronApi ? '正在编译 LaTeX 并生成 PDF 图片预览；如果失败，请检查编译器或点击“导出 .tex”查看源码。' : '移动/Web 版本将生成 .tex 源码预览。'))
                  : '选中模板后将自动生成预览'}
              </div>
            </div>
          )}
        </div>
      ) : previewLoading ? (
        <div className="a4-container" style={{
          width: '794px', minHeight: '1123px',
          background: '#fff', borderRadius: '4px',
          overflow: 'hidden', position: 'relative',
          transform: `scale(${canvasScale})`, transformOrigin: 'top center',
          boxShadow: '0 8px 40px rgba(0,0,0,0.3)',
          display: 'flex', alignItems: 'center', justifyContent: 'center'
        }}>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px', color: '#6b7280' }}>
            <Loader size={28} className="animate-spin" />
            <div style={{ fontSize: '15px', fontWeight: 700 }}>正在生成真实 Word 图片预览...</div>
            <div style={{ fontSize: '12px' }}>空间模板不再先显示编辑画布，避免误把兜底画布当成最终效果。</div>
          </div>
        </div>
      ) : (
        <div style={{ position: 'relative' }}>
          <div className="print-hide" style={{
            maxWidth: '760px', margin: '0 auto 10px', padding: '8px 12px', borderRadius: '8px',
            background: 'rgba(245,158,11,0.10)', border: '1px solid rgba(245,158,11,0.22)',
            color: '#fbbf24', fontSize: '12px', lineHeight: 1.5
          }}>
            真实 Word 图片预览暂不可用，当前显示空间编辑兜底画布，仅用于手动微调；最终效果请以导出的 DOCX 为准。
          </div>
          <InteractiveCanvas
            templatePath={selectedTemplate?.path}
            resumeData={resumeData}
            setResumeData={setResumeData}
            onNotification={onNotification}
            canvasScale={canvasScale}
            layoutAdjustments={layoutAdjustments}
            setLayoutAdjustments={setLayoutAdjustments}
            isDesensitized={isDesensitized}
            themeColor={themeColor}
            fontSizeOffset={fontSizeOffset}
            spacingOffset={spacingOffset}
          />
        </div>
      )}

      {/* AI Polish floating popup menu for flow layout templates */}
      {polishState && (
        <div style={{
          position: 'absolute',
          left: `${Math.max(10, Math.min(585 - 280, polishState.x - 140))}px`,
          top: `${Math.max(10, polishState.y)}px`,
          zIndex: 9999,
          background: 'rgba(23, 23, 23, 0.95)',
          border: '1px solid rgba(255,255,255,0.15)',
          borderRadius: '8px',
          padding: '6px 12px',
          display: 'flex',
          alignItems: 'center',
          boxShadow: '0 8px 30px rgba(0,0,0,0.5)',
          backdropFilter: 'blur(10px)',
          gap: '8px',
          animation: 'slideUpShort 0.2s cubic-bezier(0.16,1,0.3,1) forwards'
        }}>
          <span style={{ fontSize: '10px', color: '#9ca3af', fontWeight: 600 }}>AI 智能改写:</span>
          <button
            onClick={() => handleAIPolish('professional')}
            disabled={polishing}
            style={{
              background: 'none', border: 'none', color: '#60a5fa', fontSize: '10.5px',
              fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center',
              gap: '2px', padding: '3px 6px', borderRadius: '4px'
            }}
            className="hover-action-btn"
          >
            专业
          </button>
          <button
            onClick={() => handleAIPolish('star')}
            disabled={polishing}
            style={{
              background: 'none', border: 'none', color: '#34d399', fontSize: '10.5px',
              fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center',
              gap: '2px', padding: '3px 6px', borderRadius: '4px'
            }}
            className="hover-action-btn"
          >
            <Sparkles size={11} className={polishing ? "animate-spin" : ""} /> STAR
          </button>
          <button
            onClick={() => handleAIPolish('shorten')}
            disabled={polishing}
            style={{
              background: 'none', border: 'none', color: '#fbbf24', fontSize: '10.5px',
              fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center',
              gap: '2px', padding: '3px 6px', borderRadius: '4px'
            }}
            className="hover-action-btn"
          >
            精简
          </button>
          <div style={{ width: '1px', height: '12px', background: 'rgba(255,255,255,0.15)' }} />
          <button
            onClick={() => setPolishState(null)}
            style={{
              background: 'none', border: 'none', color: '#9ca3af', fontSize: '10px',
              cursor: 'pointer', padding: '3px 6px'
            }}
          >
            取消
          </button>
        </div>
      )}

      {/* Snapshot Controller Modal Popover */}
      {showSnapshotModal && (
        <SnapshotModal
          onClose={() => setShowSnapshotModal(false)}
          templateName={selectedTemplate?.name}
          resumeData={resumeData}
          layoutAdjustments={layoutAdjustments}
          onApplySnapshot={handleApplySnapshot}
          onNotification={onNotification}
        />
      )}

      <style>{`
        /* docx-preview styling alignments */
        .preview-docx-container {
          background: #ffffff;
          overflow-y: auto;
          color: #1f2937;
        }
        .preview-docx-container .docx-wrapper {
          padding: 0 !important;
          background: transparent !important;
          box-shadow: none !important;
        }
        .preview-docx-container .docx {
          margin: 0 auto !important;
          box-shadow: none !important;
          border: none !important;
          width: 100% !important;
          padding: 40px !important;
          box-sizing: border-box !important;
        }
        .animate-spin {
          animation: spin 1s linear infinite;
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        @keyframes slideUpShort {
          from { transform: translateY(4px); opacity: 0; }
          to { transform: translateY(0); opacity: 1; }
        }
        .hover-action-btn:hover {
          background: rgba(255,255,255,0.06) !important;
        }
      `}</style>
    </div>
  );
}
