const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const { execSync, exec, execFile } = require('child_process');
const { autoUpdater } = require('electron-updater');
const mammoth = require('mammoth');

const RESUME_USER_DATA_SUFFIX = (process.env.RESUME_USER_DATA_SUFFIX || 'latex-resume-studio').replace(/[^A-Za-z0-9_.-]+/g, '-');
if (RESUME_USER_DATA_SUFFIX) {
  const currentUserData = app.getPath('userData');
  app.setPath('userData', `${currentUserData}-${RESUME_USER_DATA_SUFFIX}`);
}
try { fs.mkdirSync(app.getPath('userData'), { recursive: true }); } catch (e) {}
const RESUME_DEV_PORT = Number(process.env.RESUME_DEV_PORT || 3101);
const CONFIG_PATH = path.join(app.getPath('userData'), 'config.json');
console.log('[LaTeX Resume Studio] userData:', app.getPath('userData'));
console.log('[LaTeX Resume Studio] devPort:', RESUME_DEV_PORT);
const LATEX_TEMPLATES_DIR = process.env.LATEX_TEMPLATES_DIR
  ? path.resolve(process.env.LATEX_TEMPLATES_DIR)
  : (app.isPackaged ? path.join(process.resourcesPath, 'latex_templates') : path.join(__dirname, 'latex_templates'));
const FILLER_SCRIPT = app.isPackaged
  ? path.join(process.resourcesPath, 'utils', 'docx_filler_v2.py')
  : path.join(__dirname, 'src/utils/docx_filler_v2.py');
const ENGINE_SCRIPT = app.isPackaged
  ? path.join(process.resourcesPath, 'utils', 'template_engine.py')
  : path.join(__dirname, 'src/utils/template_engine.py');
const PHOTO_SCRIPT = app.isPackaged
  ? path.join(process.resourcesPath, 'utils', 'photo_replace.py')
  : path.join(__dirname, 'src/utils/photo_replace.py');
const LATEX_RENDERER_SCRIPT = app.isPackaged
  ? path.join(process.resourcesPath, 'utils', 'latex_renderer.py')
  : path.join(__dirname, 'src/utils/latex_renderer.py');
const WINDOW_ICON = app.isPackaged
  ? path.join(__dirname, 'dist', 'app-icon.png')
  : path.join(__dirname, 'public', 'app-icon.png');

function loadConfig() {
  try { return JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf-8')); } catch (e) { return {}; }
}
function saveConfig(cfg) {
  try { fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2), 'utf-8'); } catch (e) {}
}

let mainWindow = null;

function scanLatexTemplates() {
  try {
    if (!LATEX_TEMPLATES_DIR || !fs.existsSync(LATEX_TEMPLATES_DIR)) return [];
    return fs.readdirSync(LATEX_TEMPLATES_DIR, { withFileTypes: true })
      .filter(entry => entry.isDirectory() && !entry.name.startsWith('_') && !entry.name.startsWith('.'))
      .map(entry => {
        const templateDir = path.join(LATEX_TEMPLATES_DIR, entry.name);
        const metaPath = path.join(templateDir, 'meta.json');
        const texPath = path.join(templateDir, 'template.tex.j2');
        if (!fs.existsSync(metaPath) || !fs.existsSync(texPath)) return null;
        const meta = JSON.parse(fs.readFileSync(metaPath, 'utf-8'));
        const id = meta.id || entry.name;
        return {
          ...meta,
          id,
          name: id,
          displayName: meta.displayName || meta.name || id,
          path: templateDir,
          metaPath,
          templatePath: texPath,
          kind: 'latex',
          engineType: 'latex',
          group: meta.group || 'LaTeX 模板'
        };
      })
      .filter(Boolean)
      .sort((a, b) => (a.displayName || a.name).localeCompare(b.displayName || b.name, 'zh-Hans-CN'));
  } catch (e) {
    console.error('Scan LaTeX templates error:', e);
    return [];
  }
}

function scanTemplates() {
  return scanLatexTemplates();
}

function findTemplateByName(templateName) {
  return scanTemplates().find(t => t.name === templateName || t.id === templateName || t.path === templateName);
}

