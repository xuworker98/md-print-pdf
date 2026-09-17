#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
md2html.py — 零依赖 Markdown → A4 打印版 HTML 转换器

设计目标
--------
把任意 Markdown 文档转换成"打印级"HTML，供 print_pdf.js（playwright-core + Edge）
渲染为 A4 PDF。全部逻辑只用 Python 标准库，不依赖任何第三方包。

关键约定（对应需求文档 §8 坑位清单）
-----------------------------------
- 坑位1  <img> 独占一行时必须包成 <p class="fig">，否则行内元素会与文字挤一行
- 坑位2  md 表格用 class="md"；内嵌 HTML 表格保持无边框（并排图靠它）
- 坑位3  空单元格输出 &nbsp; 防塌陷
- 坑位4  图片路径用 Path.as_uri() 转 URI（中文自动百分号编码）
- 坑位7  含 HTML 的字符串禁用 % 格式化，一律 f-string / .replace()
- 坑位8  变换链每步后确认下一步匹配目标形态（本文件按"先抽离代码块/公式→再行内→再块级"顺序）
- 坑位12 表格分隔行严格匹配 管道符+横线 的整行形态（正则见 _SEP_RE）

数学公式（对应需求文档 §6.11）
------------------------------
双路方案：
- 检测到 assets/katex/（含 katex.min.js + katex.min.css + fonts/）→ mode=render
  输出 KaTeX auto-render 加载代码，由浏览器端渲染；print_pdf.js 会等待渲染完成标记。
- 未检测到 → mode=placeholder，输出显式占位提示，绝不静默丢弃、绝不输出乱码。

用法
----
    python md2html.py --md input.md --out output.html [--config print.config.json]
                      [--katex-dir assets/katex] [--work-dir <临时目录>]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import html as _html
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

# ---------------------------------------------------------------------------
# 0. 常量与默认配置
# ---------------------------------------------------------------------------

VERSION = "1.1.0"

# 默认配置（对应需求文档 §5 配置项清单，缺项由此补全）
DEFAULT_CONFIG: dict = {
    "paper": {"size": "A4", "orientation": "portrait"},
    "margin": {"top": "14mm", "bottom": "18mm", "left": "15mm", "right": "15mm"},
    "typography": {
        # 2026-09-17 冻结规范：正文 10.5pt / 篇 17pt / 章 13.5pt / 节 11.5pt / 目 10.5pt / 表 9.5pt
        "baseFontSize": "10.5pt",
        "lineHeight": 1.6,
        "textAlign": "justify",
        "h1Size": "17pt",
        "h2Size": "13.5pt",
        "h3Size": "11.5pt",
        "h4Size": "10.5pt",
        "tableFontSize": "9.5pt",
        "captionFontSize": "10pt",
        "noteFontSize": "9.5pt",
        "codeFontSize": "9pt",
        "paraSpacing": "2.6mm",
        "firstLineIndent": "2em",     # 段落首行缩进 2 字符（用户 2026-09-17 指定）
    },
    "accent": {                       # 蓝色单色体系（用户 2026-09-17 拍板：弃灰、弃绿，标题统一 #14508C）
        "primary": "#14508C",         # 主色：H1~H3 标题 / 表头字 / 要点框竖线 / 题注序号 / 封面分隔线
        "primaryLight": "#B5D4F4",    # 章标题下细线
        "tableHeadBg": "#E6F1FB",     # 表头底色（浅蓝）
        "tableHeadLine": "#14508C",   # 表头下边线（1pt 主色）
        "tableLine": "#D8DEE6",       # 表体横线（0.5pt）
        "zebra": "#FAFBFC",           # 斑马纹色
        "zebraOn": False,             # 斑马纹开关（用户 2026-09-17：默认不启用）
        "quoteBg": "#F4F8FC",         # 要点/提要框底
        "quoteBar": "#14508C",
        "noteBg": "#F7F8FA",          # 图注框底
        "noteBar": "#9AA0A6",
        "tipBg": "#FDF6E3",           # 提示框底（琥珀）
        "tipBar": "#A16207",
        "warnBg": "#FDECEA",          # 警示框底（红）
        "warnBar": "#B3261E",
        "listBg": "#F1EFE8",          # 配图清单条底（暖灰）
        "listBar": "#888780",
        "codeBg": "#F6F8FA",          # 代码/结构示意块底
        "codeBar": "#D0D7DE",
        "textPrimary": "#1A1A1A",
        "textSecondary": "#444444",
        "textMuted": "#6B7280",
        "footerLine": "#DCDCDC",      # 页脚横线（在文字下方）
        "footerText": "#6B7280",
        "coverRule": "#14508C",
        "ok": "#1D9E75",              # 功能色：已核标记（禁止用于标题层级）
        "src": "#BA7517",             # 功能色：单源标记
        "alert": "#B3261E",           # 功能色：告警
    },
    "pageBreak": {"chapterOnNewPage": True},
    "headerFooter": {
        "preset": "title-pagefooter",
        "docTitle": "",
        "footerFormat": "第 {page} 页 / 共 {total} 页",
        "footerLine": True,
        "linePlacement": "below",     # below: 横线在页码文字下方（用户 2026-09-16 指定）
        "lineColor": "#DCDCDC",
        "fontSize": "10.5px",
        "color": "#6B7280",
    },
    "cover": {
        "enabled": True,
        "title": "",
        "subtitle": "",
        "version": "",
        "date": "",
        "org": "",
        "classification": "",
        "template": "classic",
        "frontMatter": "none",  # none | roman  封面/目录是否用罗马数字另编页码
    },
    "toc": {"enabled": True, "depth": 2, "linkable": True, "showPageNumber": False},
    "watermark": {"enabled": False, "text": "", "opacity": 0.08, "fontSize": "42pt",
                  "rotate": -30, "color": "#000000"},
    "numbering": {
        "auto": True,
        "style": "chapter",  # simple: 图 1 ｜ chapter: 图 1-1 ｜ en: Figure 1
        "headingAuto": False,   # 章节序号默认由作者手写，本工具只做「跳级/格式」校验
        "headingCheck": True,   # 关闭则不产生章节序号告警
        "headingScheme": ["一、", "1、", "1.1", "1.1.1"],   # 四级序号体系（用户 2026-09-16 指定）
        "figPrefixCn": "图",
        "tabPrefixCn": "表",
        "figPrefixEn": "Figure",
        "tabPrefixEn": "Table",
    },
    "metadata": {"title": "", "author": "", "subject": "", "keywords": ""},
    "bookmarks": {"enabled": True},
    "math": {"mode": "auto", "imageDir": ""},   # auto | placeholder | image | render
    "fonts": {
        "heading": '"SimHei", "黑体", "Microsoft YaHei", "微软雅黑", sans-serif',
        "body": '"SimSun", "宋体", "Microsoft YaHei", "微软雅黑", serif',
        "latin": '"Times New Roman", "SimSun", "宋体", serif',
        "mono": '"Consolas", "Courier New", "SimSun", "宋体", monospace',
    },
    "warning": {"levels": {"font": "warn", "image": "warn", "math": "info",
                           "overflow": "warn", "ref": "error", "footnote": "info"}},
}

