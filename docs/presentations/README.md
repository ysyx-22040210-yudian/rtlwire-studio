# 功能与实现原理演示文稿

- [可编辑 PowerPoint，24 页](RTLWire_Studio_Functions_and_Architecture_v0.5.0.pptx)
- [PDF 预览](RTLWire_Studio_Functions_and_Architecture_v0.5.0.pdf)
- [逐页内容与讲解备注](slide_notes.md)
- [生成脚本](build_deck.cjs)

正文讲解两类 ELAB 接线场景、嵌套层次的排他归属、NPI 连接提取、架构图布局、FSDB 事件读取、RPT 按位分组、隔离/掉电/恢复规则和验证边界。各页的演讲者备注列出了相关实现文件或函数。

图示使用 PowerPoint 原生形状和文本，便于二次编辑。截图来自 Linux 上实际运行的 Tk 界面，使用本仓库整理后的示例记录。演示文稿采用 16:9、暖白与陶土色，并保留中文字体回退所需的可编辑文本。

## 重新生成

在仓库根目录安装文档构建依赖并运行：

```bash
npm install --no-save --package-lock=false pptxgenjs@4.0.1
node docs/presentations/build_deck.cjs
```

字体使用 Microsoft YaHei 和 Consolas；未安装这些字体时，Office 或 LibreOffice 会替换字体，需要再次检查换行和间距。该 Node.js 依赖只用于重建演示文稿，工具本身仍使用 Python 标准库与 Tk。

PDF 可用 PowerPoint 导出，或通过已安装的 LibreOffice 转换：

```bash
libreoffice --headless --convert-to pdf --outdir docs/presentations \
  docs/presentations/RTLWire_Studio_Functions_and_Architecture_v0.5.0.pptx
```

发布前已将 24 页全部渲染为图片进行检查，并修复端口连线、标签间距、示例一致性和页边距问题。`slide_content.json` 提供生成时的文字与文本框坐标，便于内容审查；它不替代视觉检查。
