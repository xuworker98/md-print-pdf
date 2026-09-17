# print.config.json 配置项逐条说明

> **本文档以 `print.config.json` 实际冻结值为准**。立项需求文档 §5 中的旧默认值（10.4pt/1.74/19pt 等）已被 2026-09-17 冻结规范取代，以本文为准。
> 全部配置项均有内置默认值——**删掉任意项，脚本照常运行**。

---

## paper · 页面

| 项 | 冻结值 | 说明 |
|---|---|---|
| `size` | `"A4"` | A4 / A3 / Letter |
| `orientation` | `"portrait"` | portrait / landscape（横竖混排不自动检测，横版需整体切换） |

## margin · 页边距

| 项 | 冻结值 | 说明 |
|---|---|---|
| `top` | `"18mm"` | |
| `bottom` | `"22mm"` | 比其余边大，给页脚留位 |
| `left` / `right` | `"18mm"` | |

## typography · 版式

| 项 | 冻结值 | 说明 |
|---|---|---|
| `baseFontSize` | `"10.5pt"` | 正文 |
| `lineHeight` | `1.6` | |
| `textAlign` | `"justify"` | justify / left |
| `h1Size` | `"17pt"` | 篇标题 |
| `h2Size` | `"13.5pt"` | 章标题 |
| `h3Size` | `"11.5pt"` | 节标题 |
| `h4Size` | `"10.5pt"` | 目标题 |
| `tableFontSize` | `"9.5pt"` | 表格字号 |
| `captionFontSize` | `"10pt"` | 图注/表注字号 |
| `noteFontSize` | `"9.5pt"` | 图注底衬字号 |
| `codeFontSize` | `"9pt"` | 代码字号 |
| `paraSpacing` | `"2.6mm"` | 段间距 |
| `firstLineIndent` | `"2em"` | **正文首行缩进**；框体/题注/图注自动豁免 |

## accent · 配色（28 色 Token，分五组）

| 项 | 冻结值 | 说明 |
|---|---|---|
| `primary` | `"#14508C"` | 全部标题统一主蓝（2026-09-17 冻结，去绿色） |
| `primaryLight` | `"#B5D4F4"` | H2 底线 |
| `tableHeadBg` | `"#E6F1FB"` | 表头底色 |
| `tableHeadLine` | `"#14508C"` | 表头 1pt 下线 |
| `tableLine` | `"#D8DEE6"` | 表格上下边线 |
| `zebra` / `zebraOn` | `"#FAFBFC"` / `false` | 斑马纹默认关 |
| `quoteBg` / `quoteBar` | `"#F4F8FC"` / `"#14508C"` | 摘要框 |
| `noteBg` / `noteBar` | `"#F7F8FA"` / `"#9AA0A6"` | 图注底衬 |
| `tipBg` / `tipBar` | `"#FDF6E3"` / `"#A16207"` | 提示框 |
| `warnBg` / `warnBar` | `"#FDECEA"` / `"#B3261E"` | 警示框 |
| `listBg` / `listBar` | `"#F1EFE8"` / `"#888780"` | 要点列表框 |
| `codeBg` / `codeBar` | `"#F6F8FA"` / `"#D0D7DE"` | 代码块 |
| `textPrimary` | `"#1A1A1A"` | 正文 |
| `textSecondary` | `"#444444"` | 图注文字 |
| `textMuted` | `"#6B7280"` | 次要文字/页脚 |
| `footerLine` | `"#DCDCDC"` | 页脚横线 |
| `coverRule` | `"#14508C"` | 封面主色线 |
| `ok` | `"#1D9E75"` | ✅ 验证标记（功能色，非标题） |
| `src` | `"#BA7517"` | 🔶 单源已核标记 |
| `alert` | `"#B3261E"` | 数据警示文字 |

## pageBreak · 分页

| 项 | 冻结值 | 说明 |
|---|---|---|
| `chapterOnNewPage` | `true` | 每章另起页；false 时章节连排 |

## headerFooter · 页眉页脚

