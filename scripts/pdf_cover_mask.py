#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pdf_cover_mask.py —— 指定页页脚留白（零依赖，纯 Python 标准库）

用途
----
浏览器打印引擎（Chromium/Edge）的页眉页脚是整篇统一的，无法“封面不显示、
正文显示”。本脚本对已生成的 PDF 做**增量更新**（incremental update）：
在指定页的页脚区域叠加一个与页面背景同色的矩形，实现“该页页脚留白”。

原理与安全性
------------
- 仅在文件末尾追加内容（新内容流对象 + 被修改页对象的同号重定义 +
  新 xref 段 + 新 trailer），不改动原始字节；任何标准阅读器按“最后一个
  xref”读取，这是 PDF 规范的标准增量更新机制。
- 仅依赖经典 xref 表（Chromium/Skia 产物即此格式，已实测验证）；
  不支持 xref 流（/Type /XRef）时给出明确报错，不做静默破坏。

用法
----
python pdf_cover_mask.py --pdf in.pdf --out out.pdf --pages 1 --margin-bottom-mm 18

参数
----
--pdf              输入 PDF
--out              输出 PDF（默认覆盖 --pdf 时请谨慎，建议另存）
--pages            需要留白的页码，逗号分隔（如 1 或 1,2）
--margin-bottom-mm 页脚下边距高度（mm），与打印 margin.bottom 一致
--color            遮盖色，默认 "1 1 1"（白色 RGB 归一化）
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

MM2PT = 72.0 / 25.4


def _die(msg: str) -> None:
    print(f"[pdf_cover_mask 错误] {msg}")
    sys.exit(2)


def parse_xref(data: bytes, xref_off: int) -> tuple[dict[int, int], dict]:
    """解析经典 xref 表，返回 {对象号: 字节偏移} 与 trailer 字典文本。"""
    if data[xref_off:xref_off + 4] != b"xref":
        _die("startxref 指向的不是经典 xref 表（可能为 xref 流），本工具不支持。")
    pos = xref_off + 4
    offsets: dict[int, int] = {}
    while True:
        m = re.compile(rb"\s*(\d+)\s+(\d+)\s*").match(data, pos)
        if not m:
            break
        start, count = int(m.group(1)), int(m.group(2))
        pos = m.end()
        if start == 0 and count > 0 and data[pos:pos + 20].startswith(b"0000000000"):
            pass  # 首段首条目是 freelist，照常逐条解析
        for k in range(count):
            entry = data[pos:pos + 20]
            mm = re.compile(rb"(\d{10})\s+(\d{5})\s+([nf])").match(entry)
            if not mm:
                _die(f"xref 条目解析失败（对象段 {start}+{k}），文件可能已损坏。")
            if mm.group(3) == b"n":
                offsets[start + k] = int(mm.group(1))
            pos += 20
        # 看后面是否还有新段或进入 trailer
        probe = re.compile(rb"\s*(\d+\s+\d+\s*|trailer)\b").match(data, pos)
        if not probe:
            break
        if probe.group(1) == b"trailer":
            pos = probe.end()
            break
        pos = probe.end()
    tm = re.compile(rb"trailer\s*(<<)", re.S).match(data, pos - len(b"trailer")) \
        if data[pos - 7:pos] == b"trailer" else re.compile(rb"trailer\s*(<<)", re.S).search(data, pos - 60)
    if not tm:
        _die("未找到 trailer 字典。")
    # 取 trailer 的平衡 << >>
    depth, i = 0, tm.start(1)
    while i < len(data):
        if data[i:i + 2] == b"<<":
            depth += 1
            i += 2
        elif data[i:i + 2] == b">>":
            depth -= 1
            i += 2
            if depth == 0:
                break
        else:
            i += 1
    trailer = data[tm.start(1):i].decode("latin-1")
    return offsets, trailer


def read_object(data: bytes, offsets: dict[int, int], num: int) -> tuple[int, str]:
    """按 xref 偏移读取对象原文，返回 (偏移, 文本)。"""
    off = offsets.get(num)
    if off is None:
        _die(f"对象 {num} 0 R 不在 xref 表中。")
    end = data.find(b"endobj", off)
    if end < 0:
        _die(f"对象 {num} 缺少 endobj。")
    return off, data[off:end].decode("latin-1")