# 诊断信息收集（供质检使用）
DIAG: dict = {
    "fonts_warning": [],
    "images": [],        # {src, exists, line}
    "math": [],          # {raw, line, kind}
    "figures": [],       # {kind, title, number, line}
    "refs": [],          # {kind, target, resolved, line}
    "tables": [],        # {index, header_cols, max_data_cols, ragged, line}
    "headings": [],
    "footnotes": [],
    "unclosed_fragment": [],
    "numcheck": [],      # 章节序号校验：{line, level, text, issue, detail}
    "capnum": [],        # 题注序号不一致：{kind, title, written, generated, line}
    "tabcap_orphan": [], # 表注未紧邻表格：{title, line}
}


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并配置，override 覆盖 base；不改动入参。"""
    out = {}
    for k, v in base.items():
        if isinstance(v, dict):
            out[k] = _deep_merge(v, override.get(k, {}) if isinstance(override.get(k), dict) else {})
        else:
            out[k] = override.get(k, v)
    return out


def log(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# 1. 字体可用性预检（需求文档 §4.3 · 功能项 #1）
# ---------------------------------------------------------------------------

# 各平台候选池：键 = 逻辑字体名，值 = 候选文件/族名
FONT_CANDIDATES = {
    "SimHei": {
        "win": ["simhei.ttf"],
        "mac": ["/System/Library/Fonts/STHeiti Medium.ttc"],
        "linux": ["NotoSansCJK-Bold.ttc", "SourceHanSansSC-Bold.otf", "wqy-zenhei.ttc"],
        "fallback_msg": '标题将回退为 Microsoft YaHei / 系统无衬线字体',
        "advice": '安装「黑体 SimHei」或「思源黑体 Source Han Sans」',
    },
    "SimSun": {
        "win": ["simsun.ttc", "simsun.ttf"],
        "mac": ["/System/Library/Fonts/Supplemental/Songti.ttc"],
        "linux": ["NotoSerifCJK-Regular.ttc", "SourceHanSerifSC-Regular.otf", "wqy-zenhei.ttc"],
        "fallback_msg": '正文将回退为 Microsoft YaHei / 系统衬线字体',
        "advice": '安装「宋体 SimSun」或「思源宋体 Source Han Serif」',
    },
    "Times New Roman": {
        "win": ["times.ttf"],
        "mac": ["/System/Library/Fonts/Times.ttc"],
        "linux": ["LiberationSerif-Regular.ttf", "DejaVuSerif.ttf"],
        "fallback_msg": '英文/数字将回退为系统衬线字体',
        "advice": '安装「Times New Roman」或「Liberation Serif」（度量兼容）',
    },
}


def font_dirs() -> dict:
    if sys.platform.startswith("win"):
        return {"key": "win", "dirs": [Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"]}
    if sys.platform == "darwin":
        return {"key": "mac", "dirs": [Path("/System/Library/Fonts"),
                                       Path("/Library/Fonts"),
                                       Path.home() / "Library/Fonts"]}
    return {"key": "linux", "dirs": [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"),
                                     Path.home() / ".fonts", Path.home() / ".local/share/fonts"]}


def precheck_fonts(cfg: dict) -> list:
    """探测关键字体是否存在。返回告警列表（人类可读）。"""
    info = font_dirs()
    platform_key = info["key"]
    # 建立已有字体文件名（小写）与完整路径集合
    present_names, present_paths = set(), []
    for d in info["dirs"]:
        if not d.is_dir():
            continue
        try:
            for p in d.rglob("*"):
                if p.is_file():
                    present_names.add(p.name.lower())
                    present_paths.append(p)
        except (PermissionError, OSError):
            continue

    warnings = []
    for logical, spec in FONT_CANDIDATES.items():
        candidates = spec.get(platform_key, [])
        # 显式配置的字体路径优先（cfg.fonts.* 若为路径形式）
        explicit = cfg.get("fonts", {}).get(f"{logical}_path") or cfg.get("fonts", {}).get(logical)
        if explicit and Path(str(explicit)).is_file():
            continue
        hit = False
        for cand in candidates:
            c = cand.lower()
            if "/" in cand or "\\" in cand:
                if Path(cand).exists():
                    hit = True
                    break
            elif c in present_names:
                hit = True
                break
        if not hit:
            warnings.append(
                f"[字体告警] 未找到 {logical}，{spec['fallback_msg']}。\n"
                f"           原因：目标机器未安装该字体。建议：{spec['advice']}。"
            )
    return warnings


# ---------------------------------------------------------------------------
# 2. 行内元素解析
# ---------------------------------------------------------------------------

# 行内代码先抽取（保护其内部不被后续规则改写）
_MATH_DISPLAY_RE = re.compile(r"\$\$(.+?)\$\$", re.S)
_MATH_INLINE_RE = re.compile(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)")


def esc(text: str) -> str:
    """HTML 转义（保留 & 已转义实体的判断交给调用方）。"""
    return _html.escape(text, quote=False)


def _inline(text: str, ctx: dict) -> str:
    """行内 Markdown → HTML。ctx 携带 line_no 等上下文。"""
    line_no = ctx.get("line_no", 0)

    # 保护：代码片段用占位符替换，最后还原（避免 ** 与 * 生效）
    spans: list = []

    def _stash(payload: str) -> str:
        spans.append(payload)
        return f"\x00SPAN{len(spans) - 1}\x00"

    # 2.1 行内代码 `code` —— 最高优先级
    text = re.sub(r"`([^`\n]+)`", lambda m: _stash(f"<code>{esc(m.group(1))}</code>"), text)

    # 2.2 转义字符 \* \_ \` 等（保护为占位符）
    text = re.sub(r"\\([\\`*_{}\[\]()#+\-.!<>~$|])",
                  lambda m: _stash(esc(m.group(1))), text)

    # 2.3 数学公式：块级 $$...$$ 必须先处理，否则 $$ 会被行内规则拆散
    #     （坑位8：变换链每一步后须确认下一步匹配目标形态）
    def _math_block(m):
        raw = m.group(1).strip()
        DIAG["math"].append({"raw": raw, "line": line_no, "kind": "block"})
        return _stash(f'<span class="math-block" data-math="{_html.escape(raw, quote=True)}">{esc(raw)}</span>')
    text = _MATH_DISPLAY_RE.sub(_math_block, text)

    def _math_inline(m):
        raw = m.group(1).strip()
        DIAG["math"].append({"raw": raw, "line": line_no, "kind": "inline"})
        return _stash(f'<span class="math-inline" data-math="{_html.escape(raw, quote=True)}">{esc(raw)}</span>')
    text = _MATH_INLINE_RE.sub(_math_inline, text)

    # 2.4 图片 ![alt](src "title") —— 注意此时还未转成 <img>（坑位8：顺序）
    def _img(m):
        alt = m.group(1) or ""
        target = m.group(2).strip()
        title = (m.group(3) or "").strip()
        attr = f' title="{_html.escape(title, quote=True)}"' if title else ""
        DIAG["images"].append({"src": target, "line": line_no})
        return _stash(f'<img src="{target}" alt="{_html.escape(alt, quote=True)}"{attr}>')
    text = re.sub(r'!\[([^\]]*)\]\(\s*([^)\s]+)(?:\s+"([^"]*)")?\s*\)', _img, text)

    # 2.5 链接 [text](url "title")
    def _link(m):
        label, url = m.group(1), m.group(2).strip()
        title = (m.group(3) or "").strip()
        attr = f' title="{_html.escape(title, quote=True)}"' if title else ""
        ext = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", url)
        extra = ' target="_blank" rel="noopener"' if ext else ""
        return _stash(f'<a href="{_html.escape(url, quote=True)}"{attr}{extra}>{label}</a>')
    text = re.sub(r'\[([^\]\n]+)\]\(\s*([^)\s]+)(?:\s+"([^"]*)")?\s*\)', _link, text)

    # 2.6 脚注引用 [^id]（降级为文末尾注，§6.12）
    def _fnref(m):
        fid = m.group(1)
        DIAG["footnotes"].append({"id": fid, "line": line_no})
        return _stash(f'<sup class="fnref"><a href="#fn-{_html.escape(fid, quote=True)}" id="fnref-{_html.escape(fid, quote=True)}">{esc(fid)}</a></sup>')
    text = re.sub(r"\[\^([^\]]+)\]", _fnref, text)

    # 2.7 图/表占位符引用 {{fig:xxx}} / {{tab:xxx}}（功能项 #2）
    def _ref(m):
        kind, target = m.group(1), m.group(2).strip()
        DIAG["refs"].append({"kind": kind, "target": target, "resolved": None, "line": line_no})
        # 先输出标记，待编号阶段统一回填
        return _stash(f'<span class="xref" data-kind="{kind}" data-target="{_html.escape(target, quote=True)}">?</span>')
    text = re.sub(r"\{\{(fig|tab)\s*:\s*([^}]+)\}\}", _ref, text)

    # 2.8 删除线、加粗、斜体、高亮（顺序：*** → ** → * → ~~ → ==）
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"~~(.+?)~~", r"<del>\1</del>", text)
    text = re.sub(r"==(.+?)==", r"<mark>\1</mark>", text)

    # 2.9 中文排版微调：全角标点后不留多余空格（不做激进替换，只在明确场景）
    #     ——刻意保持克制，避免破坏源代码块外的正常表达

    # 还原占位符（循环两次以支持嵌套）
    for _ in range(3):
        if "\x00SPAN" not in text:
            break
        text = re.sub(r"\x00SPAN(\d+)\x00", lambda m: spans[int(m.group(1))], text)
    return text


# ---------------------------------------------------------------------------
# 3. 表格解析（含坑位 3、12）
# ---------------------------------------------------------------------------

_SEP_RE = re.compile(r"^\|[\s\-:|]+\|$")


def _is_sep_row(line: str) -> bool:
    """严格匹配表格分隔行 |---|---|（坑位12）。"""
    s = line.strip()
    if not _SEP_RE.match(s):
        return False
    # 至少一个 '-'，防止 | | 误判
    return "-" in s


def _split_row(line: str) -> list:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _aligns_from_sep(sep_line: str) -> list:
    aligns = []
    for cell in _split_row(sep_line):
        cell = cell.strip()
        left, right = cell.startswith(":"), cell.endswith(":")
        if left and right:
            aligns.append("center")
        elif right:
            aligns.append("right")
        elif left:
            aligns.append("left")
        else:
            aligns.append("")
    return aligns


def parse_table(lines: list, start: int, ctx: dict) -> tuple:
    """解析一个 md 表格，返回 (html, next_index, meta)。"""
    header_line = lines[start]
    sep_line = lines[start + 1]
    header = _split_row(header_line)
    aligns = _aligns_from_sep(sep_line)

    rows, i = [], start + 2
    while i < len(lines):
        cur = lines[i]
        if not cur.strip():
            break
        if "|" not in cur:
            break
        if _is_sep_row(cur) and i == start:
            break
        rows.append(_split_row(cur))
        i += 1

    ncols = len(header)
    # 补齐前先记录数据行最大列数，供质检报告说明"差在哪"（补丁 2026-09-17）
    max_data_cols = max([len(r) for r in rows] or [ncols])
    ragged = False
    for r in rows:
        if len(r) != ncols:
            ragged = True
            while len(r) < ncols:
                r.append("")
            del r[ncols:]

    DIAG["tables"].append({
        "index": len(DIAG["tables"]) + 1,
        "header_cols": ncols,
        "max_data_cols": max_data_cols,
        "rows": len(rows),
        "ragged": ragged,
        "line": ctx.get("offset", 0) + start + 1,
    })

    def cell_html(text: str, tag: str, idx: int) -> str:
        content = _inline(text, ctx)
        if not content.strip():
            content = "&nbsp;"          # 坑位3：空单元格防塌陷
        style = f' style="text-align:{aligns[idx]}"' if idx < len(aligns) and aligns[idx] else ""
        return f"<{tag}{style}>{content}</{tag}>"

    out = ['<table class="md">', "<thead>", "<tr>"]
    out += [cell_html(c, "th", k) for k, c in enumerate(header)]
    out += ["</tr>", "</thead>", "<tbody>"]
    if not rows:
        out += ["<tr>"] + [cell_html("", "td", k) for k in range(ncols)] + ["</tr>"]
    for r in rows:
        out.append("<tr>")
        out += [cell_html(c, "td", k) for k, c in enumerate(r)]
        out.append("</tr>")
    out += ["</tbody>", "</table>"]
    return "\n".join(out), i, {"cols": ncols, "rows": len(rows), "ragged": ragged}


# ---------------------------------------------------------------------------
# 4. 块级解析主循环
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_UL_RE = re.compile(r"^(\s*)([-*+])\s+(.*)$")
_OL_RE = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
_HR_RE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
_QUOTE_RE = re.compile(r"^\s{0,3}>\s?(.*)$")
_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})\s*([^\s`]*)\s*$")
_FOOTDEF_RE = re.compile(r"^\[\^([^\]]+)\]:\s*(.*)$")
# 题注标记（2026-09-16 改版）：三种写法均识别，且避免误判正文句
#   ① 图：名称 / 表：名称            —— 推荐，无需写序号（序号由工具生成）
#   ② 图　名称（全角空格分隔）
#   ③ 图 1-1　名称（带旧序号，兼容；开启自动编号时忽略并在不一致时告警）
# 关键：带编号时分隔符必须是全角空格或冒号，普通半角空格的「图 1 给出了…」不判为题注。
_CAP_NUM_SEP = r"([0-9]+(?:[-\u2013\u2014][0-9]+)?)\s*[:\uff1a\u3001]?\u3000"
_CAPTION_FIG_RE = re.compile(
    r"^\s*(?:\*\*)?图\s*(?:(?:" + _CAP_NUM_SEP + r")|\u3000|[:：])\s*(.*?)(?:\*\*)?\s*$")
_CAPTION_TAB_RE = re.compile(
    r"^\s*(?:\*\*)?表\s*(?:(?:" + _CAP_NUM_SEP + r")|\u3000|[:：])\s*(.*?)(?:\*\*)?\s*$")
_HTML_BLOCK_RE = re.compile(r"^\s*<[a-zA-Z!/]")
_CONTAINER_RE = re.compile(r"^\s{0,3}:::\s*([a-zA-Z][a-zA-Z0-9-]*)?\s*$")
_CONTAINER_START_RE = re.compile(r"^\s{0,3}:::\s+([a-zA-Z][a-zA-Z0-9-]*)\s*(.*)$")
_IMG_LINE_RE = re.compile(r"^!\[([^\]]*)\]\(\s*([^)\s]+)(?:\s+\"([^\"]*)\")?\s*\)$")


class SectionIndex:
    """标题计数与锚点分配（供目录 / 书签共用）。

    章级自适应（2026-09-16 V2 修复）
    --------------------------------
    - 文档有 ≥2 个 H1：H1=章、H2=节（multi 模式）
    - 文档只有 0–1 个 H1（H1 是文档名）：H2=章、H3=节（single 模式）
      这是工程文档最常见结构（文档名用 H1，各章用 H2）。
    - 章级以下锚点：sec-c{章}-s{节}[-{子序号}]
    - 文档名级标题锚点固定 sec-doc，不进目录、不占章号。
    """

    def __init__(self, chapter_level: int = 1) -> None:
        self.ch_level = max(1, min(6, chapter_level))
        self.items: list = []   # {level, rel, text, chap, sec, anchor}
        self.chap = 0
        self.sec = 0
        self.sub: dict = {}

    def add(self, level: int, text: str) -> str:
        if level < self.ch_level:
            return "sec-doc"       # 文档名级：不进编号体系
        if level == self.ch_level:
            self.chap += 1
            self.sec = 0
            self.sub = {}
            anchor = f"sec-c{self.chap}"
            rel = 1
        elif level == self.ch_level + 1:
            self.sec += 1
            self.sub = {}
            anchor = f"sec-c{self.chap}-s{self.sec}"
            rel = 2
        else:
            depth = level - self.ch_level          # 3,4,5...
            self.sub[depth] = self.sub.get(depth, 0) + 1
            for k in range(depth + 1, 8):
                self.sub.pop(k, None)
            tail = "-".join(str(self.sub[k]) for k in sorted(self.sub) if k >= 3)
            anchor = f"sec-c{self.chap}-s{self.sec}-{tail}" if tail else f"sec-c{self.chap}-s{self.sec}"
            rel = depth + 1
        self.items.append({"level": level, "rel": rel, "text": text,
                           "chap": self.chap, "sec": self.sec, "anchor": anchor})
        return anchor


def convert(md_text: str, cfg: dict, base_dir: Path, katex_dir: Path | None) -> tuple:
    """把 Markdown 转成打印版 HTML body。返回 (body_html, meta)。"""
    lines = md_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    # 章级自适应：H1 ≥2 → H1 是章；否则 H2 是章（H1 为文档名）
    n_h1 = sum(1 for ln in lines if re.match(r"\s{0,3}#\s+\S", ln))
    chapter_level = 1 if n_h1 >= 2 else 2

    idx = SectionIndex(chapter_level=chapter_level)
    out: list = []
    foot_defs: list = []
    i = 0
    first_h1 = None

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # --- 空行 ---
        if not stripped:
            i += 1
            continue

        # --- 围栏代码块 ---
        m = _FENCE_RE.match(line)
        if m:
            fence, lang = m.group(1), m.group(2)
            buf, j = [], i + 1
            while j < len(lines) and not re.match(r"^\s{0,3}" + re.escape(fence[0]) + r"{3,}\s*$", lines[j]):
                buf.append(lines[j])
                j += 1
            if j >= len(lines):
                DIAG["unclosed_fragment"].append({"kind": "code-fence", "line": i + 1})
            lang_attr = f' data-lang="{_html.escape(lang, quote=True)}"' if lang else ""
            body = esc("\n".join(buf))
            out.append(f'<pre class="code"{lang_attr}><code>{body}</code></pre>')
            i = j + 1
            continue

        # --- 容器语法 ::: figure-row / ::: abstract（方案 A，用户 2026-09-16 拍板） ---
        mc = _CONTAINER_START_RE.match(line)
        if mc:
            kind = mc.group(1)
            arg = (mc.group(2) or "").strip()      # 可选自定义标题，如 ::: abstract 内容提要
            buf, j = [], i + 1
            closed = False
            while j < len(lines):
                if _CONTAINER_RE.match(lines[j]) and not _CONTAINER_START_RE.match(lines[j]):
                    closed = True
                    j += 1
                    break
                buf.append(lines[j])
                j += 1
            if not closed:
                DIAG["unclosed_fragment"].append({"kind": f"container:{kind}", "line": i + 1})
            if kind == "figure-row":
                out.append(render_figure_row(buf, ctx_line=i + 1))
            elif kind == "abstract":
                out.append(render_abstract(buf, title=arg or "本章要点"))
            else:
                # 未知容器类型：原样按段落输出并告警
                log(f"[容器告警] 第 {i + 1} 行的 ::: {kind} 不是受支持的容器类型（figure-row / abstract），按普通段落处理。")
                out.append("<p>" + _inline(" ".join(x.strip() for x in buf if x.strip()), {"line_no": i + 1}) + "</p>")
            i = j
            continue

        # --- 独立 HTML 块（并排图表格等）：原样透传，不加 md 表格样式（坑位2） ---
        if _HTML_BLOCK_RE.match(line):
            buf, j = [], i
            while j < len(lines) and lines[j].strip():
                buf.append(lines[j])
                j += 1
            raw = "\n".join(buf)
            out.append(self_contained_html_block(raw))
            i = j
            continue

        # --- 块级公式（独占一行或多行的 $$...$$） ---
        if stripped.startswith("$$"):
            if stripped.count("$$") >= 2 and len(stripped) > 4:
                raw = stripped.strip("$").strip()
                DIAG["math"].append({"raw": raw, "line": i + 1, "kind": "block"})
                out.append(f'<div class="math-display" data-math="{_html.escape(raw, quote=True)}">'
                           f'{_html.escape(raw)}</div>')
                i += 1
                continue
            # 多行形式
            buf, j = [], i
            inner = stripped[2:]
            while j < len(lines):
                cur = lines[j] if j > i else inner
                if "$$" in (cur if j > i else ""):
                    buf.append((cur if j > i else inner).split("$$")[0])
                    break
                buf.append(cur)
                j += 1
            raw = "\n".join(x for x in buf if x is not None).strip()
            DIAG["math"].append({"raw": raw, "line": i + 1, "kind": "block"})
            out.append(f'<div class="math-display" data-math="{_html.escape(raw, quote=True)}">'
                       f'{_html.escape(raw)}</div>')
            i = j + 1
            continue

        # --- 分隔线 ---
        if _HR_RE.match(line):
            out.append("<hr>")
            i += 1
            continue

        # --- 标题 ---
        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            if level == 1 and first_h1 is None:
                first_h1 = re.sub(r"[*`_]", "", text)
            anchor = idx.add(level, re.sub(r"[*`_]", "", text))
            DIAG["headings"].append({"level": level, "text": re.sub(r"[*`_]", "", text),
                                     "anchor": anchor, "line": i + 1})
            out.append(f'<h{level} id="{anchor}">{_inline(text, {"line_no": i + 1})}</h{level}>')
            i += 1
            continue

        # --- 块引用（图注/表注/依据说明） ---
        m = _QUOTE_RE.match(line)
        if m:
            buf, j = [], i
            while j < len(lines):
                mm = _QUOTE_RE.match(lines[j])
                if not mm:
                    break
                buf.append(mm.group(1))
                j += 1
            inner = _inline(" ".join(x for x in buf if x.strip()), {"line_no": i + 1})
            out.append(f'<blockquote class="note">{inner}</blockquote>')
            i = j
            continue

        # --- 表格 ---
        if "|" in line and i + 1 < len(lines) and _is_sep_row(lines[i + 1]):
            tbl_html, nxt, meta = parse_table(lines, i, {"line_no": i + 1})
            out.append(tbl_html)
            i = nxt
            continue

        # --- 脚注定义 ---
        m = _FOOTDEF_RE.match(line)
        if m:
            fid = m.group(1)
            body_parts = [m.group(2)]
            j = i + 1
            while j < len(lines) and lines[j].startswith((" ", "\t")) and lines[j].strip():
                body_parts.append(lines[j].strip())
                j += 1
            foot_defs.append({"id": fid, "text": " ".join(body_parts)})
            i = j
            continue

        # --- 列表 ---
        if _UL_RE.match(line) or _OL_RE.match(line):
            html, nxt = parse_list(lines, i)
            out.append(html)
            i = nxt
            continue

        # --- 图注 / 表注（独立成行；序号由工具生成，作者可只写名称） ---
        m = _CAPTION_FIG_RE.match(stripped)
        if m and (m.group(2) or "").strip() and len(stripped) < 120:
            num, title = (m.group(1) or "").strip(), m.group(2).strip()
            label = f"图 {num}" if num else "图"
            DIAG["figures"].append({"kind": "fig", "title": title, "number": num,
                                    "line": i + 1, "auto": not num})
            out.append(f'<p class="figcap" data-kind="fig" data-title="{_html.escape(title, quote=True)}" data-num="{num}">'
                       f'<span class="cap-badge">{label}</span><span class="cap-text">{_inline(title, {"line_no": i + 1})}</span></p>')
            i += 1
            continue
        m = _CAPTION_TAB_RE.match(stripped)
        if m and (m.group(2) or "").strip() and len(stripped) < 120:
            num, title = (m.group(1) or "").strip(), m.group(2).strip()
            label = f"表 {num}" if num else "表"
            DIAG["figures"].append({"kind": "tab", "title": title, "number": num,
                                    "line": i + 1, "auto": not num})
            out.append(f'<p class="tabcap" data-kind="tab" data-title="{_html.escape(title, quote=True)}" data-num="{num}">'
                       f'<span class="cap-badge">{label}</span><span class="cap-text">{_inline(title, {"line_no": i + 1})}</span></p>')
            i += 1
            continue

        # --- 普通段落（连续行合并） ---
        buf, j = [stripped], i + 1
        while j < len(lines):
            nxt = lines[j]
            if not nxt.strip():
                break
            if (_HEADING_RE.match(nxt) or _FENCE_RE.match(nxt) or _HR_RE.match(nxt)
                    or _QUOTE_RE.match(nxt) or _UL_RE.match(nxt) or _OL_RE.match(nxt)
                    or _FOOTDEF_RE.match(nxt) or _HTML_BLOCK_RE.match(nxt)
                    or _CONTAINER_RE.match(nxt)
                    or ("|" in nxt and j + 1 < len(lines) and _is_sep_row(lines[j + 1]))):
                break
            buf.append(nxt.strip())
            j += 1

        joined = "".join(buf) if _is_cjk_joined(buf) else " ".join(buf)
        inner = _inline(joined, {"line_no": i + 1})

        # 坑位1：整行仅含一个 <img> → 包成 <p class="fig">
        if re.fullmatch(r"\s*<img\b[^>]*>\s*", inner):
            cls = "fig"
            out.append(f'<p class="{cls}">{inner.strip()}</p>')
        else:
            out.append(f"<p>{inner}</p>")
        i = j

    # --- 脚注列表（文末尾注，§6.12） ---
    if foot_defs:
        items = []
        for fd in foot_defs:
            items.append(
                f'<li id="fn-{_html.escape(fd["id"], quote=True)}">'
                f'<span class="fn-back">[{_html.escape(fd["id"])}]</span> '
                f'{_inline(fd["text"], {"line_no": 0})}</li>')
        out.append('<section class="footnotes"><h4 class="fn-title">注释</h4><ol>'
                   + "".join(items) + "</ol></section>")

    return "\n".join(out), {"first_h1": first_h1, "toc": idx.items,
                            "chapter_level": chapter_level, "footnotes": foot_defs}


def _is_cjk_joined(buf: list) -> bool:
    """软换行拼接策略：中文行末/行首为 CJK 时直接相接，否则补空格。"""
    if len(buf) < 2:
        return False
    prev = buf[0][-1:] or ""
    nxt = buf[1][:1] or ""
    return bool(re.match(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]", prev + nxt))


def parse_list(lines: list, start: int) -> tuple:
    """解析（可嵌套的）有序/无序列表。"""
    items: list = []          # 每项: {"indent":int,"ordered":bool,"text":str,"children":[...]}
    ordereds: list = []
    i = start
    last = None
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            # 空行：若下一行仍是列表项则继续，否则结束
            if i + 1 < len(lines) and (_UL_RE.match(lines[i + 1]) or _OL_RE.match(lines[i + 1])):
                i += 1
                continue
            break
        mu, mo = _UL_RE.match(line), _OL_RE.match(line)
        if not (mu or mo):
            break
        if mu:
            indent, text, ordered = len(mu.group(1)), mu.group(3), False
        else:
            indent, text, ordered = len(mo.group(1)), mo.group(3), True
        node = {"indent": indent, "ordered": ordered, "text": text}
        if last is None or indent <= last["indent"]:
            items.append(node)
        else:
            last.setdefault("children", []).append(node)
        last = node
        ordereds.append(ordered)
        i += 1

    def render(nodes: list, ordered_flag: bool) -> str:
        tag = "ol" if ordered_flag else "ul"
        body = []
        for n in nodes:
            inner = _inline(n["text"], {"line_no": 0})
            if n.get("children"):
                inner += render(n["children"], n["children"][0]["ordered"])
            body.append(f"<li>{inner}</li>")
        return f"<{tag}>" + "".join(body) + f"</{tag}>"

    ordered_flag = items[0]["ordered"] if items else False
    return render(items, ordered_flag), i


def render_figure_row(buf: list, ctx_line: int = 0) -> str:
    """渲染 ::: figure-row 容器（方案 A 并排图语法）。

    容器内每张图片形如 ![子图注](路径)，输出为：
        <div class="figrow-box">
          <figure><img ...><figcaption>子图注</figcaption></figure>
          ...
        </div>
    两图并排、三图并排均由 CSS flex 自动均分；整块防跨页。
    """
    figs = []
    for ln in buf:
        s = ln.strip()
        if not s:
            continue
        m = _IMG_LINE_RE.match(s)
        if m:
            alt, target = m.group(1) or "", m.group(2).strip()
            DIAG["images"].append({"src": target, "line": ctx_line, "source": "container"})
            cap = f"<figcaption>{esc(alt)}</figcaption>" if alt else ""
            figs.append(f'<figure><img src="{target}" alt="{_html.escape(alt, quote=True)}">{cap}</figure>')
        else:
            log(f"[容器告警] figure-row 内第 {ctx_line} 行附近存在非图片内容，已忽略：{s[:40]}")
    if not figs:
        log(f"[容器告警] 第 {ctx_line} 行的 figure-row 容器内没有图片。")
        return ""
    return '<div class="figrow-box">' + "".join(figs) + "</div>"


def render_abstract(buf: list, title: str = "本章要点") -> str:
    """渲染 ::: abstract 容器（B4 要点块）。

    容器内支持普通段落与 - 列表；输出带题头的灰底块。
    题头默认「本章要点」，可在容器行后自定义：::: abstract 内容提要
    """
    items, paras = [], []
    cur_para: list = []
    for ln in buf:
        s = ln.strip()
        if not s:
            if cur_para:
                paras.append(" ".join(cur_para))
                cur_para = []
            continue
        mu = re.match(r"^[-*+]\s+(.*)$", s)
        if mu:
            if cur_para:
                paras.append(" ".join(cur_para))
                cur_para = []
            items.append(mu.group(1))
        else:
            cur_para.append(s)
    if cur_para:
        paras.append(" ".join(cur_para))

    inner = ""
    if items:
        inner += "<ul>" + "".join(f"<li>{_inline(x, {'line_no': 0})}</li>" for x in items) + "</ul>"
    for p in paras:
        inner += f"<p>{_inline(p, {'line_no': 0})}</p>"
    if not inner.strip():
        return ""
    return (f'<div class="abstract-box">'
            f'<div class="abstract-title">{esc(title)}</div>{inner}</div>')


def self_contained_html_block(raw: str) -> str:
    """透传 md 内嵌的 HTML 块，并做安全与打印适配处理。

    - 补 <img> 的相对路径→绝对 URI 由调用方统一处理（此处只做包裹）
    - 坑位2：不加 md 表格 class，保持无边框
    - 为并排图表格加 class="figrow" 便于 CSS 控制间距与避免断页
    """
    txt = raw
    # 标识并排图容器（含 <img> 的 table）
    if re.search(r"<table\b", txt, re.I) and re.search(r"<img\b", txt, re.I):
        txt = re.sub(r"<table\b", '<table class="figrow"', txt, count=1, flags=re.I)
    return f'<div class="htmlblock">\n{txt}\n</div>'


# ---------------------------------------------------------------------------
# 5. 后处理：图片 URI、图表编号、公式策略、水印、封面、目录
# ---------------------------------------------------------------------------

def make_image_uri(src: str, base_dir: Path) -> tuple:
    """把 md 中的图片路径转为绝对 file:/// URI（坑位4）。返回 (uri, exists)。"""
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", src) or src.startswith("data:"):
        return src, True
    p = Path(src)
    if not p.is_absolute():
        p = (base_dir / p).resolve()
    else:
        p = p.resolve()
    exists = p.is_file()
    try:
        return p.as_uri(), exists
    except ValueError:
        return "file:///" + quote(str(p).replace("\\", "/")), exists