| 项 | 冻结值 | 可选值 |
|---|---|---|
| `preset` | `"title-pagefooter"` | `none` / `pagenum-only` / `title-pagefooter` / `chapter-pagefooter` |
| `docTitle` | `""`（自动取 md 一级标题） | 页脚显示的文档名 |
| `footerFormat` | `"第 {page} 页 / 共 {total} 页"` | 支持 `{page}` `{total}` |
| `footerLine` | `true` | 是否画页脚横线 |
| `linePlacement` | `"below"` | 横线在文字下方（固定如此实现） |
| `lineColor` | `"#DCDCDC"` | |
| `fontSize` | `"10.5px"` | 页脚模板用 px（引擎限制） |
| `color` | `"#6B7280"` | |

> `chapter-pagefooter` 实际显示文档名：引擎无法在页脚模板感知当前章名（能力边界，见 README）。

## cover · 封面

| 项 | 冻结值 | 说明 |
|---|---|---|
| `enabled` | `true` | |
| `title` / `subtitle` | `""`（自动取一级标题） | |
| `version` | `""` | 如 `V2.0` |
| `date` | `""`（默认当天） | |
| `org` | `""` | 编制单位 |
| `classification` | `"内部材料　·　注意保密"` | 密级行（2026-09-17 用户定稿文案） |
| `template` | `"classic"` | classic（居中+主色线）/ minimal / banner |
| `frontMatter` | `"none"` | |
| `maskFooter` | `true` | 出 PDF 后对封面页做页脚留白（pdf_cover_mask.py） |

## toc · 目录

| 项 | 冻结值 | 说明 |
|---|---|---|
| `enabled` | `true` | |
| `depth` | `2` | 收录 H1+H2；可调 1–3 |
| `linkable` | `true` | 点击跳转 |
| `showPageNumber` | `false` | **固定 false**——引擎页码变量无法注入正文（硬边界） |

## watermark · 水印

| 项 | 冻结值 | 说明 |
|---|---|---|
| `enabled` | `false` | |
| `text` | `""` | 如「内部资料 请勿外传」 |
| `opacity` | `0.08` | 0–1 |
| `fontSize` | `"42pt"` | |
| `rotate` | `-30` | 度（负=逆时针） |
| `color` | `"#000000"` | |

## numbering · 编号

| 项 | 冻结值 | 说明 |
|---|---|---|
| `auto` | `true` | 图表题注自动按章编号（图 1-1 / 表 2-3） |
| `style` | `"chapter"` | 按章编号 |
| `headingAuto` | `false` | 章节序号**手写**（2026-09-16 用户定：工具只校验不生成） |
| `headingCheck` | `true` | 开启序号校验（缺号/跳级告警） |
| `headingScheme` | `["一、","1、","1.1","1.1.1"]` | 章/节/小节/条 四级形态 |
| `figPrefixCn` / `tabPrefixCn` | `"图"` / `"表"` | |
| `figPrefixEn` / `tabPrefixEn` | `"Figure"` / `"Table"` | |

## metadata · PDF 元数据

`title / author / subject / keywords`，默认 `""`；写入 `<meta>` 与 `document.title`，随 `page.pdf()` 落入文档属性。

## bookmarks · 书签

| 项 | 冻结值 | 说明 |
|---|---|---|
| `enabled` | `true` | 生成 PDF 侧边大纲；引擎不支持时自动降级并提示 |

## math · 公式

| 项 | 冻结值 | 说明 |
|---|---|---|
| `mode` | `"auto"` | auto：检测到 katex 资产即 render，否则 placeholder；可强制 `render` / `placeholder` |
| `imageDir` | `""` | 预渲染公式图片目录（备用通道） |

## fonts · 字体

| 项 | 冻结值 |
|---|---|
| `heading` | `"SimHei", "黑体", "Microsoft YaHei", sans-serif` |
| `body` | `"Times New Roman", "SimSun", "宋体", "Microsoft YaHei", serif` |
| `latin` | `"Times New Roman", "SimSun", serif` |
| `mono` | `"Consolas", "Courier New", "SimSun", monospace` |

> 预检逻辑：`simhei.ttf / simsun.ttc / times.ttf` 任一缺失 → 走回退链 + 质检告警，**禁止静默降级**。

## warning · 告警分级

`levels` 控制各检查项的严重级别：`font/image/math/overflow → warn`，`ref → error`，`footnote → info`。