function fillDocx(templatePath, resumeData, outputPath, layoutAdjustments) {
  const tempJson = path.join(app.getPath('temp'), `resume_${Date.now()}.json`);
  fs.writeFileSync(tempJson, JSON.stringify(resumeData, null, 2), 'utf-8');

  let tempLayoutJson = null;
  let layoutArg = '';
  if (layoutAdjustments && Object.keys(layoutAdjustments).length > 0) {
    tempLayoutJson = path.join(app.getPath('temp'), `layout_${Date.now()}.json`);
    fs.writeFileSync(tempLayoutJson, JSON.stringify(layoutAdjustments, null, 2), 'utf-8');
    layoutArg = ` "${tempLayoutJson}"`;
  }

  try {
    // Use template_engine.py with fill_with_fallback (YAML → engine, else → v2)
    execSync(
      `python3 "${ENGINE_SCRIPT}" "${tempJson}" "${templatePath}" "${outputPath}"${layoutArg}`,
      { encoding: 'utf-8', timeout: 30000 }
    );
    if (!fs.existsSync(outputPath)) {
      console.error('Fill docx: output file not created');
      return false;
    }
    return true;
  } catch (err) {
    console.error('Fill docx error:', err.message);
    // Fallback to v2 if engine fails
    try {
      execSync(
        `python3 "${FILLER_SCRIPT}" "${tempJson}" "${templatePath}" "${outputPath}"`,
        { encoding: 'utf-8', timeout: 30000 }
      );
      const ok = fs.existsSync(outputPath);
      if (ok) applyPhotoReplacementSync(outputPath, tempJson, resumeData);
      return ok;
    } catch (err2) {
      console.error('V2 fallback error:', err2.message);
      return false;
    }
  } finally {
    try { fs.unlinkSync(tempJson); } catch (e) {}
    if (tempLayoutJson) {
      try { fs.unlinkSync(tempLayoutJson); } catch (e) {}
    }
  }
}

function makeTempPath(prefix, suffix) {
  return path.join(app.getPath('temp'), `${prefix}_${process.pid}_${Date.now()}_${Math.random().toString(36).slice(2)}${suffix}`);
}

function execFileAsync(file, args, options = {}) {
  return new Promise((resolve, reject) => {
    execFile(file, args, { encoding: 'utf-8', timeout: 30000, maxBuffer: 2 * 1024 * 1024, ...options }, (error, stdout, stderr) => {
      if (error) {
        error.stdout = stdout;
        error.stderr = stderr;
        reject(error);
        return;
      }
      resolve({ stdout, stderr });
    });
  });
}

function parseJsonPayload(text) {
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch (e) {
    return null;
  }
}

async function runLatexRenderer(args, options = {}) {
  const rendererEnv = {
    ...process.env,
    LATEX_TEMPLATES_DIR
  };
  const runOptions = {
    timeout: options.timeout || 90000,
    maxBuffer: options.maxBuffer || 8 * 1024 * 1024,
    env: rendererEnv
  };

  try {
    const { stdout, stderr } = await execFileAsync('python3', [LATEX_RENDERER_SCRIPT, ...args], runOptions);
    const payload = parseJsonPayload(stdout) || { success: false, error: 'LaTeX renderer stdout is not JSON', stdout };
    if (stderr) payload.stderr = stderr;
    return payload;
  } catch (err) {
    const payload = parseJsonPayload(err.stdout) || { success: false };
    return {
      ...payload,
      success: false,
      error: payload.error || err.message || 'LaTeX renderer failed',
      stderr: payload.stderr || err.stderr || '',
      stdout: payload.stdout || err.stdout || ''
    };
  }
}

async function getLatexCompilerStatus() {
  const result = await runLatexRenderer(['status'], { timeout: 15000 });
  if (result.success === false && !result.compiler) {
    return {
      success: false,
      compiler: { available: false, message: result.error || '无法检测 LaTeX 编译器' },
      error: result.error || '无法检测 LaTeX 编译器'
    };
  }
  return result;
}

async function renderLatexTemplate(template, resumeData, { noCompile = false, layoutAdjustments = null } = {}) {
  const tempJson = makeTempPath('latex_resume', '.json');
  const outputDir = makeTempPath(noCompile ? 'latex_tex' : 'latex_pdf', '');
  fs.mkdirSync(outputDir, { recursive: true });
  const dataForLatex = {
    ...(resumeData || {}),
    __visual: layoutAdjustments && typeof layoutAdjustments === 'object' ? layoutAdjustments : {}
  };
  fs.writeFileSync(tempJson, JSON.stringify(dataForLatex, null, 2), 'utf-8');

  try {
    const args = ['render', tempJson, template.id || template.name, outputDir];
    if (noCompile) args.push('--no-compile');
    return await runLatexRenderer(args, { timeout: noCompile ? 45000 : 120000 });
  } finally {
    try { fs.unlinkSync(tempJson); } catch (e) {}
  }
}