def process_math(html_body: str, cfg: dict, katex_dir: Path | None, base_dir: Path) -> tuple:
    """按 math.mode 处理公式：render / image / placeholder。返回 (html, mode_used)。"""
    mode = cfg["math"]["mode"]
    has_katex = bool(katex_dir and (katex_dir / "katex.min.js").is_file()
                     and (katex_dir / "katex.min.css").is_file()
                     and (katex_dir / "fonts").is_dir())

    if mode == "auto":
        mode = "render" if has_katex else "placeholder"

    # --- render 模式：还原为 $...$ / $$...$$ 原文，交给 KaTeX auto-render ---
    if mode == "render" and has_katex:
        dq = chr(34)

        def _unesc(s: str) -> str:
            return _html.unescape(s).replace("&quot;", dq)

        # 行内公式：<span class="math-inline" ...>原文</span>  →  $原文$
        html_body = re.sub(
            r'<span class="math-inline"\s+data-math="([^"]*)"\s*>[^<]*</span>',
            lambda m: "$" + _unesc(m.group(1)) + "$", html_body)
        html_body = re.sub(
            r'<span class="math-inline">([^<]*)</span>',
            lambda m: "$" + _unesc(m.group(1)) + "$", html_body)
        # 块级公式：<div class="math-display" ...>原文</div>  →  div 内包 $$原文$$
        # 注意：主循环输出的 div 内是纯 TeX（无 $），此处补 $$ 供 auto-render 识别；
        #      若已有 $$ 则不再重复添加（防 $$$$ 四美元错误）。
        def _to_display(raw: str) -> str:
            tex = _unesc(raw).strip()
            if tex.startswith("$$"):
                tex = tex[2:]
            if tex.endswith("$$"):
                tex = tex[:-2]
            return '<div class="math-display">$$' + tex.strip() + '$$</div>'

        html_body = re.sub(
            r'<div class="math-display"\s+data-math="([^"]*)"\s*>[^<]*</div>',
            lambda m: _to_display(m.group(1)), html_body)
        html_body = re.sub(
            r'<div class="math-display">([^<]*)</div>',
            lambda m: _to_display(m.group(1)), html_body)
        return html_body, "render"

    # --- image 模式：按出现顺序替换为图片（预留接口） ---
    if mode == "image":
        img_dir = cfg["math"]["imageDir"] or ""
        d = Path(img_dir) if img_dir else None
        if d and d.is_dir():
            seq = sorted([p for p in d.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".svg")])
            counter = {"n": 0}

            def _sub(_m):
                if counter["n"] < len(seq):
                    uri = seq[counter["n"]].as_uri()
                    counter["n"] += 1
                    return f'<img class="math-img" src="{uri}" alt="formula">'
                return '<span class="math-ph">［公式图片缺失］</span>'
            html_body = re.sub(r'<span class="math-(?:inline|block)"[^>]*>.*?</span>', _sub, html_body, flags=re.S)
            html_body = re.sub(r'<div class="math-display"[^>]*>.*?</div>', _sub, html_body, flags=re.S)
            return html_body, f"image({counter['n']}/{len(seq)})"
        log("[公式告警] math.mode=image 但 imageDir 不存在，已回退为 placeholder")

    # --- placeholder 模式：显式提示，绝不静默（§6.11） ---
    def _ph_from_raw(raw: str, block: bool) -> str:
        shown = _html.escape(raw.strip())
        note = '<span class="math-ph-note">（未渲染：数学公式引擎未激活）</span>'
        if block:
            return f'<p class="math-ph-block">［公式］{shown}{note}</p>'
        return f'<span class="math-ph">［公式］{shown}{note}</span>'

    html_body = re.sub(
        r'<span class="math-block"\s+data-math="([^"]*)"\s*>[^<]*</span>',
        lambda m: _ph_from_raw(_html.unescape(m.group(1)), True), html_body)
    html_body = re.sub(
        r'<div class="math-display"\s+data-math="([^"]*)"\s*>[^<]*</div>',
        lambda m: _ph_from_raw(_html.unescape(m.group(1)), True), html_body)
    html_body = re.sub(
        r'<div class="math-display">([^<]*)</div>',
        lambda m: _ph_from_raw(_html.unescape(m.group(1)), True), html_body)
    html_body = re.sub(
        r'<span class="math-inline"\s+data-math="([^"]*)"\s*>[^<]*</span>',
        lambda m: _ph_from_raw(_html.unescape(m.group(1)), False), html_body)
    html_body = re.sub(
        r'<span class="math-inline">([^<]*)</span>',
        lambda m: _ph_from_raw(_html.unescape(m.group(1)), False), html_body)
    # 兜底：残留的 $...$ / $$...$$
    html_body = re.sub(r"\$\$(.+?)\$\$",
                       lambda m: _ph_from_raw(m.group(1), True), html_body, flags=re.S)
    return html_body, "placeholder"


