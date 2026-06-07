const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  getTemplateList: () => ipcRenderer.invoke('get-template-list'),
  checkTemplateConfig: (templatePath) => ipcRenderer.invoke('check-template-config', { templatePath }),
  parseTemplateLayout: (templatePath) => ipcRenderer.invoke('parse-template-layout', { templatePath }),
  selectTemplateDir: () => ipcRenderer.invoke('select-template-dir'),
  renderPreview: (templateName, resumeData, layoutAdjustments) => ipcRenderer.invoke('render-preview', { templateName, resumeData, layoutAdjustments }),

  getApiConfig: () => ipcRenderer.invoke('get-api-config'),
  saveApiConfig: (cfg) => ipcRenderer.invoke('save-api-config', cfg),

  printToPdf: (fileName, htmlContent) => ipcRenderer.send('print-to-pdf', { defaultFileName: fileName, htmlContent }),
  onPdfSaved: (callback) => { const h = (e, ...a) => callback(...a); ipcRenderer.on('pdf-saved', h); return () => ipcRenderer.removeListener('pdf-saved', h); },
  onPdfFailed: (callback) => { const h = (e, ...a) => callback(...a); ipcRenderer.on('pdf-failed', h); return () => ipcRenderer.removeListener('pdf-failed', h); },

  exportToWord: (templateName, resumeData, layoutAdjustments) => ipcRenderer.send('export-to-word', { templateName, resumeData, layoutAdjustments }),
  onWordSaved: (callback) => { const h = (e, ...a) => callback(...a); ipcRenderer.on('word-saved', h); return () => ipcRenderer.removeListener('word-saved', h); },
  onWordFailed: (callback) => { const h = (e, ...a) => callback(...a); ipcRenderer.on('word-failed', h); return () => ipcRenderer.removeListener('word-failed', h); },

  getLatexCompilerStatus: () => ipcRenderer.invoke('get-latex-compiler-status'),
  renderLatexSourcePreview: (source, name, resumeData) => ipcRenderer.invoke('render-latex-source-preview', { source, name, resumeData }),
  exportLatexTex: (templateName, resumeData) => ipcRenderer.send('export-latex-tex', { templateName, resumeData }),
  onLatexTexSaved: (callback) => { const h = (e, ...a) => callback(...a); ipcRenderer.on('latex-tex-saved', h); return () => ipcRenderer.removeListener('latex-tex-saved', h); },
  onLatexTexFailed: (callback) => { const h = (e, ...a) => callback(...a); ipcRenderer.on('latex-tex-failed', h); return () => ipcRenderer.removeListener('latex-tex-failed', h); },
  exportLatexPdf: (templateName, resumeData) => ipcRenderer.send('export-latex-pdf', { templateName, resumeData }),
  onLatexPdfSaved: (callback) => { const h = (e, ...a) => callback(...a); ipcRenderer.on('latex-pdf-saved', h); return () => ipcRenderer.removeListener('latex-pdf-saved', h); },
  onLatexPdfFailed: (callback) => { const h = (e, ...a) => callback(...a); ipcRenderer.on('latex-pdf-failed', h); return () => ipcRenderer.removeListener('latex-pdf-failed', h); },

  checkForUpdates: () => ipcRenderer.send('check-for-updates'),
  onUpdateAvailable: (callback) => { const h = (e, info) => callback(info); ipcRenderer.on('update-available', h); return () => ipcRenderer.removeListener('update-available', h); },
  onUpdateNotAvailable: (callback) => { const h = () => callback(); ipcRenderer.on('update-not-available', h); return () => ipcRenderer.removeListener('update-not-available', h); },
  onUpdateError: (callback) => { const h = (e, msg) => callback(msg); ipcRenderer.on('update-error', h); return () => ipcRenderer.removeListener('update-error', h); },
  onDownloadProgress: (callback) => { const h = (e, p) => callback(p); ipcRenderer.on('download-progress', h); return () => ipcRenderer.removeListener('download-progress', h); },
  onUpdateDownloaded: (callback) => { const h = (e, info) => callback(info); ipcRenderer.on('update-downloaded', h); return () => ipcRenderer.removeListener('update-downloaded', h); },
  restartAndUpdate: () => ipcRenderer.send('restart-and-update')
});
