# 坑位清单 · 24 条（实测踩过）

> 每条含【现象】【根因】【正解】。改代码前先通读一遍，同类错误不二犯。
> 1–14 来自立项需求文档 §8；15–22 来自 2026-09-16/17 构建过程实测补充；23–24 来自验收阶段实测。

---

## 转换器（md2html.py）

### 1. `<img>` 未包 `<p class="fig">`
- **现象**：单行 HTML `<img>` 是行内元素，与前后文字挤同一行。
- **正解**：凡整行仅含 `<img>` 的，转换时包成 `<p class="fig">…</p>`。

### 2. 并排图表格被加边框
- **现象**：md 内嵌 HTML `<table>` 被套用 md 表格样式，并排图带边框。
- **正解**：md 表格加 `class="md"`；内嵌 HTML 表用 `table:not(.md)` 排除。

### 3. 表格空单元格塌陷
- **正解**：空单元格输出 `&nbsp;`。

### 4. 图片路径含中文
- **现象**：手工拼 `file:///` URI 遇中文/空格出错。
- **正解**：用 `Path.as_uri()` 标准转码，勿手工拼字符串。

### 5. HTML 行被当正文数字审计
- **现象**：质检把 `width="50%"` 里的 50 当正文数字报异常。
- **正解**：质检规则跳过以 `<` 开头的行。

### 6. 图注检查窗口过窄误报
- **现象**：`<img>` 常在表格容器中，图注距离被拉远，检查窗口 ±3 行误报"无图注"。
- **正解**：对 `<img>` 场景图注检查窗口放宽到 ±8 行。

### 7. `%` 格式化遇 HTML 抛 ValueError
- **现象**：含 `width="50%"` 的字符串做 `%` 格式化报 `unsupported format character`。
- **正解**：含 HTML 的字符串禁用 `%` 格式化，用 f-string 或 `.format()`。

### 8. 变量替换顺序错误
- **现象**：`![]()` 已转成 `<img>` 后，后续正则仍按旧形态匹配 → 匹配失败。
- **正解**：变换链每一步后确认下一步的匹配目标形态；或统一在最后阶段转换。

### 9. 批量改写脚本中途失败污染文件
- **正解**：补丁脚本每步 `assert count == 1`，任一失败立即 `sys.exit(1)` 且不落盘；动手前先备份到 temp。

### 12. 表格分隔行识别失败
- **现象**：`|---|---|` 匹配不上导致整表异常。
- **正解**：分隔行严格匹配 `^\|[\s\-:|]+\|$`；表头列数与数据列数不一致时补齐空格并记入 diag（`ragged`）。

### 13. `__pycache__` 污染项目目录
- **现象**：`py_compile` 或普通导入会在脚本同目录生成缓存目录。
- **正解**：语法检查一律 `python -c "import ast; ast.parse(open(f,encoding='utf-8').read())"`，**禁用 py_compile**；`.gitignore` 必须含 `__pycache__/`。

### 14. 临时产物落在仓库内
- **正解**：中间 HTML、截图、diag JSON 统一写系统临时目录（`run.py` 默认 `tempfile.gettempdir()`，`--work-dir` 可覆盖）；`.gitignore` 覆盖 `*.html`（examples 豁免）。

---

## 打印引擎（print_pdf.js / 浏览器）

### 10. PDF 无法目视验收
- **现象**：无 pypdf，解析不了 PDF 内容。
- **正解**：headless 浏览器 `page.goto('file:///x.pdf')` 打开内置 PDF 查看器截图目视；`#page=N&zoom=100` 锚点翻页。

### 11. PDF 文件过大
- **正解**：位图预压缩；质检对 >10MB 提示、>20MB 告警；能用 SVG 就用 SVG。

### 15. 封面与目录挤同页 ★构建实测
- **现象**：封面后面直接跟目录，没有分页；或封面高度不够页脚顶到正文。
- **根因**：`.cover` 没有 `page-break-after: always`；`min-height: 245mm` 小于 A4 内容区 257mm。
- **正解**：`.cover { min-height: 250mm; page-break-after: always; }`（250mm 留余量）。

### 16. 跨页表格表头不重复 ★构建实测
- **现象**：长表翻页后第二页没有表头。
- **根因**：Chromium 打印引擎只认 `<thead>` 的 `table-header-group`；直接写 `<tr><th>` 无效。
- **正解**：表头必须包 `<thead>` + CSS `thead { display: table-header-group; }`。

### 17. f-string 里写 CSS 花括号炸裂 ★构建实测
- **现象**：`build_css` 用 f-string 拼样式表，CSS 的 `{}` 被当占位符抛错。
- **正解**：CSS 字面花括号全部写成 `{{ }}`——**注释里的 `{` 也要转义**，最容易漏。