def apply_numbering(html_body: str, cfg: dict, idx_items: list) -> str:
    """图表自动编号 + 交叉引用回填（功能项 #2）。"""
    nb = cfg["numbering"]
    if not nb.get("auto"):
        # 不做自动编号，但仍回填引用（用已有编号）
        pass

    chaps = {}      # anchor -> 章号（保留接口，按章编号时使用）
    for it in idx_items:
        if it["rel"] == 1:
            chaps[it["anchor"]] = it["chap"]

    style = nb.get("style", "simple")
    counters = {"fig": 0, "tab": 0}
    chap_counters = {"fig": {}, "tab": {}}
    mapping = {}    # (kind, title) -> 编号字符串
    seq_by_kind = {"fig": [], "tab": []}

    def _num_for(kind: str, title: str, chap: int | None) -> str:
        """返回带前缀的完整题注序号，如「图 1-1」「表 2-3」。"""
        counters[kind] += 1
        if kind == "fig" and style == "en":
            pref = nb["figPrefixEn"]
        elif kind == "tab" and style == "en":
            pref = nb["tabPrefixEn"]
        else:
            pref = nb["figPrefixCn"] if kind == "fig" else nb["tabPrefixCn"]
        if style == "chapter" and chap:
            chap_counters[kind][chap] = chap_counters[kind].get(chap, 0) + 1
            return f"{pref} {chap}-{chap_counters[kind][chap]}"
        return f"{pref} {counters[kind]}"

    # 需按文档顺序处理：用出现位置排序
    cap_re = re.compile(r'<p class="(figcap|tabcap)" data-kind="(fig|tab)" '
                        r'data-title="([^"]*)" data-num="([^"]*)">'
                        r'<span class="cap-badge">([^<]*)</span><span class="cap-text">(.*?)</span></p>', re.S)
    events = [(m.start(), m, "cap") for m in cap_re.finditer(html_body)]

    # 推断每个图注所属章号：按章级标题（rel==1）锚点出现位置
    head_pos = []
    for it in idx_items:
        if it["rel"] != 1:
            continue
        anchor = it.get("anchor") or ""
        pos = html_body.find(f'id="{anchor}"')
        if pos >= 0:
            head_pos.append((pos, it["chap"], anchor))
    head_pos.sort()

    def chap_at(pos: int) -> int:
        cur = 0
        for p, chap, _a in head_pos:
            if p <= pos:
                cur = chap
            else:
                break
        return cur

    def _cap_line_of(kind: str, title: str):
        for f in DIAG["figures"]:
            if f["kind"] == kind and f["title"] == title:
                return f.get("line")
        return None

    def _cap_sub(m) -> str:
        kind, title = m.group(2), m.group(3)
        old = m.group(4)
        gen = _num_for(kind, title, chap_at(m.start()))
        if nb.get("auto"):
            num = gen
            # 作者写了旧序号但与自动编号不一致时告警（帮作者发现重排后的错位）
            if old and old != num.split()[-1]:
                DIAG["capnum"].append({"kind": kind, "title": title,
                                       "written": old, "generated": num,
                                       "line": _cap_line_of(kind, title)})
        else:
            pref = nb["figPrefixCn"] if kind == "fig" else nb["tabPrefixCn"]
            if kind == "fig" and style == "en":
                pref = nb["figPrefixEn"]
            num = f"{pref} {old}" if old else pref
        cap_text = m.group(6)
        mapping[(kind, title)] = num
        seq_by_kind[kind].append(num)
        return (f'<p class="{m.group(1)}" data-kind="{kind}" data-title="{title}" data-num="{num}">'
                f'<span class="cap-badge">{num}</span><span class="cap-text">{cap_text}</span></p>')

    html_body = cap_re.sub(_cap_sub, html_body)

    # 回填交叉引用
    def _xref(m) -> str:
        kind = m.group(1)
        target = m.group(2)
        hit = mapping.get((kind, target))
        if hit:
            for r in DIAG["refs"]:
                if r["target"] == target and r["kind"] == kind and r["resolved"] is None:
                    r["resolved"] = hit
                    break
            return hit
        for r in DIAG["refs"]:
            if r["target"] == target and r["kind"] == kind and r["resolved"] is None:
                r["resolved"] = False
                break
        return f'［未找到引用：{_html.escape(target)}］'
    html_body = re.sub(r'<span class="xref" data-kind="(fig|tab)" data-target="([^"]*)">\?</span>',
                       _xref, html_body)
    return html_body


