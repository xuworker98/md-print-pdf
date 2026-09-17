#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""md-print-pdf · qc_check.py —— 质检：读 md2html 诊断 JSON + PDF 结构，产出分级报告。

用法：
  python qc_check.py --diag <diag.json> [--pdf <out.pdf>] [--md <src.md>]
                     [--json <报告.json>] [--quiet]

退出码：0 = 无 error 级问题；1 = 存在 error 级问题；2 = 参数/文件错误。
零第三方依赖，仅用标准库。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zlib
from pathlib import Path
from urllib.parse import unquote, urlparse

# ------------------------------------------------------------------ 级别
ERROR, WARN, INFO = "error", "warn", "info"
_LABEL = {ERROR: "[错误]", WARN: "[告警]", INFO: "[提示]"}
_ORDER = {ERROR: 0, WARN: 1, INFO: 2}


class Report:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, level: str, code: str, msg: str, detail: str = "") -> None:
        self.items.append({"level": level, "code": code, "msg": msg, "detail": detail})

    def count(self, level: str) -> int:
        return sum(1 for i in self.items if i["level"] == level)

    def dump(self, quiet: bool = False) -> None:
        if not self.items:
            print("[md-print-pdf] 质检通过：未发现问题。")
            return
        ordered = sorted(self.items, key=lambda i: _ORDER[i["level"]])
        for it in ordered:
            if quiet and it["level"] == INFO:
                continue
            print("%s %s" % (_LABEL[it["level"]], it["msg"]))
            if it["detail"]:
                for line in str(it["detail"]).splitlines():
                    print("        " + line)
        print("—" * 46)
        print("质检汇总：错误 %d 项 / 告警 %d 项 / 提示 %d 项"
              % (self.count(ERROR), self.count(WARN), self.count(INFO)))


# ------------------------------------------------------- 单项检查
def check_fonts(diag: dict, rep: Report) -> None:
    for w in diag.get("fonts_warning") or []:
        msg = w if isinstance(w, str) else json.dumps(w, ensure_ascii=False)
        rep.add(WARN, "font", "[字体告警] " + msg,
                "原因：目标机器未安装该字体。建议：安装字体或改用可嵌入的替代字体。")


def _uri_to_path(src: str) -> Path | None:
    try:
        if src.startswith("file:"):
            return Path(unquote(urlparse(src).path.lstrip("/"))) if not re.match(r"^/[A-Za-z]:", urlparse(src).path) \
                else Path(unquote(urlparse(src).path[1:]))
    except Exception:
        return None
    return None


def check_images(diag: dict, rep: Report) -> None:
    miss = []
    for im in diag.get("images") or []:
        src = im.get("src") or ""
        exists = im.get("exists")
        if exists is False:
            miss.append(im)
            continue
        if exists is None and src.startswith("file:"):
            p = _uri_to_path(src)
            if p is not None and not p.exists():
                miss.append(im)
    for im in miss:
        rep.add(ERROR, "image-missing",
                "[图片告警] 第 %s 行引用的图片不存在：%s" % (im.get("line", "?"), im.get("src", "")),
                "已在正文输出占位框（禁止静默空白）。请修正路径或补齐文件。")
    if not miss and diag.get("images"):
        rep.add(INFO, "image-ok", "[图片] %d 张全部存在。" % len(diag["images"]))


def check_math(diag: dict, rep: Report, math_mode: str = "") -> None:
    """math 列表 = 文档中检测到的公式清单；只有占位模式才是问题。

    补丁 2026-09-17：原实现把"检测到公式"误判为"公式未渲染"，导致已成功用
    KaTeX 渲染的文档也刷出一串告警。现按 math_mode 判定。
    """
    items = diag.get("math") or []
    if not items or math_mode == "render":
        return
    head = "第 %s 行 %s 公式：%s"
    lines = [head % (m.get("line", "?"), m.get("kind", ""), (m.get("raw") or "").strip()[:60])
             for m in items[:10]]
    if len(items) > 10:
        lines.append("（其余 %d 处从略）" % (len(items) - 10))
    rep.add(WARN, "math-placeholder",
            "[公式告警] 文档含 %d 处公式，当前为占位模式（未渲染）" % len(items),
            "原因：未激活离线公式引擎。\n" + "\n".join(lines))


def check_refs(diag: dict, rep: Report) -> None:
    for r in diag.get("refs") or []:
        # resolved: None=回填流程未跑到（异常）；False=回填过但没找到；字符串=已解析
        if r.get("resolved") in (None, False):
            kind = "图" if r.get("kind") == "fig" else "表"
            rep.add(ERROR, "ref-unresolved",
                    "[交叉引用] 第 %s 行引用了不存在的%s：%s"
                    % (r.get("line", "?"), kind, r.get("target", "")),
                    "请检查占位符拼写，或在文中补上对应图表。")


