---
name: md-print-pdf
version: 1.1.0
display_name: Markdown 打印工作流
display_name_en: md-print-pdf
license: MIT
description: 把 Markdown 一键转成可交付的 A4 打印版 PDF（零第三方 Python 依赖 + playwright-core 驱动系统 Edge）。当用户需要"md 转 PDF / 出正式打印版报告 / 调研报告排版定稿 / 报告导出 Word 级排版 PDF / 公式表格图片混排打印"时使用。内置封面、可点击目录、页脚页码、图表自动编号与交叉引用、KaTeX 离线公式、PDF 书签与元数据、四步流水线质检。
---

# md-print-pdf · Markdown → A4 打印版 PDF

## 一句话定位

输入一个 `.md`，输出一份**版式达到正式交付标准**的 A4 PDF：封面、可点击目录、页脚页码、图表自动编号、KaTeX 离线公式、PDF 书签元数据，全程零网络依赖。

## 何时用本 Skill

- 用户说：md 转 PDF、出打印版、报告定稿排版、导出正式交付稿
- 文档要素：标题层级 + 表格 + 图片 + 代码块 + 列表 + 引用块 + 公式 + 交叉引用
- 要求：封面/目录/页码/书签齐全，黑白打印可辨，跨页表格有表头

## 快速开始（一条命令）

```bash
python scripts/run.py --md <输入.md> --out <输出.pdf> --config print.config.json
```

四步流水线自动执行：md→HTML → HTML→PDF → 封面页脚留白 → 元数据写入 → 质检（共五步）。
中间产物默认写系统临时目录（`--work-dir` 可指定），`--keep-html` 保留中间 HTML。

## 分步调用（需要中间产物时）

```bash
# 1. md → A4 打印版 HTML（零第三方依赖，仅标准库）
python scripts/md2html.py --md in.md --out print.html --config print.config.json [--diag diag.json]

# 2. HTML → PDF（必须设 NODE_PATH，否则找不到 playwright-core）
NODE_PATH="<node工作区>/node_modules" node scripts/print_pdf.js \
  --html print.html --pdf out.pdf --config print.config.json --preset title-pagefooter

# 3. 封面页脚留白（增量更新，零依赖；多封面页用 --pages 1,2）
python scripts/pdf_cover_mask.py --pdf out.pdf --out out.pdf --pages 1

# 4. 质检（读 diag JSON + PDF 结构，退出码 0=可交付）
python scripts/qc_check.py --diag diag.json --pdf out.pdf --md in.md --json qc.json
```

## 环境依赖与探测（必须先做）

| 依赖 | 探测顺序 |
|---|---|
| Python ≥3.10 | `python` → `python3` → 托管目录 |
| Node ≥18 | `node` → 托管 `.workbuddy/binaries/node/versions/*` |
| playwright-core | 当前目录 `node_modules` → `NODE_PATH` 各段 |
| Edge/Chrome | `EDGE_PATH`/`CHROME_PATH` 环境变量 → Windows/Mac/Linux 常见安装位 |

脚本均已内置探测与友好报错；缺什么会明确说缺什么，不静默失败。

## 五条硬规则（不可绕过）

1. **`NODE_PATH` 必须 Windows 风格**（`C:\...`），bash 里用 `export NODE_PATH='C:\...'`
2. **语法检查禁用 `py_compile`**（会生成 `__pycache__` 污染目录），用
   `python -c "import ast; ast.parse(open(f,encoding='utf-8').read())"`
3. **临时产物一律落系统临时目录**，禁止写进仓库/项目目录
4. **封面 HTML 必须 `page-break-after: always` + `min-height: 250mm`**，否则封面与目录挤同页
5. **跨页表头只认 `<thead>` + `display: table-header-group`**，裸 `<tr><th>` 无效

## 冻结版式规范（2026-09-17 用户确认）

- **配色**：蓝色单色体系，全部标题统一 `#14508C`，层级靠字号+装饰线区分
  - 篇 H1 17pt + 1.5pt 主线 ｜ 章 H2 13.5pt + 0.75pt 浅蓝线 #B5D4F4 ｜ 节 H3 11.5pt ｜ 目 H4 10.5pt
- **正文**：宋体 10.5pt / 行距 1.6 / **首行缩进 2em** / 两端对齐
- **字体**：标题黑体、正文宋体、英文数字 Times New Roman、表头宋体加粗、代码等宽
- **封面**：居中版式 + 46mm 主色线 + 密级行（默认"内部材料　·　注意保密"）+ 页脚留白
- **框体**：摘要蓝 #F4F8FC/#14508C ｜ 提示黄 #FDF6E3/#A16207 ｜ 警示红 #FDECEA/#B3261E ｜ 图注灰 #F7F8FA/#9AA0A6
- **表格**：表头蓝字 #14508C + 浅蓝底 #E6F1FB + 1pt 主色下线；斑马纹默认关
- 功能色保留：`✅` #1D9E75（绿，仅用于验证标记，非标题色）、来源🔶 #BA7517、警示 #B3261E

详见 `references/css-rules.md`（完整样式）与 `references/config-reference.md`（配置逐条）。

## 已知边界（须向用户说明，不得静默）

- **目录无页码**：浏览器内核页码变量只在页脚模板可用，无法注入正文目录（`toc.showPageNumber` 固定 false）
- **公式未激活时**：输出占位提示框 + 质检告警，绝不输出乱码；激活条件是 `assets/katex/` 就位
- **脚注排文末**：浏览器打印引擎无"当页页底"能力，脚注统一排在文档末尾
- **章名页脚不可注入**：`chapter-pagefooter` 预设只显示文档名（引擎无法感知当前章名）
- **页码从封面起算**：封面页脚已留白但页码计数包含封面
- **书签需 tagged 双开**：`outline:true` 单给不产出 /Outlines，须同时 `tagged:true`（脚本已内置处理）
- **元数据只有 Title 走引擎**：Author/Subject/Keywords 由 `pdf_meta.py` 增量更新写入（run.py 自动执行）

## 深入阅读

- `references/pitfalls.md` —— 22 条实测坑位（复现路径 + 正解），改代码前先查
- `references/css-rules.md` —— 排版四铁律 + 冻结样式规范全文
- `references/config-reference.md` —— print.config.json 全部配置项逐条说明
- `examples/demo.md` / `demo.pdf` —— 覆盖全部支持要素的示例
- `examples/style-preview.html` / `style-preview.pdf` —— 版式规范样张（5 页）
