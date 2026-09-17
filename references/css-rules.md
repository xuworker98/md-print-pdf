# 排版规则与冻结样式规范

> 两部分：① 四条铁律（核心竞争力，不可关闭）；② 2026-09-17 冻结的完整样式规范（配色/字体/要素）。

---

## 一、排版四铁律

「正式文件」与「网页打印」的分水岭，全部**必须实现且不可关闭**：

| # | 规则 | CSS 实现 | 解决什么 |
|---|---|---|---|
| 1 | 图片不被切断 | 图段落 `break-inside: avoid` | 避免图片被拦腰截成两页 |
| 2 | 标题不孤悬页尾 | 标题 `break-after: avoid` + `break-inside: avoid` | 避免标题独留页底、正文翻页才开始 |
| 3 | 跨页表格重复表头 | `thead { display: table-header-group }` | 长表第二页起仍有表头 |
| 4 | 章标题另起页 | H1 `break-before: page`（`pageBreak.chapterOnNewPage` 可关） | 章节分野清晰 |

**附加规则**：
- 表格行 `break-inside: avoid`（单行不拆两页）；
- 题注/图注/框体 `break-inside: avoid`；
- md 表格本体 `break-inside: auto`（长表允许跨页，配合规则 3）；
- `@media print` 内对全部框体（摘要/提示/警示/图注）补 `break-inside: avoid`。

### 层级辨识的双线索原则

主蓝 #14508C 灰阶约 69，浅蓝 #B5D4F4 约 207，黑白打印可辨；但**同色系的层级（如 H2 与 H3 同为 #14508C）灰度差为零**，必须叠「字号 + 装饰线」双重线索：

- H1：17pt + 底部 1.5pt 主色线
- H2：13.5pt + 底部 0.75pt 浅蓝线（#B5D4F4）
- H3：11.5pt（无装饰线，与 H2 差 2pt 字号）
- H4：10.5pt（正文色，仅加粗）

---

## 二、冻结配色 · 蓝色单色体系

> 演进：早期"蓝主＋青绿次"双色方案 → 分析发现主蓝（灰阶 69）与青绿（灰阶 79）仅差 10 阶，黑白打印不可辨 → 2026-09-17 用户确认改为**蓝色单色体系**，全部标题统一 #14508C。

### 五组 28 色 Token（accent.*）

**① 标题与主色**
| Token | 值 | 用途 |
|---|---|---|
| `primary` | `#14508C` | 全部标题、封面主线、表头下线、目录项 |
| `primaryLight` | `#B5D4F4` | H2 底线（黑白打印靠明度差仍可辨） |

**② 表格**
| Token | 值 | 用途 |
|---|---|---|
| `tableHeadBg` | `#E6F1FB` | 表头底色 |
| `tableHeadLine` | `#14508C` | 表头 1pt 下线（列分隔靠 0.5pt 上下表线） |
| `tableLine` | `#D8DEE6` | 表格上下 0.5pt 边线 |
| `zebra` / `zebraOn` | `#FAFBFC` / `false` | 斑马纹默认关闭（行数多时可开） |

**③ 框体四件套**
| Token | 背景 | 左竖线 | 用途 |
|---|---|---|---|
| `quoteBg` / `quoteBar` | `#F4F8FC` | `#14508C` 3pt | 摘要框 |
| `tipBg` / `tipBar` | `#FDF6E3` | `#A16207` 3pt | 提示框 |
| `warnBg` / `warnBar` | `#FDECEA` | `#B3261E` 3pt | 警示框 |
| `noteBg` / `noteBar` | `#F7F8FA` | `#9AA0A6` 2pt | 图注底衬 |
| `listBg` / `listBar` | `#F1EFE8` | `#888780` | 要点列表框 |
| `codeBg` / `codeBar` | `#F6F8FA` | `#D0D7DE` | 代码块 |

**④ 文字灰阶**
| Token | 值 | 用途 |
|---|---|---|
| `textPrimary` | `#1A1A1A` | 正文 |
| `textSecondary` | `#444444` | 图注文字 |
| `textMuted` | `#6B7280` | 页脚文字 |

**⑤ 功能色（保留，非标题色）**
| Token | 值 | 用途 |
|---|---|---|
| `ok` | `#1D9E75` | `✅` 验证标记（绿仅此处使用） |
| `src` | `#BA7517` | `🔶` 单源已核标记 |
| `alert` | `#B3261E` | 数据警示文字 |
| `footerLine` | `#DCDCDC` | 页脚横线 |

---

## 三、冻结字体矩阵

| 元素 | 字体族 | 字重 |
|---|---|---|
| H1–H4 标题 | 黑体 SimHei | 加粗 |
| 表头 th | 宋体 SimSun | 加粗 |
| 正文（含 `**粗体**`） | 宋体 SimSun | 忠于源文件 |
| 表注/图注 | 宋体 SimSun | 不加粗 |
| 英文数字 | Times New Roman（置于宋体前） | 随所在元素 |
| 代码 | Consolas → Courier New → 宋体 | 不加粗 |

回退链：
```css
--font-heading: "SimHei", "黑体", "Microsoft YaHei", sans-serif;
--font-body: "Times New Roman", "SimSun", "宋体", serif;
--font-mono: "Consolas", "Courier New", "SimSun", monospace;
```

启动时预检 `simhei.ttf / simsun.ttc / times.ttf`，缺失走回退链并在质检报告**显式告警，禁止静默降级**。

---

## 四、冻结版式参数（typography.*）

| 项 | 值 | 说明 |
|---|---|---|
| 正文 | 10.5pt / 行距 1.6 / 两端对齐 | |
| **首行缩进** | **2em** | 2026-09-17 用户确认；框体内段落、题注、图注不缩进 |
| H1 / H2 / H3 / H4 | 17 / 13.5 / 11.5 / 10.5 pt | |
| 表格 | 9.5pt | |
| 题注 | 10pt（表注在表上方、图注在图下方，居中） | |
| 图注底衬 | 9.5pt | |
| 代码 | 9pt | |
| 段间距 | 2.6mm | |
| 页边距 | 上 18 / 下 22 / 左 18 / 右 18 mm | 下 22mm 给页脚留位 |

---

## 五、封面与页脚

**封面**（`.cover`）：
- 居中 Flex 版式；`min-height: 250mm` + `page-break-after: always`（坑位 15）
- 密级行（kicker）在最上方：默认 `内部材料　·　注意保密`
- 主标题 26pt 黑体主蓝色 → 46mm × 1.5pt 主色横线 → 副题 → 元数据行（版本/日期/编制/适用范围）
- `cover.maskFooter: true` → 出 PDF 后由 `pdf_cover_mask.py` 增量更新做页脚留白（写视觉白块，文本层仍在，属正常）

**页脚**（四种预设）：
- `none` / `pagenum-only`（第 N 页 / 共 M 页）/ `title-pagefooter`（文档名 ｜ 第 N 页）/ `chapter-pagefooter`（同 title，章名不可注入）
- 实现：单 div + `padding-bottom: 4px` + `border-bottom: 0.5pt solid #DCDCDC`，保证横线在文字**下方**
- 页码变量 `pageNumber/totalPages` 只能在页脚模板用（坑位：无法做真页码目录）

---

## 六、目录

- 由 H1/H2 生成（`toc.depth` 可调 1–3），可点击锚点跳转
- 项样式：主蓝色文字 + 浅灰点线；**无页码**（引擎限制）
- 目录紧随封面，其后 `page-break-after: always` 与正文分隔
