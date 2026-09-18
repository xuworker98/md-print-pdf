# md-print-pdf

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.1.0-14508C.svg)]()
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()

**Markdown 一键转 A4 打印版 PDF**。零第三方 Python 依赖，浏览器内核本地渲染，全程离线可用——输入一个 `.md`，输出一份封面、目录、页码、图表编号、公式齐全的正式交付稿。

> 一个 `.md` 进去，一份可以直接打印、可以直接交付的 A4 PDF 出来。

---

## 一、工具说明

md-print-pdf 是一套 Markdown → A4 打印级 PDF 的转换流水线，面向**工程/技术文档的正式交付场景**：

- 工程/技术调研报告的正式交付（含图表、代码、公式）
- 内部决策材料的打印稿
- 需要「同一份 md，输出外观一致 PDF」的场合
- 离线环境出 PDF（不依赖任何在线服务）

核心是一条四步流水线，一条命令跑完：

```
md → 打印版 HTML → PDF → 封面页脚处理 → 元数据写入 → 质检
```

设计原则：**单一职责**（只做 md → 打印级 PDF）、**零网络依赖**（全用本机资源）、**配置驱动**（不改代码即可换样式）。

## 二、主要功能特点

- **四步流水线**：一条命令从 md 直达可交付 PDF，含质检出口（错误 0 / 告警 0 → 可交付）
- **零第三方 Python 依赖**：md2html / qc_check / pdf_cover_mask / pdf_meta 只用标准库
- **正式文件级排版四铁律**：图片不跨页切断、标题不孤悬页尾、跨页表格重复表头、章标题另起页
- **封面 / 目录 / 页脚**：模板化封面（含密级行）、可点击跳转目录、四套页脚预设
- **图表自动编号 + 交叉引用**：`图 1-1` / `表 2-3` 按章自动编号，`见图 1-1` 自动回填，错引用告警
- **KaTeX 离线公式**：`$...$` 行内、`$$...$$` 独立块，离线包就位即渲染，缺位时占位提示不乱码
- **PDF 书签 + 元数据**：侧边大纲书签；Title/Author/Subject/Keywords 自动写入
- **超宽表格自动降字号**：估宽超版心自动缩字号（7pt 下限），仍超则告警
- **质检报告**：字体预检、图片存在性、交叉引用、表格列齐与超宽、章节序号、题注位置、PDF 书签与元数据，分级汇总

## 三、操作说明

### 3.1 环境要求

| 依赖 | 版本 | 说明 |
|---|---|---|
| Python | ≥ 3.10 | 仅标准库，无需 pip install |
| Node.js | ≥ 18 | 驱动无头浏览器打印 |
| playwright-core | 任意近期版本 | `npm install playwright-core` 或设 `NODE_PATH` |
| Edge 或 Chrome | 系统已装即可 | 打印内核，无需单独下载浏览器 |

脚本内置依赖探测与友好报错：缺什么明确说缺什么，不静默失败。也支持 `EDGE_PATH` / `CHROME_PATH` / `NODE_EXE` 环境变量指定路径。

### 3.2 一条命令（推荐）

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

### 3.3 换自己的配置

默认配置 `print.config.json`，全部项可改，缺项回退内置默认值（完整见 `references/config-reference.md`）：

```bash
python scripts/run.py --md in.md --out out.pdf --config my.config.json
```

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

### 3.4 md 写作约定

- **图片**：标准语法 `![图注](images/x.png)`，单独一行；并排图用 `<p class="fig"><img …><img …></p>`
- **图表题注**：`【图】`标题写在图片下一行，`【表】`标题写在表格上一行（按章自动编号，手写编号会被校验）
- **交叉引用**：`{图|图注文字}`、`{表|表注文字}`，转换时自动回填编号
- **公式**：`$...$` 行内，`$$...$$` 独立块
- **章节序号**：手写（一、/1、/1.1/1.1.1），工具只校验不生成（缺号、跳级会告警）

## 四、注意事项

以下为 headless Chromium 打印引擎的**硬边界**，属于能力边界而非 bug，使用前请知悉：

1. **目录无页码**——页码变量只能在页眉页脚模板中使用，无法注入正文目录
2. **脚注排在文末**，无法做到"当页页底"
3. **`chapter-pagefooter` 页脚显示文档名而非当前章名**（引擎在页脚模板里感知不到当前章）
4. **页码计数包含封面**（封面页脚已留白，但计数从封面起算）
5. **不支持横竖版混排的自动检测**；横版需整体配置 `paper.orientation`
6. **公式渲染需 `assets/katex/` 离线包**；未就位时输出占位提示框，绝不静默乱码
7. **Author/Subject/Keywords 依赖 `pdf_meta.py` 后处理**（`run.py` 流水线自动执行；单用 `print_pdf.js` 时只有 Title）

另外：临时产物默认写系统临时目录（`--work-dir` 可指定），不污染项目目录；Linux/macOS 缺中文字体时质检会告警，建议安装思源宋体/黑体。

## 五、技术栈

| 层 | 技术 | 用途 |
|---|---|---|
| 解析转换 | Python 3 标准库 | md → 打印版 HTML、质检、封面留白、PDF 元数据 |
| 渲染引擎 | Node.js + playwright-core | 驱动系统 Edge/Chrome 无头打印 HTML → PDF |
| 数学公式 | KaTeX（离线内置） | `$...$` / `$$...$$` 公式渲染，零网络依赖 |
| 排版控制 | 打印级 CSS（`@page` / paged media） | 页眉页脚、分页、封面、四铁律排版 |

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

## 六、许可证

- 本仓库代码与文档采用 **[MIT](LICENSE)** 许可：**可商用，但须保留版权声明与本许可文本（即保留署名）**。
- 第三方组件（KaTeX 等）的许可信息见 [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md)。

## 七、联系作者

📞 联系方式 / Contact

- **作者 Author**：通信民工（Jerry Xu）
- **哔哩哔哩 Bilibili**：[@通信民工](https://space.bilibili.com/482597398)（UID：482597398）
- **微信公众号 WeChat**：@通信民工（ComDesigner）
- **QQ**：853665220（@qq.com）
- **著作 Book**：《5G网络规划与工程实践》（清华大学出版社出版，当当、京东、淘宝等平台均可购买）

使用中遇到问题、有功能建议或排版需求，欢迎通过上述任一渠道交流。