def _text_width_em(text: str) -> float:
    """估算单元格文本显示宽度（CJK 记 1em，其余记 0.55em）。"""
    text = _html.unescape(re.sub(r"<[^>]+>", "", text))
    return sum(1.0 if ord(c) > 0x2E80 else 0.55 for c in text)


def fit_table_widths(html_body: str, cfg: dict) -> str:
    """功能项 #7：估宽超过版心的 md 表格自动降字号（下限 7pt），仍超则记 overflow 告警。

    估算模型：各列取最大文本宽（em）求和 + 每格 1.6em 的内外边距，
    与版心宽度（纸宽 − 左右边距）比较；降字号比例 = 版心宽 / 自然宽。
    """
    paper_w = {"A4": 210.0, "A3": 297.0, "Letter": 215.9}.get(
        cfg["paper"].get("size", "A4"), 210.0)
    _num = lambda s: float(re.sub(r"[^0-9.]", "", str(s)) or 0)
    lm = _num(cfg["margin"].get("left", "15mm")) or 15.0
    rm = _num(cfg["margin"].get("right", "15mm")) or 15.0
    content_pt = (paper_w - lm - rm) / 25.4 * 72
    base_pt = _num(cfg["typography"].get("tableFontSize", "9.5pt")) or 9.5
    min_pt = 7.0

    counter = {"n": 0}

    def _fix(m: re.Match) -> str:
        table = m.group(0)
        i = counter["n"]
        counter["n"] += 1
        colw: list[float] = []
        ncol = 0
        for row in re.findall(r"<tr>(.*?)</tr>", table, re.S):
            cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S)
            if not cells:
                continue
            ncol = max(ncol, len(cells))
            while len(colw) < len(cells):
                colw.append(0.0)
            for j, c in enumerate(cells):
                colw[j] = max(colw[j], _text_width_em(c))
        if not ncol:
            return table
        rec = DIAG["tables"][i] if i < len(DIAG["tables"]) else None
        est_em = sum(colw) + ncol * 1.6
        natural_pt = est_em * base_pt
        if natural_pt <= content_pt:
            return table
        new_pt = max(min_pt, base_pt * content_pt / natural_pt)
        if rec is not None:
            rec["fittedFontSize"] = round(new_pt, 1)
            if new_pt <= min_pt + 1e-9 and est_em * min_pt > content_pt:
                rec["overflow"] = True
        return table.replace('<table class="md">',
                             '<table class="md" style="font-size:%.1fpt">' % new_pt, 1)

    return re.sub(r'<table class="md">.*?</table>', _fix, html_body, flags=re.S)


def check_heading_numbering(idx_items: list, cfg: dict) -> None:
    """章节序号校验（2026-09-16 用户定：序号手写，工具只校验不生成）。

    体系（cfg.numbering.headingScheme）：
      rel1 章 → 中文数字 + 、    每章递增（一、二、三…）
      rel2 节 → 阿拉伯数字 + 、   每章内从 1 重新递增
      rel3    → 节号.小节序号     每一节内从 1 递增
      rel4    → 小节号.序号       每一小节内从 1 递增
    检查项：缺号 / 形态与层级不符（跳级、越级）/ 同级不连续 / 编号与上级不符。
    """
    if not cfg["numbering"].get("headingCheck", True):
        return
    CN = "一二三四五六七八九十"
    line_of = {h.get("anchor"): h.get("line") for h in DIAG["headings"]}
    pats = {
        4: re.compile(r"^(\d+)\.(\d+)\.(\d+)(?![\d.])"),
        3: re.compile(r"^(\d+)\.(\d+)(?![\d.])"),
        2: re.compile(r"^(\d+)、"),
        1: re.compile(rf"^([{CN}]+)、"),
    }

    def cn2int(s: str) -> int:
        if not s:
            return -1
        if s == "十":
            return 10
        if s.startswith("十"):
            return 10 + (CN.index(s[1]) + 1) if len(s) > 1 else 10
        if "十" in s:
            a, b = s.split("十", 1)
            head = CN.index(a) + 1
            tail = CN.index(b) + 1 if b else 0
            return head * 10 + tail
        if len(s) == 1 and s in CN:
            return CN.index(s) + 1
        return -1

    def shape_of(text: str):
        for lvl in (4, 3, 2, 1):     # 先长后短，防 1.1.1 被 1 级规则误匹配
            m = pats[lvl].match(text)
            if m:
                return lvl, m.groups()
        return None, ()

    def rep(it: dict, issue: str, detail: str) -> None:
        DIAG["numcheck"].append({
            "line": line_of.get(it.get("anchor")), "level": it["rel"],
            "text": re.sub(r"[*`_]", "", it["text"]), "issue": issue, "detail": detail})

    last_l1 = last_l2 = 0
    last_l3 = (0, 0)
    last_l4 = (0, 0, 0)
    for it in idx_items:
        rel = it["rel"]
        if rel > 4:
            continue
        text = re.sub(r"[*`_]", "", it["text"]).strip()
        shape, groups = shape_of(text)
        if shape is None:
            rep(it, "缺号", "标题未以序号开头（体系示例：一、/1、/1.1/1.1.1）")
            continue
        if shape != rel:
            ladder = {1: "一、", 2: "1、", 3: "1.1", 4: "1.1.1"}
            rep(it, "跳级或越级",
                f"该标题为第 {rel} 级，序号形态却属第 {shape} 级；第 {rel} 级应为「{ladder[rel]}」式")
            continue
        if rel == 1:
            n = cn2int(groups[0])
            if n < 0:
                rep(it, "序号异常", f"章号「{groups[0]}」超出可识别范围")
            elif n != last_l1 + 1:
                rep(it, "同级不连续", f"章号应从 1 起连续递增，上一章为 {last_l1}，此处为 {n}")
            if n > 0:
                last_l1 = n
            last_l2 = 0
            last_l3 = (0, 0)
            last_l4 = (0, 0, 0)
        elif rel == 2:
            n = int(groups[0])
            if n != last_l2 + 1:
                rep(it, "同级不连续", f"每章节号应从 1 重新递增，此处为 {n}（上一节为 {last_l2}）")
            last_l2 = n
            last_l3 = (0, 0)
            last_l4 = (0, 0, 0)
        elif rel == 3:
            sec_no, sub_no = int(groups[0]), int(groups[1])
            if sec_no != last_l2:
                rep(it, "编号与上级不符", f"第一段 {sec_no} 应等于所属节号 {last_l2}")
            elif sub_no != last_l3[1] + 1:
                rep(it, "同级不连续", f"小节序号应为 {last_l3[1] + 1}，此处为 {sub_no}")
            last_l3 = (sec_no, sub_no)
            last_l4 = (0, 0, 0)
        else:
            a, b, c = int(groups[0]), int(groups[1]), int(groups[2])
            if (a, b) != last_l3:
                rep(it, "编号与上级不符",
                    f"前两段 {a}.{b} 应等于所属小节 {last_l3[0]}.{last_l3[1]}")
            elif c != last_l4[2] + 1:
                rep(it, "同级不连续", f"序号应为 {last_l4[2] + 1}，此处为 {c}")
            last_l4 = (a, b, c)


def check_tabcap_adjacency(html_body: str) -> None:
    """表注（表名）必须在表格上方紧邻——2026-09-16 用户定。

    表名位置惯例：表名在表上方、图名在图下方。本函数只做提示，不改动排版。
    """
    line_of = {}
    for f in DIAG["figures"]:
        if f["kind"] == "tab":
            line_of[f["title"]] = f.get("line")
    for m in re.finditer(r'<p class="tabcap"[^>]*data-title="([^"]*)"[^>]*>.*?</p>',
                         html_body, re.S):
        title = m.group(1)
        if not html_body[m.end():].lstrip().startswith("<table"):
            DIAG["tabcap_orphan"].append({"title": title, "line": line_of.get(title)})


def build_cover(cfg: dict, meta: dict) -> str:
    """生成封面（功能项 #12）。"""
    c = cfg["cover"]
    if not c.get("enabled"):
        return ""
    title = c.get("title") or meta.get("first_h1") or "（未命名文档）"
    date = c.get("date") or _dt.date.today().strftime("%Y年%m月%d日")
    tpl = c.get("template", "classic")
    cls = f"cover cover--{tpl}"

    rows = []
    if c.get("classification"):
        rows.append(f'<div class="cover-classification">{esc(c["classification"])}</div>')

    center = [f'<h1 class="cover-title">{esc(title)}</h1>']
    if c.get("subtitle"):
        center.append(f'<div class="cover-subtitle">{esc(c["subtitle"])}</div>')

    meta_rows = []
    if c.get("version"):
        meta_rows.append(f'<div class="cover-meta-row"><span class="k">版本</span><span class="v">{esc(c["version"])}</span></div>')
    meta_rows.append(f'<div class="cover-meta-row"><span class="k">日期</span><span class="v">{esc(date)}</span></div>')
    if c.get("org"):
        meta_rows.append(f'<div class="cover-meta-row"><span class="k">编制单位</span><span class="v">{esc(c["org"])}</span></div>')

    return (
        f'<section class="{cls}">'
        f'{"".join(rows)}'
        f'<div class="cover-center">{"".join(center)}</div>'
        f'<div class="cover-meta">{"".join(meta_rows)}</div>'
        f'</section>'
    )


def build_toc(cfg: dict, idx_items: list) -> str:
    """生成目录（功能项 #13/#14，A 方案：无页码 + 可点击）。

    收录范围按**逻辑级别**（rel）：1=章、2=节。
    toc.depth = 收录到的逻辑级别（默认 2 → 章+节）。
    toc.fromLevel = 起始逻辑级别（默认 1）。

    2026-09-16 用户意见：目录条目不显示编号（标题文字自带序号，避免重复），
    并删除“本目录不含页码”说明行，仅保留点击跳转。
    """
    t = cfg["toc"]
    if not t.get("enabled") or not idx_items:
        return ""
    depth = int(t.get("depth", 2))
    from_level = int(t.get("fromLevel", 1))
    entries = [it for it in idx_items if from_level <= it["rel"] <= depth]
    if not entries:
        return ""
    rows = []
    for it in entries:
        anchor = it["anchor"]
        rel = it["rel"]
        text = it["text"]
        if t.get("linkable", True):
            rows.append(f'<li class="toc-l{rel}"><a href="#{anchor}">'
                        f'<span class="toc-text">{esc(text)}</span></a></li>')
        else:
            rows.append(f'<li class="toc-l{rel}"><span class="toc-text">{esc(text)}</span></li>')
    return (f'<section class="toc"><h2 class="toc-title">目　录</h2>'
            f'<ul class="toc-list">{"".join(rows)}</ul></section>')


