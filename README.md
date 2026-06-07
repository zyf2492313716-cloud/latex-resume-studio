# LaTeX 简历工坊

LaTeX 简历工坊是一个独立打包的 macOS 桌面简历生成器，专注 **LaTeX 简历模板**：可结构化填写简历、可视化微调照片/主题/字号/间距，导出 `.tex`，并在检测到本机 LaTeX 编译器后进一步编译 PDF。

> 即使电脑没有安装 LaTeX 编译器，应用也不会崩溃；LaTeX 模板仍可正常生成 `.tex` 源文件，并给出清晰的编译器缺失提示。

## 下载与安装

### 1. 下载 DMG

从 [GitHub Releases](https://github.com/zyf2492313716-cloud/latex-resume-studio/releases) 下载最新版本的 `.dmg` 文件。

### 2. 打开 DMG

双击下载的 `.dmg` 文件，会弹出安装窗口。

### 3. 拖拽安装

将左侧的 **LaTeX 简历工坊.app** 图标拖拽到右侧的 **Applications** 文件夹图标上。

### 4. 首次启动

由于当前应用未经过 Apple 官方签名，首次打开时可能会看到安全提示。

解决方法：

- 打开 **系统设置** → **隐私与安全性**
- 在页面底部找到“已阻止使用 LaTeX 简历工坊”的提示
- 点击 **仍要打开**
- 或者：在 Applications 文件夹中右键点击应用图标，选择 **打开**

如果提示“应用程序已损坏”，可只对新应用执行：

```bash
xattr -cr /Applications/LaTeX\ 简历工坊.app
```

## 功能特性

- **LaTeX-only 模板库**：内置 12 套 LaTeX 简历模板，包括学术、ATS、侧栏、时间线、创意卡片和原 Word 风格复刻模板。
- **预览内可视调版**：在预览框内调整照片位置、照片尺寸、主题色、字号、间距和紧凑模式，并自动重编译预览。
- **照片自动压缩**：上传大图时自动压缩并转为 LaTeX 友好的临时 JPEG，不再因为照片过大阻断使用。
- **可选 PDF 编译**：检测到 `xelatex` / `latexmk` 等本机 LaTeX 编译器后，可直接编译 PDF。
- **无编译器降级**：没有 LaTeX 编译器时仍能生成 `.tex`，并提示用户如何后续编译。
- **渲染预览**：使用 LaTeX 编译生成 PDF，再通过系统 QuickLook 转为预览图。
- **AI 智能提取**：粘贴简历文本后自动解析并填入结构化表单。
- **模板隔离打包**：打包版会随应用带上 `latex_templates/` 与 Python 渲染工具，不再打包旧 Word 模板资源。
- **自动更新入口**：GitHub Release 可作为后续版本更新来源。

## 系统要求

- macOS 12.0 或更高版本
- Apple Silicon (M 系列) 或 Intel Mac
- Python 3（系统或 Homebrew 安装均可）
- LaTeX PDF 编译为可选能力；仅导出 `.tex` 不要求安装 TeX 发行版

## 常见问题

**Q: 模板列表为空怎么办？**

A: 打包版会内置 `latex_templates/`；开发模式会读取仓库内 `latex_templates/`。右侧模板面板的“刷新”会重新扫描 LaTeX 模板。

**Q: 没有 LaTeX 编译器能用吗？**

A: 可以。LaTeX 模板仍可导出 `.tex` 文件；只有“编译 PDF”按钮需要本机 LaTeX 编译器。

**Q: 会覆盖旧的“智能简历生成器”吗？**

A: 不会。新版产品名为 **LaTeX 简历工坊**，包名为 `latex-resume-studio`，macOS `appId` 为 `com.zyf.latex-resume-studio`，并使用独立的 Electron userData 后缀。

## 开发

```bash
npm install
npm run build
python3 scripts/validate_latex_render.py
python3 scripts/validate_latex_preview_image.py
npm run dist
```

本地开发 Electron 时默认使用 `RESUME_DEV_PORT=3101`，避免复用旧项目常用的 `3000` 端口。

## 发布

- GitHub 仓库：<https://github.com/zyf2492313716-cloud/latex-resume-studio>
- Release 页面：<https://github.com/zyf2492313716-cloud/latex-resume-studio/releases>
- 本地打包脚本 `npm run dist` 默认包含 `--publish=never`，不会在打包阶段自动上传 Release。

## 技术栈

- Electron + React + Vite
- Python 3 渲染工具链
- LaTeX 模板渲染器

## License

MIT