def deref(data: bytes, offsets: dict[int, int], ref_num: int, key: str) -> int:
    """在 ref_num 对象中找 key 对应的间接引用号。"""
    _, text = read_object(data, offsets, ref_num)
    m = re.search(rf"/{key}\s+(\d+)\s+0\s+R", text)
    if not m:
        _die(f"对象 {ref_num} 中未找到 /{key} 引用。")
    return int(m.group(1))


def _leading_ctm_inverse(data: bytes, offsets: dict[int, int],
                         first_content_num: int) -> str:
    """解析页面第一个内容流首部的遗留 cm，返回其逆矩阵 cm 文本。

    Chromium/Skia 的页面内容流第一条操作符通常是「0.xx 0 0 -0.xx 0 H cm」
    （CSS 像素到 PDF 点的缩放翻转），且不带包裹 q。追加流会继承这个 CTM，
    直接画矩形会错位——故先写逆变换把坐标系复位。
    """
    off = offsets.get(first_content_num)
    if off is None:
        return ""
    end = data.find(b"endobj", off)
    blob = data[off:end]
    sm = re.search(rb"stream\r?\n(.*?)\r?\nendstream", blob, re.S)
    if not sm:
        return ""
    raw = sm.group(1)
    try:
        import zlib
        txt = zlib.decompress(raw).decode("latin-1")
    except Exception:
        return ""
    m = re.match(
        r"\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+cm",
        txt)
    if not m:
        return ""
    a, b, c, d, e, f = (float(x) for x in m.groups())
    det = a * d - b * c
    if abs(det) < 1e-12:
        return ""
    ia, ib = d / det, -b / det
    ic, id_ = -c / det, a / det
    ie, if_ = (c * f - d * e) / det, (b * e - a * f) / det
    return f"{ia:.6f} {ib:.6f} {ic:.6f} {id_:.6f} {ie:.6f} {if_:.6f} cm"