def check_tables(diag: dict, rep: Report) -> None:
    for t in diag.get("tables") or []:
        if t.get("ragged"):
            rep.add(WARN, "table-ragged",
                    "[表格告警] 第 %d 个表格（源文件第 %s 行）列数不齐：表头 %s 列，数据行最多 %s 列"
                    % (t.get("index", 0), t.get("line", "?"),
                       t.get("header_cols"), t.get("max_data_cols", "?")),
                    "已自动补齐空单元格（输出 &nbsp;），请核对源文件。")
        if t.get("overflow"):
            rep.add(WARN, "table-overflow",
                    "[表格告警] 第 %d 个表格（源文件第 %s 行）超宽：降至 7pt 下限仍超版心"
                    % (t.get("index", 0), t.get("line", "?")),
                    "建议：拆分表格、精简单元格内容，或将页面改为横版（paper.orientation=landscape）。")


def check_captions(diag: dict, rep: Report) -> None:
    for c in diag.get("capnum") or []:
        rep.add(WARN, "caption-number",
                "[题注告警] 第 %s 行的%s题注「%s」原文写 %s，按章-序规则应为 %s"
                % (c.get("line", "?"), "图" if c.get("kind") == "fig" else "表",
                   c.get("title", ""), c.get("written"), c.get("generated")),
                "已按 numbering.style 自动重排；如需保留原编号请关闭 numbering.auto。")
    for c in diag.get("tabcap_orphan") or []:
        rep.add(WARN, "tabcap-orphan",
                "[题注告警] 表题「%s」与对应的表格不相邻（源文件第 %s 行）"
                % (c.get("title", ""), c.get("line", "?")),
                "表题应紧贴表格上方；中间夹段落会导致跨页时题注与表格分离。")


def check_numbering(diag: dict, rep: Report) -> None:
    for n in diag.get("numcheck") or []:
        rep.add(WARN, "heading-number",
                "[章节序号] 第 %s 行「%s」%s" % (n.get("line", "?"), n.get("text", ""), n.get("issue", "")),
                n.get("detail", ""))
    for u in diag.get("unclosed_fragment") or []:
        rep.add(ERROR, "unclosed",
                "[结构错误] 第 %s 行存在未闭合的%s" % (u.get("line", "?"), u.get("kind", "片段")),
                "未闭合会导致后续内容被错误吞并，请检查源文件。")


# ------------------------------------------------------- PDF 层检查
_PAGE_RE = re.compile(rb"/Type\s*/Page(?![s])")
_MEDIABOX_RE = re.compile(rb"/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)")


def _pdf_blobs(data: bytes) -> list[bytes]:
    """原文 + 全部 FlateDecode 解压流（书签字典常在压缩对象流内，裸搜不到）。"""
    blobs = [data]
    for m in _STREAM_RE.finditer(data):
        end = data.find(b"endstream", m.end())
        if end < 0:
            continue
        try:
            blobs.append(zlib.decompress(data[m.end():end]))
        except Exception:
            pass
    return blobs


_STREAM_RE = re.compile(rb"stream\r?\n")


def check_pdf(pdf: Path, rep: Report, cfg: dict | None = None) -> dict:
    info: dict = {}
    if not pdf or not pdf.exists():
        rep.add(ERROR, "pdf-missing", "[产物错误] 未找到输出 PDF：%s" % pdf)
        return info
    data = pdf.read_bytes()
    size_mb = len(data) / 1024 / 1024
    pages = len(_PAGE_RE.findall(data))
    info.update({"pages": pages, "mb": round(size_mb, 2)})
    if pages == 0:
        rep.add(ERROR, "pdf-empty", "[产物错误] PDF 未解析到任何页面，文件可能损坏。")
        return info

    mb = _MEDIABOX_RE.search(data)
    if mb:
        w, h = float(mb.group(3)), float(mb.group(4))
        info["page_size_pt"] = [round(w), round(h)]
        if abs(w - 595) > 6 or abs(h - 842) > 6:
            rep.add(WARN, "paper-size",
                    "[纸张告警] 实测页面尺寸 %.0f×%.0f pt，非标准 A4（595×842）" % (w, h),
                    "请检查 paper.size / margin 配置，或是否启用了 preferCSSPageSize。")

    if size_mb > 20:
        rep.add(WARN, "pdf-large",
                "[体积告警] PDF 体积 %.1f MB，明显偏大" % size_mb,
                "多因内嵌高清位图。建议压缩原图，或改用矢量图（SVG）。")
    elif size_mb > 10:
        rep.add(INFO, "pdf-larger",
                "[体积提示] PDF 体积 %.1f MB，偏大（阈值 10 MB）" % size_mb,
                "若含 AI 写实位图属正常；纯矢量文档一般 < 3 MB。")

    # 书签与元数据（2026-09-17 增补，供验收留证）
    blobs = _pdf_blobs(data)
    info["bookmarks"] = any(b"/Outlines" in b for b in blobs)
    info["meta_title"] = any(b"/Title" in b for b in blobs)
    info["meta_author"] = any(b"/Author" in b for b in blobs)
    if info["bookmarks"]:
        rep.add(INFO, "bookmarks-ok", "[书签] PDF 大纲（/Outlines）已生成。")
    else:
        rep.add(INFO, "bookmarks-none", "[书签] 未检测到 PDF 大纲（关闭书签或引擎不支持时属正常）。")
    rep.add(INFO, "meta-title", "[元数据] Title %s。" % ("已写入" if info["meta_title"] else "未写入"))
    rep.add(INFO, "meta-author", "[元数据] Author %s。" % ("已写入" if info["meta_author"] else "未配置"))
    return info