def build_watermark(cfg: dict) -> str:
    """生成水印层（功能项 #10）。"""
    w = cfg["watermark"]
    if not w.get("enabled") or not w.get("text"):
        return ""
    tiles = "".join('<span class="wm-tile">%s</span>' % esc(w["text"]) for _ in range(12))
    return (f'<div class="watermark" style="opacity:{w.get("opacity", 0.08)};'
            f'-webkit-transform:rotate({w.get("rotate", -30)}deg);'
            f'transform:rotate({w.get("rotate", -30)}deg);'
            f'font-size:{w.get("fontSize", "42pt")};color:{w.get("color", "#000")};">'
            f'{tiles}</div>')


# ---------------------------------------------------------------------------
# 6. 样式表（§7 排版规则 + §4 字体矩阵）
# ---------------------------------------------------------------------------

def build_css(cfg: dict, katex_dir: Path | None) -> str:
    ty = cfg["typography"]
    mg = cfg["margin"]
    ft = cfg["fonts"]
    ac = cfg.get("accent", {})
    ACC      = ac.get("primary", "#14508C")        # 主色（蓝色单色体系，2026-09-17 冻结）
    ACC_LT   = ac.get("primaryLight", "#B5D4F4")
    THBG     = ac.get("tableHeadBg", "#E6F1FB")
    THLN     = ac.get("tableHeadLine", "#14508C")
    TBLN     = ac.get("tableLine", "#D8DEE6")
    ZEBRA    = ac.get("zebra", "#FAFBFC")
    ZEBRA_ON = bool(ac.get("zebraOn", False))
    QBG      = ac.get("quoteBg", "#F4F8FC")
    QBAR     = ac.get("quoteBar", "#14508C")
    NBG      = ac.get("noteBg", "#F7F8FA")
    NBAR     = ac.get("noteBar", "#9AA0A6")
    TPBG     = ac.get("tipBg", "#FDF6E3")
    TPBAR    = ac.get("tipBar", "#A16207")
    WNBG     = ac.get("warnBg", "#FDECEA")
    WNBAR    = ac.get("warnBar", "#B3261E")
    LSBG     = ac.get("listBg", "#F1EFE8")
    LSBAR    = ac.get("listBar", "#888780")
    CDBG     = ac.get("codeBg", "#F6F8FA")
    CDBAR    = ac.get("codeBar", "#D0D7DE")
    TXT      = ac.get("textPrimary", "#1A1A1A")
    TXT2     = ac.get("textSecondary", "#444444")
    TXT3     = ac.get("textMuted", "#6B7280")
    ALERT    = ac.get("alert", "#B3261E")
    nb_break = cfg["pageBreak"]["chapterOnNewPage"]
    tbl_fs   = ty["tableFontSize"]
    cap_fs   = ty.get("captionFontSize", "10pt")
    note_fs  = ty.get("noteFontSize", "9.5pt")
    code_fs  = ty.get("codeFontSize", "9pt")
    para_sp  = ty.get("paraSpacing", "2.6mm")
    indent   = ty.get("firstLineIndent", "2em")

    h1_break = "break-before: page; page-break-before: always;" if nb_break else ""
    # single-h1 模式下 H1 是文档名、H2 才是章，故章级分页规则需挂在 H2 上（目录标题除外）
    h2_break = ("body.layout-single-h1 h2:not(.toc-title) {"
                " break-before: page; page-break-before: always; }") if nb_break else ""
    zebra_rule = (f"table.md tbody tr:nth-child(even) td {{ background: {ZEBRA}; }}"
                  if ZEBRA_ON else "/* 斑马纹未启用（accent.zebraOn=false） */")

    return f"""
/* ============================================================
   md-print-pdf · A4 打印样式表（自动生成）
   配色体系：蓝色单色（主色 {ACC}）—— 标题/表头字/竖线/序号同色，
   层级靠「字号 + 装饰线」区分（黑白打印下颜色不可辨，故不单靠颜色）。
   功能色（已核/单源/告警）独立于层级色，禁止用于标题。
   生效日期：2026-09-17（V1.1 冻结规范）
   ============================================================ */

@page {{
  size: {cfg['paper']['size']} {cfg['paper']['orientation']};
  margin: {mg['top']} {mg['right']} {mg['bottom']} {mg['left']};
}}

/* ---------- 基础 ---------- */
* {{ box-sizing: border-box; }}

html, body {{
  margin: 0;
  padding: 0;
  background: #ffffff;
  color: {TXT};
  font-family: {ft['body']};
  font-size: {ty['baseFontSize']};
  line-height: {ty['lineHeight']};
  text-align: {ty['textAlign']};
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
  font-variant-numeric: lining-nums tabular-nums;
}}

/* ---------- 标题（黑体加粗 · 全蓝色体系） ---------- */
h1, h2, h3, h4, h5, h6 {{
  font-family: {ft['heading']};
  font-weight: bold;
  color: {ACC};
  text-align: left;
  break-after: avoid;          /* §7-2 标题不孤悬页尾 */
  page-break-after: avoid;
  break-inside: avoid;
  page-break-inside: avoid;
}}

/* 章级大编号已按用户意见取消（2026-09-16）：序号由作者手写（一、/1、/1.1/1.1.1） */
h1 {{
  font-size: {ty['h1Size']}; line-height: 1.45; margin: 0 0 5mm 0;
  padding-bottom: 2.2mm; border-bottom: 1.5pt solid {ACC}; {h1_break}
}}

h2 {{
  font-size: {ty['h2Size']}; margin: 7mm 0 3.5mm 0;
  padding-bottom: 1.6mm; border-bottom: 0.75pt solid {ACC_LT};
}}
{h2_break}

/* H3 与 H2 同色，靠字号与「无装饰线」区分（2026-09-17 去绿） */
h3 {{ font-size: {ty['h3Size']}; margin: 5mm 0 2.5mm 0; }}
h4 {{ font-size: {ty['h4Size']}; color: {TXT}; margin: 3.5mm 0 2mm 0; }}

/* ---------- 正文（首行缩进 2 字符，2026-09-17 指定） ---------- */
p {{
  margin: 0 0 {para_sp} 0;
  text-indent: {indent};
  orphans: 2;
  widows: 2;
}}

strong {{ font-weight: bold; }}   /* 忠于 md 源文件（§4.1） */
em {{ font-style: italic; }}
del {{ color: #888; }}
mark {{ background: #fff3a3; padding: 0 1px; }}

a {{ color: {ACC}; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}

code {{
  font-family: {ft['mono']};
  font-size: {code_fs};
  background: {CDBG};
  padding: 0.6mm 1mm;
  border-radius: 1pt;
}}

/* ---------- 代码块 / 结构示意 ---------- */
pre.code {{
  font-family: {ft['mono']};
  font-size: {code_fs};
  line-height: 1.5;
  background: {CDBG};
  border-left: 2pt solid {CDBAR};
  padding: 2.4mm 3mm;
  margin: 3mm 0;
  white-space: pre-wrap;
  word-break: break-all;
  overflow-wrap: anywhere;
  position: relative;
  break-inside: auto;
  page-break-inside: auto;
}}
pre.code::before {{
  content: attr(data-lang);
  position: absolute;
  top: 1.4mm; right: 2.4mm;
  font-family: {ft['mono']};
  font-size: 7.5pt;
  color: {TXT3};
  letter-spacing: 0.3pt;
}}
pre.code code {{ background: none; padding: 0; font-size: inherit; }}

/* ---------- 列表（主色符号） ---------- */
ul, ol {{ margin: 1.6mm 0 3mm 0; padding-left: 7mm; }}
li {{ margin: 0.8mm 0; }}
li > ul, li > ol {{ margin: 0.8mm 0 0.8mm 0; }}
li::marker {{ color: {ACC}; }}
li p {{ text-indent: 0; }}

/* ---------- 分隔线 ---------- */
hr {{ border: none; border-top: 0.5pt solid {TBLN}; margin: 4mm 0; }}

/* ---------- 表格（表头浅蓝底 + 主色字 + 1pt 主色下边线；§7-3 跨页重复表头） ---------- */
table.md {{
  width: 100%;
  border-collapse: collapse;
  margin: 1.6mm 0 4mm 0;
  font-size: {tbl_fs};
  line-height: 1.5;
  break-inside: auto;
  border-top: 0.5pt solid {TBLN};
  border-bottom: 0.5pt solid {TBLN};
}}
table.md thead {{ display: table-header-group; }}   /* §7-3 关键 */
table.md tr {{
  break-inside: avoid;
  page-break-inside: avoid;
}}
table.md th {{
  font-family: {ft['body']};     /* 表头宋体加粗（§4.1） */
  font-weight: bold;
  color: {THLN};
  background: {THBG};
  border-bottom: 1pt solid {THLN};
  padding: 1.5mm 1.6mm;
  text-align: left;
  vertical-align: middle;
  word-break: break-word;
}}
table.md td {{
  color: {TXT};
  border-bottom: 0.5pt solid {TBLN};
  padding: 1.4mm 1.6mm;
  vertical-align: top;
  word-break: break-word;
  overflow-wrap: anywhere;
  text-indent: 0;
}}
table.md td:first-child, table.md th:first-child {{ padding-left: 2.2mm; }}
table.md tbody tr:last-child td {{ border-bottom: none; }}
{zebra_rule}

/* 并排图容器（::: figure-row 容器语法） */
.figrow-box {{
  display: flex;
  gap: 4mm;
  margin: 3.5mm 0 1.5mm 0;
  break-inside: avoid;
  page-break-inside: avoid;
}}
.figrow-box figure {{
  flex: 1 1 0;
  margin: 0;
  min-width: 0;
}}
.figrow-box img {{ width: 100%; height: auto; display: block; }}
.figrow-box figcaption {{
  font-family: {ft['body']};
  font-size: {note_fs};
  color: {TXT};
  text-align: center;
  margin-top: 1.2mm;
  text-indent: 0;
  break-inside: avoid;
}}

/* 兼容旧式 md 内嵌 HTML 并排表格（无边框，坑位2） */
table.figrow {{
  width: 100%;
  border: none;
  border-collapse: collapse;
  margin: 3mm 0;
  break-inside: avoid;
  page-break-inside: avoid;
}}
table.figrow td {{
  border: none;
  padding: 0 2mm;
  text-align: center;
  vertical-align: bottom;
  width: 50%;
}}
table.figrow img {{ width: 100%; height: auto; }}

/* ---------- 图片（§7-1 图片不被切断；功能项 #6） ---------- */
img {{
  max-width: 100%;
  height: auto;
  display: block;
  margin: 0 auto;
}}
p.fig {{
  text-align: center;
  margin: 3.5mm 0 1.5mm 0;
  text-indent: 0;
  break-inside: avoid;           /* §7-1 关键 */
  page-break-inside: avoid;
}}
p.fig img {{ max-width: 100%; }}

/* ---------- 图题 / 表题（纯文本式：序号加粗 + 名称常规；题题同色正文） ---------- */
p.figcap, p.tabcap {{
  font-family: {ft['body']};
  font-weight: normal;
  font-size: {cap_fs};
  color: {TXT};
  text-align: center;
  text-indent: 0;
  margin: 1.4mm 0 4mm 0;
  break-inside: avoid;
  page-break-inside: avoid;
}}
p.tabcap {{ margin: 4mm 0 1.4mm 0; break-after: avoid; page-break-after: avoid; }}
.cap-badge {{
  font-family: {ft['body']};
  font-weight: bold;
  color: {TXT};
  margin-right: 0.45em;
}}
.cap-text {{ }}

/* ---------- 引用块（依据说明 / 普通引用） ---------- */
blockquote.note {{
  background: {NBG};
  border-left: 2pt solid {NBAR};
  padding: 2.2mm 3mm;
  margin: 3mm 0;
  font-size: {note_fs};
  color: {TXT2};
  break-inside: avoid;
  page-break-inside: avoid;
}}
blockquote.note p {{ margin: 0; text-indent: 0; }}

/* ---------- 图注块（用户 2026-09-17 新增，借鉴机器人 V2.0 的 37 处图注体系） ---------- */
.fignote {{
  background: {NBG};
  border-left: 2pt solid {NBAR};
  padding: 2mm 3mm;
  margin: 2mm 0 4mm 0;
  font-size: {note_fs};
  color: {TXT2};
  text-indent: 0;
  break-inside: avoid;
  page-break-inside: avoid;
}}
.fignote p {{ margin: 0; text-indent: 0; }}

/* ---------- 要点框（::: abstract） ---------- */
.abstract-box {{
  background: {QBG};
  border-left: 3pt solid {QBAR};
  padding: 2.6mm 3.2mm;
  margin: 3mm 0 4mm 0;
  break-inside: avoid;
  page-break-inside: avoid;
}}
.abstract-title {{
  font-family: {ft['heading']};
  font-weight: bold;
  font-size: {note_fs};
  color: {QBAR};
  margin: 0 0 1.4mm 0;
}}
.abstract-box p {{ margin: 0 0 1.2mm 0; font-size: {note_fs}; text-indent: 0; }}
.abstract-box ul {{ margin: 0; padding-left: 5.5mm; }}
.abstract-box li {{ margin: 0.6mm 0; font-size: {note_fs}; }}
.abstract-box li::marker {{ color: {QBAR}; }}
.abstract-box > :last-child {{ margin-bottom: 0; }}

/* ---------- 提示框（::: tip） ---------- */
.box-tip {{
  background: {TPBG};
  border-left: 3pt solid {TPBAR};
  padding: 2.4mm 3.2mm;
  margin: 3mm 0;
  font-size: {note_fs};
  color: {TXT};
  break-inside: avoid;
  page-break-inside: avoid;
}}
.box-tip p {{ margin: 0 0 1.2mm 0; text-indent: 0; }}
.box-tip > :last-child {{ margin-bottom: 0; }}

/* ---------- 警示框（::: warn） ---------- */
.box-warn {{
  background: {WNBG};
  border-left: 3pt solid {WNBAR};
  padding: 2.4mm 3.2mm;
  margin: 3mm 0;
  font-size: {note_fs};
  color: {TXT};
  break-inside: avoid;
  page-break-inside: avoid;
}}
.box-warn p {{ margin: 0 0 1.2mm 0; text-indent: 0; }}
.box-warn > :last-child {{ margin-bottom: 0; }}

/* ---------- 配图清单条（::: figlist） ---------- */
.box-listbar {{
  background: {LSBG};
  border-left: 3pt solid {LSBAR};
  padding: 2mm 3.2mm;
  margin: 3mm 0;
  font-size: {note_fs};
  color: {TXT2};
  break-inside: avoid;
  page-break-inside: avoid;
}}
.box-listbar p {{ margin: 0; text-indent: 0; }}

/* ---------- 状态标记（功能色，禁止用于标题层级） ---------- */
.ok {{ color: {ac.get('ok', '#1D9E75')}; }}
.src {{ color: {ac.get('src', '#BA7517')}; }}
.warn {{ color: {ALERT}; }}

/* ---------- 公式 ---------- */
.math-inline {{ white-space: nowrap; }}
.math-display {{
  text-align: center;
  margin: 3mm 0;
  break-inside: avoid;
}}
.math-ph {{
  background: {TPBG};
  border: 0.5pt dashed {TPBAR};
  padding: 0 1mm;
  color: {TPBAR};
  white-space: normal;
}}
.math-ph-block {{
  text-align: center;
  background: {TPBG};
  border: 0.5pt dashed {TPBAR};
  padding: 2mm;
  margin: 3mm 0;
  color: {TPBAR};
}}
.math-ph-note {{ font-size: 8.4pt; color: {TPBAR}; margin-left: 1.5mm; }}
img.math-img {{ max-width: 92%; margin: 3mm auto; }}

/* KaTeX 渲染块 */
.katex-display {{ margin: 3mm 0; break-inside: avoid; }}
.katex {{ font-size: 1.06em; }}

/* ---------- 脚注（降级为文末尾注，§6.12） ---------- */
sup.fnref {{ font-size: 0.72em; vertical-align: super; }}
sup.fnref a {{ color: {ACC}; text-decoration: none; }}
section.footnotes {{
  margin-top: 8mm;
  padding-top: 3mm;
  border-top: 0.5pt solid {TBLN};
  font-size: 8.8pt;
  color: {TXT2};
  break-inside: avoid;
}}
section.footnotes h4.fn-title {{
  font-size: 10pt;
  color: {ACC};
  margin: 0 0 2mm 0;
  border: none;
  padding: 0;
}}
section.footnotes ol {{ padding-left: 6mm; margin: 0; }}
section.footnotes li {{ margin: 1mm 0; }}
span.fn-back {{ font-weight: bold; }}

/* ---------- 封面（无外框、无页眉页脚；2026-09-16 / 09-17 定稿） ---------- */
section.cover {{
  height: 250mm;
  break-after: page;
  page-break-after: always;
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  padding: 10mm 0;
}}
.cover-classification {{
  font-family: {ft['heading']};
  font-size: 10.5pt;
  color: {TXT3};
  letter-spacing: 0.15em;
  margin-bottom: 20mm;
}}
.cover-center {{ text-align: center; }}
.cover-title {{
  font-family: {ft['heading']};
  font-weight: bold;
  font-size: 24pt;
  color: {ACC};
  line-height: 1.35;
  margin: 0;
  border: none;
  padding: 0;
  break-before: auto;
  page-break-before: auto;
  counter-increment: none;
}}
.cover-rule {{
  width: 46mm; height: 0;
  border-top: 1.5pt solid {ACC};
  margin: 9mm auto;
}}
.cover-subtitle {{
  font-family: {ft['heading']};
  font-size: 13pt;
  color: {TXT2};
  margin-top: 2mm;
}}
.cover-meta {{
  font-family: {ft['body']};
  font-size: 10.5pt;
  color: {TXT2};
  margin-top: 30mm;
  text-align: center;
  line-height: 2;
}}
.cover-meta-row {{ padding: 1.2mm 0; }}
.cover-meta-row .k {{ color: {TXT3}; }}
.cover-meta-row .v {{ font-weight: bold; color: {TXT}; }}

/* classic：标题上下细线（无外框） */
.cover--classic .cover-title {{
  border-top: none;
  border-bottom: none;
  padding: 0;
}}

/* minimal：左对齐 + 左上小方块 */
.cover--minimal {{ align-items: flex-start; text-align: left; padding-left: 6mm; }}
.cover--minimal::before {{
  content: "";
  position: absolute; top: 0; left: 0;
  width: 9mm; height: 9mm;
  background: {ACC};
}}
.cover--minimal .cover-center {{ text-align: left; }}
.cover--minimal .cover-title {{
  font-size: 22pt;
  border-bottom: 1.6pt solid {ACC};
  padding-bottom: 4mm;
}}

/* banner：顶部主色横块 */
.cover--banner {{ padding-top: 30mm; }}
.cover--banner::before {{
  content: "";
  position: absolute; top: 0; left: 0; right: 0; height: 16mm;
  background: {ACC};
}}
.cover--banner .cover-title {{ font-size: 27pt; letter-spacing: 1pt; }}

/* ---------- 目录（无编号、无页码，条目可点击跳转） ---------- */
section.toc {{
  break-after: page;
  page-break-after: always;
}}
h2.toc-title {{
  font-family: {ft['heading']};
  font-size: {ty['h2Size']};
  color: {ACC};
  text-align: left;
  margin: 0 0 8mm 0;
  padding-bottom: 1.6mm;
  border: none;
  border-bottom: 0.75pt solid {ACC_LT};
}}
ul.toc-list {{ list-style: none; padding: 0; margin: 0; }}
ul.toc-list li {{ margin: 2.2mm 0; line-height: 1.6; }}
ul.toc-list li::marker {{ content: none; }}
li.toc-l1 {{ font-family: {ft['heading']}; font-weight: bold; font-size: 11.6pt; margin-top: 3.6mm; }}
li.toc-l2 {{ padding-left: 7mm; font-size: 10.5pt; }}
li.toc-l3 {{ padding-left: 14mm; font-size: 10pt; }}
li.toc-l4 {{ padding-left: 21mm; font-size: 9.6pt; }}
ul.toc-list a {{
  color: {ACC};
  display: block;
  text-decoration: none;
}}
ul.toc-list a .toc-text {{ }}

/* ---------- 水印（功能项 #10） ---------- */
.watermark {{
  position: fixed;
  top: -12%;
  left: -12%;
  width: 124%;
  height: 124%;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  z-index: 9999;
  font-family: {ft['heading']};
  font-weight: bold;
  line-height: 3.2;
  letter-spacing: 4mm;
  white-space: nowrap;
}}
.wm-tile {{ display: inline-block; padding: 0 14mm; }}

/* ---------- 打印强制规则 ---------- */
@media print {{
  body {{ background: #fff; }}
  h1, h2, h3, h4 {{ break-after: avoid; page-break-after: avoid; }}
  table.md thead {{ display: table-header-group; }}
  p.fig, p.tabcap, p.figcap, .figrow-box, blockquote.note, .fignote,
  .abstract-box, .box-tip, .box-warn, .box-listbar {{
    break-inside: avoid; page-break-inside: avoid;
  }}
}}
"""