async function renderLatexSource(source, { name = 'edited-latex-preview', resumeData = null } = {}) {
  const sourcePath = makeTempPath('latex_source_edit', '.tex');
  const outputDir = makeTempPath('latex_source_pdf', '');
  const dataPath = resumeData ? makeTempPath('latex_source_data', '.json') : null;
  fs.mkdirSync(outputDir, { recursive: true });
  fs.writeFileSync(sourcePath, String(source || ''), 'utf-8');
  if (dataPath) fs.writeFileSync(dataPath, JSON.stringify(resumeData), 'utf-8');

  try {
    const args = ['render-source', sourcePath, outputDir, '--name', name];
    if (dataPath) args.push('--data-json', dataPath);
    return await runLatexRenderer(args, { timeout: 120000 });
  } finally {
    try { fs.unlinkSync(sourcePath); } catch (e) {}
    if (dataPath) { try { fs.unlinkSync(dataPath); } catch (e) {} }
  }
}

function cleanupLatexOutput(result) {
  const candidates = [result?.texPath, result?.pdfPath].filter(Boolean).map(file => path.dirname(file));
  for (const dir of new Set(candidates)) {
    if (dir && dir.startsWith(app.getPath('temp'))) {
      try { fs.rmSync(dir, { recursive: true, force: true }); } catch (e) {}
    }
  }
}

function readLatexTexSource(result) {
  if (!result?.texPath || !fs.existsSync(result.texPath)) return '';
  try {
    const source = fs.readFileSync(result.texPath, 'utf-8');
    // Keep IPC payload bounded while still showing the complete useful preview.
    return source.length > 80000 ? `${source.slice(0, 80000)}\n\n% ... preview truncated ...` : source;
  } catch (err) {
    console.error('Read LaTeX source preview error:', err.message);
    return '';
  }
}