### 18. KaTeX 公式截图时机过早 ★构建实测
- **现象**：截图/PDF 里公式是原始 LaTeX 源码。
- **根因**：KaTeX 渲染是异步握手（`data-math-state="pending"` → `done:N`），`load` 事件后立即截图会截到未渲染态。
- **正解**：等待 `data-math-state` 变为 `done:` 前缀再出图，兜底 `waitForTimeout(1500)`。

### 19. NODE_PATH 用 POSIX 风格找不到模块 ★构建实测
- **现象**：`export NODE_PATH='<用户目录>/...'` 后 `require('playwright-core')` 仍失败。
- **正解**：Windows 下必须 **Windows 风格反斜杠**：`export NODE_PATH='<用户目录>\...\node_modules'`。

---

## 产物与质检（pdf_cover_mask.py / qc_check.py）

### 20. 预览面板锁死产物 PDF ★构建实测
- **现象**：回写 `style-preview.pdf` 报 `PermissionError [Errno 13]` / `WinError 32`，safe-delete 也失败。
- **根因**：预览面板外部进程持有文件句柄。
- **正解**：先探测（rename 试锁），被锁就写新文件名，释放后再回写；不要死循环重试。

### 21. diag JSON 结构与质检假设不符，统计全为 0 ★构建实测
- **现象**：md2html 明明报"表格 6 个"，qc_check 统计"表格 0 个"。
- **根因**：`--diag` 输出是**双层包装** `{md, out, math_mode, katex_dir, diag:{...}, warn_count}`，质检按扁平结构读；且 `math` 列表是"检测到的公式清单"而非"失败清单"。
- **正解**：质检先解包 `raw["diag"]`；公式告警只在 `math_mode != "render"` 时给，且合并为一条而非逐条刷屏。

### 22. Bash 沙箱缺 coreutils ★环境实测
- **现象**：`ls/grep/head/cat/dirname` 均 `command not found`；`python - </dev/null` 进入 REPL 刷屏。
- **正解**：文本/文件操作改用 python `-c` 或 heredoc（`python - <<'PYEOF' … PYEOF`）；文件读写优先专用工具；**禁止 `python - </dev/null`**。

### 23. 书签必须 `outline` 与 `tagged` 同时开 ★验收实测
- **现象**：`page.pdf({ outline: true })` 传了、playwright-core 1.63 也正确映射为 CDP `generateDocumentOutline`，但 PDF 里**静默没有** `/Outlines`（解压对象流确认）。
- **根因**：Edge 153 headless（含 `--headless=new`）只在**同时开启 `tagged: true`**（生成 Tagged PDF）时才产出大纲；单独 outline 被忽略，不报错。
- **正解**：`page.pdf({ outline: true, tagged: true, … })`。注意：裸字节搜 `/Outlines` 不可靠——书签字典可能位于压缩对象流内，须解压 FlateDecode 流后再搜。
- **代价**：Tagged PDF 略增体积（demo 实测 +8%），换来书签 + 无障碍结构，值得。

### 24. Chromium 只写 Title，其余元数据须后处理 ★验收实测
- **现象**：`<meta name="author">` / `description` / `keywords` 注入 HTML 后，PDF /Info 里**只有 /Title**（来自 `document.title`）。
- **根因**：Chromium printToPDF 只回写标题，不读 meta 标签。
- **正解**：零依赖增量更新追加新 /Info 对象（`scripts/pdf_meta.py`）：新对象号 = 原 /Size，新 xref 子段只含新对象，新 trailer 用 `/Info` 指向新对象、`/Prev` 链回原 xref——旧对象不动，Reader 按 /Prev 链合并。细节：`/Size` 是整数不是引用，解析 trailer 别套用 `N 0 R` 正则；非 ASCII 值写 UTF-16BE（`FEFF` 前缀）十六进制串。

---

## 已否决的技术路线（勿走回头路）

| 方案 | 结论 | 原因 |
|---|---|---|
| Edge `--remote-debugging-port` + 自写 CDP | ❌ | 沙箱拦截 loopback TCP |
| Edge `--print-to-pdf` | 🔶 不足 | CLI 不支持 footerTemplate，拿不到"第 N 页 / 共 M 页" |
| Pandoc + LaTeX | ❌ | 约 1GB 发行版，网络不通装不上 |
| Python markdown/reportlab/weasyprint | ❌ | 未安装且无法安装 |
| 在线转换服务 | ❌ | 违背离线原则，工程文档不宜外传 |

**正解**：playwright-core（预装于托管 Node 工作区）走 `--remote-debugging-pipe`（stdio），完全绕开网络限制。