# ------------------------------------------------------- 主流程
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="md-print-pdf 质检")
    ap.add_argument("--diag", default=None, help="md2html 输出的诊断 JSON")
    ap.add_argument("--pdf", default=None, help="待检查的 PDF")
    ap.add_argument("--md", default=None, help="源 md（仅用于报告中标注）")
    ap.add_argument("--json", dest="json_out", default=None, help="把报告写成 JSON")
    ap.add_argument("--quiet", action="store_true", help="隐藏提示级")
    a = ap.parse_args(argv)

    if not a.diag and not a.pdf:
        print("qc_check.py：至少需要 --diag 或 --pdf 之一。", file=sys.stderr)
        return 2

    rep = Report()
    diag: dict = {}
    math_mode = ""
    if a.diag:
        p = Path(a.diag)
        if not p.exists():
            print("qc_check.py：诊断文件不存在：%s" % p, file=sys.stderr)
            return 2
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:                       # 配置/结构异常不崩溃
            rep.add(WARN, "diag-unreadable", "[质检告警] 诊断 JSON 无法解析：%s" % e)
            raw = {}
        # md2html --diag 输出两层：{md,out,math_mode,katex_dir,diag:{...},warn_count}
        # 兼容裸 diag 结构（补丁 2026-09-17：原先按扁平读，导致统计全为 0）
        if isinstance(raw, dict) and isinstance(raw.get("diag"), dict):
            diag = raw["diag"]
            math_mode = raw.get("math_mode") or ""
        elif isinstance(raw, dict):
            diag = raw

    check_fonts(diag, rep)
    check_images(diag, rep)
    check_math(diag, rep, math_mode)
    check_refs(diag, rep)
    check_tables(diag, rep)
    check_captions(diag, rep)
    check_numbering(diag, rep)

    pdf_info = check_pdf(Path(a.pdf), rep) if a.pdf else {}

    print("=" * 46)
    print("md-print-pdf 质检报告")
    if a.md:
        print("  源文件：%s" % a.md)
    if a.pdf:
        print("  产物：%s（%s 页 / %s MB）"
              % (a.pdf, pdf_info.get("pages", "?"), pdf_info.get("mb", "?")))
    n_tab = len(diag.get("tables") or [])
    n_fig = len(diag.get("figures") or [])
    n_img = len(diag.get("images") or [])
    n_math = len(diag.get("math") or [])
    tag = {"render": "已渲染", "placeholder": "占位"}.get(math_mode, math_mode or "未知")
    print("  统计：标题 %d 个 / 表格 %d 个 / 图表题注 %d 处 / 图片 %d 张 / 公式 %d 处（%s）"
          % (len(diag.get("headings") or []), n_tab, n_fig, n_img, n_math, tag))
    print("=" * 46)
    rep.dump(quiet=a.quiet)

    if a.json_out:
        Path(a.json_out).write_text(json.dumps({
            "source": a.md, "pdf": a.pdf, "pdf_info": pdf_info,
            "counts": {"error": rep.count(ERROR), "warn": rep.count(WARN), "info": rep.count(INFO)},
            "items": rep.items,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    if rep.count(ERROR):
        print("→ 结论：存在 %d 项错误级问题，建议修复后重新生成。" % rep.count(ERROR))
        return 1
    print("→ 结论：无错误级问题，可交付。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