def mask_pages(pdf_in: Path, pdf_out: Path, pages: list[int],
               margin_bottom_mm: float, color: str = "1 1 1") -> int:
    data = pdf_in.read_bytes()

    si = data.rfind(b"startxref")
    if si < 0:
        _die("未找到 startxref，不是有效 PDF。")
    xref_off = int(data[si:].split()[1])
    offsets, trailer = parse_xref(data, xref_off)

    rm = re.search(r"/Root\s+(\d+)\s+0\s+R", trailer)
    if not rm:
        _die("trailer 中没有 /Root。")
    root = int(rm.group(1))
    pages_obj = deref(data, offsets, root, "Pages")

    def collect_leaves(num: int, out: list[int]) -> None:
        """递归收集叶子页（页面树可能嵌套中间 /Pages 节点）。"""
        _, text = read_object(data, offsets, num)
        kids = re.search(r"/Kids\s*\[([^\]]*)\]", text)
        if not kids:
            _die(f"/Pages 对象 {num} 中未找到 /Kids。")
        for ref in re.findall(r"(\d+)\s+0\s+R", kids.group(1)):
            n = int(ref)
            _, t = read_object(data, offsets, n)
            if re.search(r"/Type\s*/Pages\b", t):
                collect_leaves(n, out)
            else:
                out.append(n)

    order: list[int] = []
    collect_leaves(pages_obj, order)
    if not order:
        _die("页面树为空。")

    max_obj = max(offsets) if offsets else 0
    new_bodies: list[bytes] = []
    new_entries: list[tuple[int, int]] = []      # (对象号, 将来偏移，追加时回填)
    next_obj = max_obj + 1
    patched: dict[int, str] = {}                 # 页对象号 -> 修改后原文

    h_pt = margin_bottom_mm * MM2PT

    for p in pages:
        if p < 1 or p > len(order):
            _die(f"--pages 中的 {p} 超出页数范围（1–{len(order)}）。")
        page_num = order[p - 1]
        if page_num in patched:
            continue
        _, page_text = read_object(data, offsets, page_num)

        mb = re.search(r"/MediaBox\s*\[([^\]]*)\]", page_text)
        if not mb:
            _die(f"第 {p} 页对象缺少 /MediaBox。")
        box = [float(x) for x in mb.group(1).split()]
        w, h = box[2] - box[0], box[3] - box[1]

        # 首个内容流（用于解析遗留 CTM）
        cm_ref = re.search(r"/Contents\s+(\d+)\s+0\s+R", page_text)
        ca_ref = re.search(r"/Contents\s*\[([^\]]*)\]", page_text)
        first_stream = None
        if cm_ref:
            first_stream = int(cm_ref.group(1))
        elif ca_ref:
            refs = re.findall(r"(\d+)\s+0\s+R", ca_ref.group(1))
            if refs:
                first_stream = int(refs[0])
        inv_cm = _leading_ctm_inverse(data, offsets, first_stream) if first_stream else ""

        # 遮盖内容流：先复位 CTM 与裁剪，再画矩形（覆盖页脚区，含正文底部边缘）
        content = (f"q\n{inv_cm}\n0 0 {w:.2f} {h:.2f} re W n\n"
                   f"{color} rg 0 0 {w:.2f} {h_pt:.2f} re f\nQ").encode("latin-1")
        mask_num = next_obj
        next_obj += 1
        new_bodies.append(
            f"{mask_num} 0 obj\n<< /Length {len(content)} >>\nstream\n".encode("latin-1")
            + content + b"\nendstream\nendobj\n")
        new_entries.append((mask_num, -1))

        # 修改页对象：/Contents 扩为数组并追加遮盖流
        new_text = None
        if ca_ref:
            new_text = page_text[:ca_ref.start(1)] + ca_ref.group(1).rstrip() + f" {mask_num} 0 R " + page_text[ca_ref.end(1):]
        elif cm_ref:
            new_text = (page_text[:cm_ref.start()] + f"/Contents [{cm_ref.group(1)} 0 R {mask_num} 0 R]"
                        + page_text[cm_ref.end():])
        else:
            _die(f"第 {p} 页对象没有 /Contents。")
        patched[page_num] = new_text

    # 组装增量更新段
    out = bytearray(data)
    for obj_num, text in patched.items():
        # read_object 返回的原文自带「N 0 obj」头，这里直接续写，勿再包一层
        new_entries.append((obj_num, len(out)))
        out += text.encode("latin-1") + b"\nendobj\n"
    for idx, (obj_num, _) in enumerate(new_entries):
        if new_entries[idx][1] < 0:
            new_entries[idx] = (obj_num, len(out))
            out += new_bodies.pop(0)
    maxnum = max([n for n, _ in new_entries] + list(offsets))
    new_xref_off = len(out)
    seg = {}
    for obj_num, off in new_entries:
        seg.setdefault(obj_num, off)
    starts = sorted(seg)
    xref_text = "xref\n"
    # 连续段合并
    groups: list[tuple[int, list[int]]] = []
    for n in starts:
        if groups and n == groups[-1][0] + len(groups[-1][1]):
            groups[-1][1].append(n)
        else:
            groups.append((n, [n]))
    for start, nums in groups:
        xref_text += f"{start} {len(nums)}\n"
        for n in nums:
            xref_text += f"{seg[n]:010d} 00000 n \n"
    xref_text += (f"trailer\n<< /Size {maxnum + 1} /Root {root} 0 R /Prev {xref_off} >>\n"
                  f"startxref\n{new_xref_off}\n%%EOF\n")
    out += xref_text.encode("latin-1")
    pdf_out.write_bytes(bytes(out))
    return len(patched)


def main() -> int:
    ap = argparse.ArgumentParser(description="指定页页脚留白（PDF 增量更新，零依赖）")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pages", default="1", help="需要留白的页码，逗号分隔")
    ap.add_argument("--margin-bottom-mm", type=float, default=18.0)
    ap.add_argument("--color", default="1 1 1", help="遮盖色 RGB 归一化，如 '1 1 1'")
    a = ap.parse_args()

    pdf_in, pdf_out = Path(a.pdf), Path(a.out)
    if not pdf_in.is_file():
        _die(f"找不到输入 PDF：{pdf_in}")
    pages = [int(x) for x in re.split(r"[,\s]+", a.pages.strip()) if x]
    n = mask_pages(pdf_in, pdf_out, pages, a.margin_bottom_mm, a.color)
    print(f"[pdf_cover_mask] 已对 {n} 页做页脚留白：{pdf_out} "
          f"({pdf_out.stat().st_size / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