# ---------------------------------------------------------------------------
# 7. 组装完整 HTML
# ---------------------------------------------------------------------------

def build_html(cfg: dict, body: str, cover: str, toc: str, watermark: str,
               meta: dict, katex_dir: Path | None, math_mode: str) -> str:
    css = build_css(cfg, katex_dir)
    md = cfg["metadata"]
    title = md.get("title") or meta.get("first_h1") or "文档"
    # chapter_level>=2 意味着 H1 是文档名（single 模式）；=1 则 H1 即章（multi 模式）
    layout_cls = "layout-single-h1" if meta.get("chapter_level", 1) >= 2 else "layout-multi-h1"
    fnt = cfg["headerFooter"]

    katex_tags = ""
    if math_mode == "render" and katex_dir:
        js_uri = (katex_dir / "katex.min.js").as_uri()
        css_uri = (katex_dir / "katex.min.css").as_uri()
        # auto-render 是 *扩展*，不在 katex.min.js 内；缺它则 renderMathInElement 未定义
        ar_path = katex_dir / "contrib" / "auto-render.min.js"
        ar_tag = ""
        if ar_path.is_file():
            ar_tag = f'<script src="{ar_path.as_uri()}"></script>'
        else:
            log("[公式告警] 未找到 contrib/auto-render.min.js，公式将无法渲染。")
            log("           该文件是 KaTeX 的 auto-render 扩展，需与 katex.min.js 一同放入 assets/katex/contrib/。")
        mhchem_path = katex_dir / "contrib" / "mhchem.min.js"
        mhchem_tag = f'<script src="{mhchem_path.as_uri()}"></script>' if mhchem_path.is_file() else ""

        katex_tags = f"""
<link rel="stylesheet" href="{css_uri}">
<script src="{js_uri}"></script>{ar_tag}{mhchem_tag}
<script>
/* KaTeX 渲染完成标记：print_pdf.js 依赖 [data-math-state] != pending 判定可打印 */
(function () {{
  var state = 'error';
  function finish(s) {{
    state = s;
    document.documentElement.setAttribute('data-math-state', s);
  }}
  function run() {{
    if (typeof renderMathInElement !== 'function') {{
      finish('error:no-autorender');
      return;
    }}
    try {{
      renderMathInElement(document.body, {{
        delimiters: [
          {{left: '$$', right: '$$', display: true}},
          {{left: '\\\\[', right: '\\\\]', display: true}},
          {{left: '$', right: '$', display: false}},
          {{left: '\\\\(', right: '\\\\)', display: false}}
        ],
        ignoredTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code'],
        throwOnError: false,
        errorColor: '#b3261e'
      }});
      var n = document.querySelectorAll('.katex').length;
      finish(n > 0 ? 'done:' + n : 'done:0');
    }} catch (e) {{
      finish('error:' + (e && e.message ? e.message.slice(0, 60) : 'unknown'));
    }}
  }}
  if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', function () {{ setTimeout(run, 0); }});
  }} else {{
    setTimeout(run, 0);
  }}
}})();
</script>
"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN" data-math-state="pending">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="author" content="{esc(md.get('author', ''))}">
<meta name="description" content="{esc(md.get('subject', ''))}">
<meta name="keywords" content="{esc(md.get('keywords', ''))}">
<meta name="generator" content="md-print-pdf v{VERSION}">
<style>
{css}
</style>{katex_tags}
</head>
<body class="{layout_cls}" data-font-heading="{esc(cfg['fonts']['heading'][:40])}">
{watermark}
{cover}
{toc}
<main class="content">
{body}
</main>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# 8. 主流程
# ---------------------------------------------------------------------------

def guess_defaults(md_path: Path) -> None:
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Markdown → A4 打印版 HTML（零依赖）",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--md", required=True, help="输入 Markdown 文件")
    ap.add_argument("--out", required=True, help="输出 HTML 文件")
    ap.add_argument("--config", default=None, help="配置文件（JSON），可省略")
    ap.add_argument("--katex-dir", default=None,
                    help="KaTeX 离线目录（含 katex.min.js / katex.min.css / fonts/）")
    ap.add_argument("--diag", default=None, help="把诊断 JSON 写到此路径（供质检读取）")
    ap.add_argument("--quiet", action="store_true", help="只输出错误")
    args = ap.parse_args(argv)

    def say(msg):
        if not args.quiet:
            log(msg)

    md_path = Path(args.md).resolve()
    if not md_path.is_file():
        log(f"[错误] 找不到输入文件：{md_path}")
        return 2

    cfg = dict(DEFAULT_CONFIG)
    if args.config:
        cp = Path(args.config).resolve()
        if cp.is_file():
            try:
                user_cfg = json.loads(cp.read_text(encoding="utf-8"))
                cfg = _deep_merge(DEFAULT_CONFIG, user_cfg)
                say(f"[配置] 已加载 {cp.name}")
            except json.JSONDecodeError as e:
                log(f"[错误] 配置文件 JSON 解析失败：{e}")
                return 2
        else:
            say(f"[配置] 未找到 {cp}，使用默认配置")

    # 字体预检
    DIAG["fonts_warning"] = precheck_fonts(cfg)

    # KaTeX 目录探测
    katex_dir = None
    if args.katex_dir:
        kd = Path(args.katex_dir).resolve()
        if kd.is_dir():
            katex_dir = kd
    if katex_dir is None:
        # 默认探测：脚本在 scripts/ 下 → ../assets/katex
        cand = (Path(__file__).resolve().parent.parent / "assets" / "katex")
        if cand.is_dir():
            katex_dir = cand

    md_text = md_path.read_text(encoding="utf-8")
    body, meta = convert(md_text, cfg, md_path.parent, katex_dir)

    # 图片路径 → file:/// URI（坑位4）
    # 说明：DIAG["images"] 只由 md 语法 ![]() 记录；md 内嵌 HTML <img>（并排图）
    #      不经行内解析，因此这里统一补登记，保证质检统计与实际图片数一致。
    def _fix_img(m):
        src = m.group(1)
        if src.startswith("file:") or src.startswith("data:") or re.match(r"^[a-z]+://", src):
            return m.group(0)
        uri, exists = make_image_uri(src, md_path.parent)
        matched = False
        for rec in DIAG["images"]:
            if rec["src"] == src and "exists" not in rec:
                rec["exists"] = exists
                rec["uri"] = uri
                matched = True
                break
        if not matched:
            line_no = body[:m.start()].count("\n") + 1
            DIAG["images"].append({"src": src, "line": line_no,
                                   "exists": exists, "uri": uri, "source": "html"})
        return m.group(0).replace(f'src="{src}"', f'src="{uri}"')
    body = re.sub(r'<img\b[^>]*?\bsrc="([^"]+)"[^>]*>', _fix_img, body)

    # 公式策略
    body, math_mode = process_math(body, cfg, katex_dir, md_path.parent)

    # 图表编号 + 交叉引用
    body = apply_numbering(body, cfg, meta["toc"])

    # 功能项 #7：超宽表格自动降字号 + 告警
    body = fit_table_widths(body, cfg)

    # 章节序号校验（体系：一、/1、/1.1/1.1.1，手写为主 + 工具校验）
    check_heading_numbering(meta["toc"], cfg)
    # 表注必须紧邻其后的表格（表名在表上方）
    check_tabcap_adjacency(body)

    cover = build_cover(cfg, meta)
    toc = build_toc(cfg, meta["toc"])
    watermark = build_watermark(cfg)

    html_out = build_html(cfg, body, cover, toc, watermark, meta, katex_dir, math_mode)

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_out, encoding="utf-8")

    # ---- 控制台报告 ----
    say("")
    say("=" * 68)
    say("md2html 转换完成")
    say("=" * 68)
    say(f"输入    : {md_path}")
    say(f"输出    : {out_path}  ({len(html_out.encode('utf-8')) / 1024:.1f} KB)")
    say(f"公式模式: {math_mode}" + (f"  (KaTeX: {katex_dir})" if math_mode == "render" else ""))
    say(f"封面    : {'启用' if cfg['cover']['enabled'] else '关闭'}"
        f"   目录: {'启用' if cfg['toc']['enabled'] else '关闭'}"
        f" (深度 {cfg['toc']['depth']})"
        f"   水印: {'启用' if cfg['watermark']['enabled'] else '关闭'}")
    say("-" * 68)
    say(f"标题 {len(DIAG['headings'])} 个 ｜ 表格 {len(DIAG['tables'])} 个 ｜ "
        f"图片 {len(DIAG['images'])} 张 ｜ 图注 {sum(1 for f in DIAG['figures'] if f['kind'] == 'fig')} 个 ｜ "
        f"表注 {sum(1 for f in DIAG['figures'] if f['kind'] == 'tab')} 个 ｜ "
        f"公式 {len(DIAG['math'])} 处 ｜ 交叉引用 {len(DIAG['refs'])} 处 ｜ 脚注 {len(DIAG['footnotes'])} 处")
    fitted = [t for t in DIAG["tables"] if t.get("fittedFontSize")]
    ovf = [t for t in DIAG["tables"] if t.get("overflow")]
    if fitted:
        say(f"[表格适配] {len(fitted)} 个表格超版心已自动降字号（"
            + "、".join(f"第{t['index']}个→{t['fittedFontSize']}pt" for t in fitted) + "）")
    if ovf:
        say(f"[表格告警] {len(ovf)} 个表格降至 7pt 下限仍超版心，建议拆列、缩内容或改横版："
            + "、".join(f"第{t['index']}个(源第{t.get('line', '?')}行)" for t in ovf))

    warn_count = 0
    for w in DIAG["fonts_warning"]:
        say("\n" + w)
        warn_count += 1

    missing = [r for r in DIAG["images"] if r.get("exists") is False]
    for r in missing:
        say(f"\n[图片告警] 第 {r['line']} 行引用的图片不存在：{r['src']}")
        warn_count += 1

    bad_refs = [r for r in DIAG["refs"] if r["resolved"] is False]
    for r in bad_refs:
        say(f"\n[引用错误] 第 {r['line']} 行引用了不存在的"
            f"{'图' if r['kind'] == 'fig' else '表'}：{r['target']}")
        warn_count += 1

    ragged = [t for t in DIAG["tables"] if t["ragged"]]
    for t in ragged:
        say(f"\n[表格告警] 第 {t['index']} 个表格（第 {t['line']} 行起）列数不一致，已按表头 {t['header_cols']} 列补齐。")
        warn_count += 1

    if DIAG["math"] and math_mode == "placeholder":
        say(f"\n[公式告警] 文档含 {len(DIAG['math'])} 处公式，当前为占位模式（未渲染）。")
        say("           激活方式：把 KaTeX 离线包放入 assets/katex/，或将配置 math.mode 设为 image 并用 --math-image 指定目录。")
        warn_count += 1

    if DIAG["footnotes"]:
        say(f"\n[脚注提示] {len(DIAG['footnotes'])} 处脚注已排在文末，非当页页底（浏览器打印引擎无此能力）。")

    if DIAG["unclosed_fragment"]:
        for u in DIAG["unclosed_fragment"]:
            say(f"\n[结构告警] 第 {u['line']} 行起的代码围栏未闭合。")
            warn_count += 1

    if DIAG["numcheck"]:
        say(f"\n[章节序号告警] 共 {len(DIAG['numcheck'])} 处（体系：一、/1、/1.1/1.1.1，不得跳级）：")
        for n in DIAG["numcheck"][:20]:
            loc = f"第 {n['line']} 行" if n["line"] else "未知行"
            say(f"   · {loc} 第 {n['level']} 级「{n['text']}」——{n['issue']}：{n['detail']}")
        if len(DIAG["numcheck"]) > 20:
            say(f"   ·（其余 {len(DIAG['numcheck']) - 20} 处从略）")
        warn_count += len(DIAG["numcheck"])

    if DIAG["tabcap_orphan"]:
        for t in DIAG["tabcap_orphan"]:
            loc = f"第 {t['line']} 行" if t["line"] else "未知行"
            say(f"\n[表名位置告警] {loc} 的表名「{t['title']}」未紧邻其后的表格；"
                f"表名应写在表格上方。")
            warn_count += 1

    if DIAG["capnum"]:
        for c in DIAG["capnum"]:
            loc = f"第 {c['line']} 行" if c["line"] else "未知行"
            say(f"\n[题注序号提示] {loc} 「{c['title']}」写作 {c['written']}，"
                f"已按自动编号输出为 {c['generated']}。")

    say("-" * 68)
    say(f"告警合计：{warn_count} 条" + ("（详见上方）" if warn_count else "（无）"))
    say("=" * 68)

    if args.diag:
        dp = Path(args.diag).resolve()
        dp.parent.mkdir(parents=True, exist_ok=True)
        dp.write_text(json.dumps({
            "md": str(md_path), "out": str(out_path), "math_mode": math_mode,
            "katex_dir": str(katex_dir) if katex_dir else None,
            "diag": DIAG, "warn_count": warn_count,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