function safeExportStem(value) {
  return String(value || '我的').replace(/[\\/:*?"<>|]+/g, '_').trim() || '我的';
}

function shouldApplyPhotoReplacement(resumeData) {
  return Boolean(resumeData?.basicInfo?.photo && fs.existsSync(PHOTO_SCRIPT));
}

function applyPhotoReplacementSync(outputPath, tempJsonPath, resumeData) {
  if (!shouldApplyPhotoReplacement(resumeData) || !fs.existsSync(outputPath)) return;
  try {
    execSync(`python3 "${PHOTO_SCRIPT}" "${tempJsonPath}" "${outputPath}"`, { encoding: 'utf-8', timeout: 30000 });
  } catch (err) {
    console.error('Photo replacement fallback error:', err.message);
  }
}

async function applyPhotoReplacementAsync(outputPath, tempJsonPath, resumeData) {
  if (!shouldApplyPhotoReplacement(resumeData) || !fs.existsSync(outputPath)) return;
  try {
    await execFileAsync('python3', [PHOTO_SCRIPT, tempJsonPath, outputPath], { timeout: 30000 });
  } catch (err) {
    console.error('Photo replacement async fallback error:', err.message);
  }
}

async function fillDocxAsync(templatePath, resumeData, outputPath, layoutAdjustments) {
  const tempJson = makeTempPath('resume', '.json');
  fs.writeFileSync(tempJson, JSON.stringify(resumeData, null, 2), 'utf-8');

  let tempLayoutJson = null;
  const engineArgs = [ENGINE_SCRIPT, tempJson, templatePath, outputPath];
  if (layoutAdjustments && Object.keys(layoutAdjustments).length > 0) {
    tempLayoutJson = makeTempPath('layout', '.json');
    fs.writeFileSync(tempLayoutJson, JSON.stringify(layoutAdjustments, null, 2), 'utf-8');
    engineArgs.push(tempLayoutJson);
  }

  try {
    await execFileAsync('python3', engineArgs);
    if (fs.existsSync(outputPath)) return true;
    console.error('Fill docx async: output file not created');
    return false;
  } catch (err) {
    console.error('Fill docx async error:', err.message);
    try {
      await execFileAsync('python3', [FILLER_SCRIPT, tempJson, templatePath, outputPath]);
      const ok = fs.existsSync(outputPath);
      if (ok) await applyPhotoReplacementAsync(outputPath, tempJson, resumeData);
      return ok;
    } catch (err2) {
      console.error('V2 async fallback error:', err2.message);
      return false;
    }
  } finally {
    try { fs.unlinkSync(tempJson); } catch (e) {}
    if (tempLayoutJson) {
      try { fs.unlinkSync(tempLayoutJson); } catch (e) {}
    }
  }
}

function findLibreOfficeExecutable() {
  const candidates = [
    '/Applications/LibreOffice.app/Contents/MacOS/soffice',
    '/Applications/OpenOffice.app/Contents/MacOS/soffice',
    '/opt/homebrew/bin/soffice',
    '/usr/local/bin/soffice',
    '/usr/bin/soffice'
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  try {
    const found = execSync('command -v soffice', { encoding: 'utf-8', timeout: 2000 }).trim();
    if (found && fs.existsSync(found)) return found;
  } catch (e) {}
  return null;
}

async function renderFileQuickLookPreview(filePath, size = '1600') {
  if (process.platform !== 'darwin') return null;

  const outDir = makeTempPath('ql_preview', '');
  fs.mkdirSync(outDir, { recursive: true });
  try {
    await execFileAsync('/usr/bin/qlmanage', ['-t', '-s', String(size), '-o', outDir, filePath], { timeout: 25000 });
    const expected = path.join(outDir, path.basename(filePath) + '.png');
    let pngPath = fs.existsSync(expected) ? expected : null;
    if (!pngPath) {
      const generated = fs.readdirSync(outDir).find(f => f.toLowerCase().endsWith('.png'));
      if (generated) pngPath = path.join(outDir, generated);
    }
    if (!pngPath || !fs.existsSync(pngPath)) return null;
    const buffer = fs.readFileSync(pngPath);
    return buffer.toString('base64');
  } catch (err) {
    console.error('QuickLook preview error:', err.message);
    return null;
  } finally {
    try { fs.rmSync(outDir, { recursive: true, force: true }); } catch (e) {}
  }
}

async function renderDocxLibreOfficePreview(docxPath) {
  const soffice = findLibreOfficeExecutable();
  if (!soffice) return null;

  const outDir = makeTempPath('lo_preview', '');
  fs.mkdirSync(outDir, { recursive: true });
  try {
    await execFileAsync(soffice, [
      '--headless', '--nologo', '--nofirststartwizard',
      '--convert-to', 'pdf', '--outdir', outDir, docxPath
    ], { timeout: 60000 });
    const pdfPath = path.join(outDir, path.basename(docxPath, path.extname(docxPath)) + '.pdf');
    if (!fs.existsSync(pdfPath)) return null;
    return await renderFileQuickLookPreview(pdfPath, '1600');
  } catch (err) {
    console.error('LibreOffice preview error:', err.message);
    return null;
  } finally {
    try { fs.rmSync(outDir, { recursive: true, force: true }); } catch (e) {}
  }
}

async function renderDocxPreviewImage(docxPath) {
  const quickLook = await renderFileQuickLookPreview(docxPath, '1600');
  if (quickLook) return quickLook;
  return await renderDocxLibreOfficePreview(docxPath);
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 920,
    minWidth: 1024,
    minHeight: 700,
    title: "LaTeX 简历工坊 | 可视化 LaTeX 简历生成器",
    icon: WINDOW_ICON,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    },
    titleBarStyle: 'hiddenInset',
    show: false
  });

  mainWindow.setMenuBarVisibility(false);

  const isDev = !app.isPackaged;
  if (isDev) {
    mainWindow.loadURL(`http://localhost:${RESUME_DEV_PORT}`);
  } else {
    mainWindow.loadFile(path.join(__dirname, 'dist/index.html'));
  }

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  createWindow();
  setTimeout(() => {
    if (!app.isPackaged || process.env.RESUME_ENABLE_AUTO_UPDATE !== '1') return;
    console.log('[AutoUpdate] Checking for updates...');
    autoUpdater.checkForUpdatesAndNotify().catch(err => {
      console.error('[AutoUpdate] Check failed:', err.message);
    });
  }, 3000);

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

ipcMain.on('check-for-updates', () => {
  console.log('[AutoUpdate] Manual check triggered');
  autoUpdater.checkForUpdatesAndNotify().catch(err => {
    console.error('[AutoUpdate] Manual check failed:', err.message);
    if (mainWindow) mainWindow.webContents.send('update-error', err.message);
  });
});

autoUpdater.on('update-available', (info) => {
  console.log('[AutoUpdate] Update available:', info.version);
  if (mainWindow) mainWindow.webContents.send('update-available', { version: info.version });
});
autoUpdater.on('update-not-available', () => {
  console.log('[AutoUpdate] No updates available');
  if (mainWindow) mainWindow.webContents.send('update-not-available');
});
autoUpdater.on('error', (err) => {
  console.error('[AutoUpdate] Error:', err.message);
  if (mainWindow) mainWindow.webContents.send('update-error', err.message);
});
autoUpdater.on('download-progress', (progress) => {
  if (mainWindow) mainWindow.webContents.send('download-progress', progress.percent);
});
autoUpdater.on('update-downloaded', (info) => {
  console.log('[AutoUpdate] Update downloaded:', info.version);
  if (mainWindow) mainWindow.webContents.send('update-downloaded', { version: info.version });
});
ipcMain.on('restart-and-update', () => {
  autoUpdater.quitAndInstall();
});

ipcMain.handle('get-template-list', async () => {
  return scanTemplates();
});

ipcMain.handle('get-latex-compiler-status', async () => {
  return getLatexCompilerStatus();
});

ipcMain.handle('parse-template-layout', async (event, { templatePath }) => {
  try {
    const template = findTemplateByName(templatePath);
    if (template?.kind === 'latex' || template?.engineType === 'latex') {
      return { success: true, engineType: 'latex', fields: [] };
    }
    const SPATIAL_SCRIPT = app.isPackaged
      ? path.join(process.resourcesPath, 'utils', 'spatial_engine.py')
      : path.join(__dirname, 'src/utils/spatial_engine.py');
    const { stdout } = await execFileAsync(
      'python3',
      [SPATIAL_SCRIPT, '--export-layout', templatePath],
      { timeout: 15000 }
    );
    return JSON.parse(stdout);
  } catch (err) {
    console.error('Parse template layout error:', err.message);
    return { error: err.message };
  }
});

const SPATIAL_WHITELIST = new Set([
  "文艺单页03", "文艺单页04", "文艺单页07", "文艺单页09", "文艺单页16",
  "活泼单页12", "知页简历02", "知页简历03", "稳重单页01", "稳重单页21",
  "简约单页18", "简约单页19", "简约单页30",
  "文艺单页10", "文艺单页12", "稳重单页06", "稳重单页12", "稳重单页20", "简约单页25"
]);

ipcMain.handle('check-template-config', async (event, { templatePath }) => {
  const template = findTemplateByName(templatePath);
  if (template?.kind === 'latex' || template?.engineType === 'latex') {
    return {
      hasConfig: true,
      fallback: false,
      engineType: 'latex',
      kind: 'latex',
      tags: template.tags || [],
      recommendedCompiler: template.recommendedCompiler || 'xelatex'
    };
  }

  let docxtplPath = templatePath.replace('.docx', '.docxtpl.docx');
  let hasDocxtpl = fs.existsSync(docxtplPath);
  
  let configPath = templatePath.replace('.docx', '.yaml');
  let hasYaml = fs.existsSync(configPath);
  
  const baseName = path.basename(templatePath, '.docx');
  let engineType = 'spatial';
  let fallback = false;
  
  if (hasDocxtpl) {
    engineType = 'docxtpl';
  } else if (SPATIAL_WHITELIST.has(baseName)) {
    engineType = 'spatial';
  } else if (hasYaml) {
    engineType = 'yaml';
    try {
      const content = fs.readFileSync(configPath, 'utf-8');
      fallback = content.includes('fallback: true');
    } catch (e) {}
  }
  
  return { hasConfig: hasYaml || hasDocxtpl, fallback, engineType };
});

ipcMain.handle('select-template-dir', async () => {
  return { success: true, count: scanTemplates().length };
});

ipcMain.handle('get-api-config', async () => {
  const cfg = loadConfig();
  return {
    provider: cfg.aiProvider || 'custom',
    apiUrl: cfg.apiUrl || '',
    apiKey: cfg.apiKey || '',
    modelName: cfg.modelName || 'deepseek-chat'
  };
});

ipcMain.handle('save-api-config', async (event, apiCfg) => {
  const cfg = loadConfig();
  cfg.aiProvider = apiCfg.provider;
  cfg.apiUrl = apiCfg.apiUrl;
  cfg.apiKey = apiCfg.apiKey;
  cfg.modelName = apiCfg.modelName;
  saveConfig(cfg);
  return { success: true };
});

ipcMain.handle('render-preview', async (event, { templateName, resumeData, layoutAdjustments }) => {
  const template = findTemplateByName(templateName);
  if (!template) return { success: false, error: '模板未找到' };

  if (template.kind === 'latex' || template.engineType === 'latex') {
    let result = null;
    try {
      result = await renderLatexTemplate(template, resumeData, { noCompile: false, layoutAdjustments });
      const texSource = readLatexTexSource(result);
      if (!result.success) {
        if (texSource) {
          return {
            success: true,
            engineType: 'latex',
            texPath: result.texPath,
            texSource,
            compiled: false,
            missingCompiler: Boolean(result.missingCompiler || !result.compiler?.available),
            compiler: result.compiler,
            message: result.error || result.stderr || 'LaTeX PDF 预览失败；可导出 .tex 查看源码。'
          };
        }
        return { success: false, engineType: 'latex', error: result.error || 'LaTeX 渲染失败' };
      }
      if (result.missingCompiler || !result.compiled || !result.pdfPath || !fs.existsSync(result.pdfPath)) {
        return {
          success: true,
          engineType: 'latex',
          texPath: result.texPath,
          texSource,
          compiled: false,
          missingCompiler: Boolean(result.missingCompiler || !result.compiler?.available),
          compiler: result.compiler,
          message: result.message || result.error || result.compiler?.message || '未检测到 LaTeX 编译器；可导出 .tex 到 Overleaf 或本地编译。'
        };
      }
      const previewImageBase64 = await renderFileQuickLookPreview(result.pdfPath, '1600');
      return {
        success: true,
        engineType: 'latex',
        texPath: result.texPath,
        pdfPath: result.pdfPath,
        texSource,
        compiled: true,
        compiler: result.compiler,
        previewImageBase64,
        message: previewImageBase64 ? '' : 'PDF 已生成，但系统图片预览转换失败；可导出 .tex 或编译 PDF。'
      };
    } catch (err) {
      return { success: false, engineType: 'latex', error: 'LaTeX 预览失败: ' + err.message };
    } finally {
      if (result && process.env.RESUME_DEBUG_PREVIEW !== '1') cleanupLatexOutput(result);
    }
  }

  const tempDir = app.getPath('temp');
  const tempDocx = path.join(tempDir, `preview_${Date.now()}.docx`);

  const filled = await fillDocxAsync(template.path, resumeData, tempDocx, layoutAdjustments);
  if (!filled) return { success: false, error: '模板填充失败' };

  try {
    if (process.env.RESUME_DEBUG_PREVIEW === '1') {
      fs.copyFileSync(tempDocx, path.join(app.getPath('temp'), 'last_preview.docx'));
    }
    const previewImageBase64 = await renderDocxPreviewImage(tempDocx);
    const buffer = fs.readFileSync(tempDocx);
    try { fs.unlinkSync(tempDocx); } catch (e) {}
    return { success: true, engineType: template.engineType || 'docx', docxBase64: buffer.toString('base64'), previewImageBase64 };
  } catch (err) {
    try { fs.unlinkSync(tempDocx); } catch (e) {}
    return { success: false, error: '读取预览 Word 失败: ' + err.message };
  }
});

ipcMain.handle('render-latex-source-preview', async (event, { source, name, resumeData }) => {
  if (!source || !String(source).trim()) {
    return { success: false, engineType: 'latex', error: 'LaTeX 源码为空' };
  }

  let result = null;
  try {
    result = await renderLatexSource(source, { name: name || 'edited-latex-preview', resumeData });
    const texSource = readLatexTexSource(result);
    if (!result.success) {
      return {
        success: false,
        engineType: 'latex',
        error: result.error || result.compileError || '手动 LaTeX 源码编译失败',
        texSource: texSource || String(source),
        message: result.stderr || result.stdout || result.error || ''
      };
    }
    if (result.missingCompiler || !result.compiled || !result.pdfPath || !fs.existsSync(result.pdfPath)) {
      return {
        success: false,
        engineType: 'latex',
        texSource: texSource || String(source),
        compiled: false,
        missingCompiler: Boolean(result.missingCompiler || !result.compiler?.available),
        compiler: result.compiler,
        error: result.compileError || result.compiler?.message || 'LaTeX 源码未能编译出 PDF',
        message: result.stdout || result.stderr || ''
      };
    }
    const previewImageBase64 = await renderFileQuickLookPreview(result.pdfPath, '1600');
    return {
      success: Boolean(previewImageBase64),
      engineType: 'latex',
      texSource: texSource || String(source),
      compiled: true,
      compiler: result.compiler,
      previewImageBase64,
      pdfPath: result.pdfPath,
      error: previewImageBase64 ? '' : 'PDF 已生成，但系统图片预览转换失败',
      message: previewImageBase64 ? '已根据手动修改重新生成 LaTeX 预览。' : 'PDF 已生成，但系统图片预览转换失败。'
    };
  } catch (err) {
    return { success: false, engineType: 'latex', error: '手动 LaTeX 源码预览失败: ' + err.message, texSource: String(source) };
  } finally {
    if (result && process.env.RESUME_DEBUG_PREVIEW !== '1') cleanupLatexOutput(result);
  }
});

ipcMain.on('export-to-word', async (event, { templateName, resumeData, layoutAdjustments }) => {
  if (!mainWindow) return;

  const template = findTemplateByName(templateName);
  if (!template) {
    event.reply('word-failed', '模板未找到');
    return;
  }
  if (template.kind === 'latex' || template.engineType === 'latex') {
    event.reply('word-failed', 'LaTeX 模板不支持 Word 导出，请使用“导出 .tex”或“编译 PDF”。');
    return;
  }

  const defaultName = `${resumeData.basicInfo.name || '我的'}_求职简历.docx`;
  const { canceled, filePath } = await dialog.showSaveDialog(mainWindow, {
    title: '导出 Word 简历',
    defaultPath: path.join(app.getPath('downloads'), defaultName),
    filters: [{ name: 'Word 文档 (*.docx)', extensions: ['docx'] }]
  });

  if (canceled || !filePath) {
    event.reply('word-failed', '导出已取消');
    return;
  }

  const tempJson = path.join(app.getPath('temp'), `export_${Date.now()}.json`);
  fs.writeFileSync(tempJson, JSON.stringify(resumeData, null, 2), 'utf-8');

  let tempLayoutJson = null;
  let layoutArg = '';
  if (layoutAdjustments && Object.keys(layoutAdjustments).length > 0) {
    tempLayoutJson = path.join(app.getPath('temp'), `export_layout_${Date.now()}.json`);
    fs.writeFileSync(tempLayoutJson, JSON.stringify(layoutAdjustments, null, 2), 'utf-8');
    layoutArg = ` "${tempLayoutJson}"`;
  }

  exec(`python3 "${ENGINE_SCRIPT}" "${tempJson}" "${template.path}" "${filePath}"${layoutArg}`, { encoding: 'utf-8', timeout: 30000 }, (error, stdout, stderr) => {
    try { fs.unlinkSync(tempJson); } catch (e) {}
    if (tempLayoutJson) {
      try { fs.unlinkSync(tempLayoutJson); } catch (e) {}
    }
    if (error) {
      // Fallback to v2
      const tempJson2 = path.join(app.getPath('temp'), `export2_${Date.now()}.json`);
      fs.writeFileSync(tempJson2, JSON.stringify(resumeData, null, 2), 'utf-8');
      exec(`python3 "${FILLER_SCRIPT}" "${tempJson2}" "${template.path}" "${filePath}"`, { encoding: 'utf-8', timeout: 30000 }, (err2) => {
        const finishFallback = () => {
          try { fs.unlinkSync(tempJson2); } catch (e) {}
          event.reply('word-saved', `已导出: ${path.basename(filePath)}`);
        };
        if (err2) {
          try { fs.unlinkSync(tempJson2); } catch (e) {}
          console.error('Export error:', err2.message);
          event.reply('word-failed', 'Word 导出失败');
          return;
        }
        if (shouldApplyPhotoReplacement(resumeData)) {
          exec(`python3 "${PHOTO_SCRIPT}" "${tempJson2}" "${filePath}"`, { encoding: 'utf-8', timeout: 30000 }, (photoErr) => {
            if (photoErr) console.error('Export photo replacement fallback error:', photoErr.message);
            finishFallback();
          });
        } else {
          finishFallback();
        }
      });
      return;
    }
    console.log('Export:', stdout);
    event.reply('word-saved', `已导出: ${path.basename(filePath)}`);
  });
});

ipcMain.on('export-latex-tex', async (event, { templateName, resumeData, layoutAdjustments }) => {
  if (!mainWindow) return;
  const template = findTemplateByName(templateName);
  if (!template || template.kind !== 'latex') {
    event.reply('latex-tex-failed', 'LaTeX 模板未找到');
    return;
  }

  const baseName = safeExportStem(resumeData?.basicInfo?.name || '我的') + '_' + safeExportStem(template.displayName || template.name);
  const { canceled, filePath } = await dialog.showSaveDialog(mainWindow, {
    title: '导出 LaTeX 源文件',
    defaultPath: path.join(app.getPath('downloads'), `${baseName}.tex`),
    filters: [{ name: 'LaTeX 源文件 (*.tex)', extensions: ['tex'] }]
  });
  if (canceled || !filePath) {
    event.reply('latex-tex-failed', '导出已取消');
    return;
  }

  let result = null;
  try {
    result = await renderLatexTemplate(template, resumeData, { noCompile: true, layoutAdjustments });
    if (!result.success || !result.texPath || !fs.existsSync(result.texPath)) {
      event.reply('latex-tex-failed', result.error || 'LaTeX 源文件生成失败');
      return;
    }
    fs.copyFileSync(result.texPath, filePath);
    event.reply('latex-tex-saved', `LaTeX 源文件已导出: ${path.basename(filePath)}`);
  } catch (err) {
    event.reply('latex-tex-failed', 'LaTeX 源文件导出失败: ' + err.message);
  } finally {
    if (result) cleanupLatexOutput(result);
  }
});

ipcMain.on('export-latex-pdf', async (event, { templateName, resumeData, layoutAdjustments }) => {
  if (!mainWindow) return;
  const template = findTemplateByName(templateName);
  if (!template || template.kind !== 'latex') {
    event.reply('latex-pdf-failed', 'LaTeX 模板未找到');
    return;
  }

  const compilerStatus = await getLatexCompilerStatus();
  if (!compilerStatus.compiler?.available) {
    event.reply('latex-pdf-failed', compilerStatus.compiler?.message || '未检测到 LaTeX 编译器；请先导出 .tex，或安装 Tectonic/MacTeX 后再编译 PDF。');
    return;
  }

  const baseName = safeExportStem(resumeData?.basicInfo?.name || '我的') + '_' + safeExportStem(template.displayName || template.name);
  const { canceled, filePath } = await dialog.showSaveDialog(mainWindow, {
    title: '编译并导出 LaTeX PDF',
    defaultPath: path.join(app.getPath('downloads'), `${baseName}.pdf`),
    filters: [{ name: 'PDF 文档 (*.pdf)', extensions: ['pdf'] }]
  });
  if (canceled || !filePath) {
    event.reply('latex-pdf-failed', '导出已取消');
    return;
  }

  let result = null;
  try {
    result = await renderLatexTemplate(template, resumeData, { noCompile: false, layoutAdjustments });
    if (!result.success || !result.compiled || !result.pdfPath || !fs.existsSync(result.pdfPath)) {
      event.reply('latex-pdf-failed', result.error || result.compileError || result.compiler?.message || 'LaTeX PDF 编译失败');
      return;
    }
    fs.copyFileSync(result.pdfPath, filePath);
    event.reply('latex-pdf-saved', `LaTeX PDF 已导出: ${path.basename(filePath)}`);
  } catch (err) {
    event.reply('latex-pdf-failed', 'LaTeX PDF 导出失败: ' + err.message);
  } finally {
    if (result) cleanupLatexOutput(result);
  }
});

ipcMain.on('print-to-pdf', async (event, { defaultFileName, htmlContent }) => {
  if (!mainWindow) return;
  const { canceled, filePath } = await dialog.showSaveDialog(mainWindow, {
    title: '导出 PDF',
    defaultPath: path.join(app.getPath('downloads'), defaultFileName || '我的求职简历.pdf'),
    filters: [{ name: 'PDF 文档 (*.pdf)', extensions: ['pdf'] }]
  });
  if (canceled || !filePath) {
    event.reply('pdf-failed', '导出已取消');
    return;
  }
  try {
    // Create HTML document with proper print styling from frontend HTML content
    const fullHtml = `<!DOCTYPE html><html><head><meta charset="utf-8">
      <style>
        @page { margin: 0; size: A4; }
        body { margin: 0; padding: 0; background: #fff; -webkit-print-color-adjust: exact; }
        .docx-wrapper { padding: 0 !important; background: transparent !important; box-sizing: border-box; box-shadow: none !important; }
        .docx { box-shadow: none !important; border: none !important; margin: 0 !important; }
        table { border-collapse: collapse; }
      </style></head><body>${htmlContent || '<p>简历内容</p>'}</body></html>`;

    const tempHtml = path.join(app.getPath('temp'), `pdf_${Date.now()}.html`);
    fs.writeFileSync(tempHtml, fullHtml, 'utf-8');

    // Create hidden window and print to PDF
    const pdfWindow = new BrowserWindow({
      width: 794, height: 1123, show: false, webPreferences: { contextIsolation: false }
    });
    await pdfWindow.loadFile(tempHtml);
    const pdfData = await pdfWindow.webContents.printToPDF({
      margins: { top: 0, bottom: 0, left: 0, right: 0 },
      pageSize: 'A4', printBackground: true, landscape: false, displayHeaderFooter: false
    });
    pdfWindow.close();

    try { fs.unlinkSync(tempHtml); } catch (e) {}

    fs.writeFile(filePath, pdfData, (err) => {
      if (err) { event.reply('pdf-failed', 'PDF 写入失败'); return; }
      event.reply('pdf-saved', `PDF 已导出: ${path.basename(filePath)}`);
    });
  } catch (e) {
    console.error('PDF error:', e);
    event.reply('pdf-failed', 'PDF 生成失败: ' + e.message);
  }
});
