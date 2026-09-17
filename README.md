# md-print-pdf

Markdown 一键转 A4 打印版 PDF。零第三方 Python 依赖，浏览器内核本地渲染，全程离线可用。

## 特性

- **四步流水线**：md → 打印版 HTML → PDF → 质检，一条命令跑完
- **零 Python 依赖**：md2html / qc_check / pdf_cover_mask 只用标准库
- **正式文件级排版**：图片不跨页切断、标题不孤悬页尾、跨页表格重复表头、章标题另起页（四铁律，见 `references/css-rules.md`）
- **封面 / 目录 / 页脚**：模板化封面（含密级行）、可点击跳转目录、四套页脚预设
- **图表自动编号 + 交叉引用**：`图 1-1` / `表 2-3` 按章编号，`见图 1-1` 自动回填，错引用告警
- **KaTeX 离线公式**：`assets/katex/` 就位即自动渲染，缺位时占位提示不乱码
- **PDF 书签 + 元数据**：侧边大纲目录（书签需 `outline`+`tagged` 双开，见 pitfalls #23）；Title 由引擎写入，Author/Subject/Keywords 由 `pdf_meta.py` 增量更新写入
- **超宽表格自动降字号**：估宽超版心自动缩字号（7pt 下限），仍超则告警
- **质检报告**：字体预检、图片存在性、交叉引用、表格列齐与超宽、章节序号、题注位置、PDF 书签与元数据，分级汇总

## 快速开始

```bash
python scripts/run.py --md examples/demo.md --out demo.pdf
```

成功输出示例：

```
[1/4] md → HTML …… 标题 20 ｜ 表格 6 ｜ 图片 3 ｜ 公式 5
[2/4] HTML → PDF …… 12 页
[3/4] 封面页脚留白 …… 1 页
[4/4] 质检 …… 错误 0 / 告警 0 → 可交付
```

## 配置

默认配置 `print.config.json`，全部项可改，缺项回退内置默认值：

```bash
python scripts/run.py --md in.md --out out.pdf --config my.config.json
```

常用项速查（完整见 `references/config-reference.md`）：

| 想改什么 | 配置项 |
|---|---|
| 页边距 | `margin.top/bottom/left/right` |
| 正文字号 / 行距 / 缩进 | `typography.baseFontSize / lineHeight / firstLineIndent` |
| 主色 | `accent.primary`（当前冻结 `#14508C`） |
| 每章另起页 | `pageBreak.chapterOnNewPage` |
| 页脚样式 | `headerFooter.preset`（none / pagenum-only / title-pagefooter / chapter-pagefooter） |
| 封面字段 | `cover.title / subtitle / version / date / org / classification` |
| 目录深度 | `toc.depth` |
| 水印 | `watermark.enabled / text / opacity` |
| 公式 | `math.mode`（auto / render / placeholder） |

## md 写作约定

- **图片**：标准语法 `![图注](images/x.png)`，单独一行；并排图用 `<p class="fig"><img …><img …></p>`
- **图表题注**：`【图】标题写在图片下一行`、`【表】标题写在表格上一行`（按章自动编号，手写编号会被校验）
- **交叉引用**：`{图|图注文字}`、`{表|表注文字}`，转换时自动回填编号
- **公式**：`$...$` 行内，`$$...$$` 独立块
- **章节序号**：手写（一、/1、/1.1/1.1.1），工具只校验不生成（缺号、跳级会告警）

## 能力边界与限制声明（重要）

以下为本引擎（headless Chromium 打印）的**硬边界**，不是 bug：

1. **目录无页码**。页码变量 `pageNumber/totalPages` 只能在页眉页脚模板中使用，无法注入正文目录。`toc.showPageNumber` 固定 `false`。
2. **脚注排在文末**，无法做到"当页页底"。
3. **`chapter-pagefooter` 页脚显示文档名而非当前章名**——引擎在页脚模板里感知不到当前章。
4. **页码计数包含封面**（封面页脚已留白，但计数从封面起算）。
5. **不支持横竖版混排的自动检测**；横版需整体配置 `paper.orientation`。
6. **公式渲染需 `assets/katex/` 离线包**；未就位时输出占位提示框，绝不静默。
7. **Author/Subject/Keywords 依赖 `pdf_meta.py` 后处理**（`run.py` 流水线自动执行；单用 `print_pdf.js` 时只有 Title）。

## 跨平台说明

脚本内置依赖探测，非本机环境按以下顺序回退并友好报错：

- **Python**：`python` → `python3` → 常见安装路径
- **Node**：`node` → `NODE_EXE` → `.workbuddy/binaries/node/versions/*`
- **playwright-core**：当前目录 `node_modules` → `NODE_PATH` 各段 → 项目内
- **浏览器**：`EDGE_PATH` / `CHROME_PATH` 环境变量 → Edge/Chrome 各平台常见安装位

Linux/macOS 字体预检走 `fc-list`，缺中文字体时建议安装思源宋体/黑体并明确告警。

## 目录结构

```
├── SKILL.md                Skill 主文件（工作流与硬规则）
├── README.md               本文件
├── LICENSE                 MIT
├── print.config.json       默认配置（冻结规范）
├── scripts/                md2html.py · print_pdf.js · pdf_cover_mask.py · pdf_meta.py · qc_check.py · run.py
├── references/             pitfalls.md · css-rules.md · config-reference.md
├── assets/katex/           离线公式引擎（已就位）
└── examples/               demo.md · demo.pdf · style-preview.html · style-preview.pdf
```

## 协议

- 本仓库代码与文档采用 **MIT** 许可（见 `LICENSE`）：**可商用，但须保留版权声明与本许可文本（即保留署名）**。
- 第三方组件（KaTeX 等）的许可信息见 [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md)。
