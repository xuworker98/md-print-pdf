#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""md-print-pdf · pdf_meta.py —— PDF 元数据后处理（Author/Subject/Keywords 等）。

背景（坑位24）：Chromium printToPDF 只把 document.title 写进 PDF /Info，
<meta name="author"> 等不落地。本脚本用 PDF 增量更新（与 pdf_cover_mask.py
同思路）追加一个新 /Info 对象 + 新 xref 段 + 带 /Prev 的 trailer，
在不动原对象的前提下覆盖元数据。零第三方依赖。

用法：
  python pdf_meta.py --pdf <file.pdf> [--out <out.pdf>]
                     [--title ...] [--author ...] [--subject ...] [--keywords ...]

行为约定：
  · 只提供 title 以外的字段时，Title 从原 /Info 继承，不会丢；
  · 非 ASCII 值按 PDF 规范写成 UTF-16BE 十六进制串；
  · 结构不支持（xref stream / 无 trailer）时退出码 0 并打印告警，供流水线降级；
  · 写入后自动回读校验，失败不落盘（先写临时文件再替换）。
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
import time
from pathlib import Path

TAG = "[pdf_meta]"

_TEXT_KEYS = ("Title", "Author", "Subject", "Keywords", "Creator", "Producer")


def _pdf_text(value: str) -> str:
    """把字符串编码为 PDF 文本值：纯 ASCII 用字面串，否则 UTF-16BE 十六进制。"""
    if all(32 <= ord(c) < 127 and c not in "()\\" for c in value):
        return "(" + value + ")"
    body = "".join("%04X" % ord(c) for c in (chr(0xFEFF) + value))
    return "<" + body + ">"


def _last_trailer(data: bytes) -> tuple[int, dict]:
    """返回 (最后 startxref 偏移, trailer 字典字节串)。"""
    i = data.rfind(b"startxref")
    if i < 0:
        raise ValueError("未找到 startxref")
    m = re.search(rb"startxref\s+(\d+)", data[i:i + 64])
    if not m:
        raise ValueError("startxref 后无偏移量")
    off = int(m.group(1))
    # 最后一个 trailer 关键字
    j = data.rfind(b"trailer")
    if j < 0:
        raise ValueError("未找到 trailer（可能是 xref stream 结构）")
    end = data.find(b"startxref", j)
    dic = data[j + len(b"trailer"):end if end > 0 else len(data)]
    return off, dic


def _dict_get(dic: bytes, key: str):
    m = re.search(rb"/" + key.encode() + rb"\s+(\d+)\s+0\s+R", dic)
    return int(m.group(1)) if m else None


def _extract_old_info(data: bytes) -> dict:
    """提取原 /Info 字典里的文本字段（Title/Producer/CreationDate 等值原样保留）。"""
    out: dict[str, str] = {}
    m = re.search(rb"/Info\s+(\d+)\s+0\s+R", data)
    if not m:
        return out
    num = int(m.group(1))
    om = re.search(rb"(?m)^" + str(num).encode() + rb" 0 obj\s*(.*?)endobj", data, re.S)
    if not om:
        return out
    body = om.group(1)
    a = body.find(b"<<")
    b = body.rfind(b">>")
    if a < 0 or b < 0:
        return out
    dic = body[a:b + 2]
    for key in _TEXT_KEYS + ("CreationDate", "ModDate"):
        km = re.search(rb"/" + key.encode() + rb"\s*((?:\((?:[^()\\]|\\.)*\))|<[^>]*>)", dic)
        if km:
            out[key] = km.group(1).decode("latin-1")
    return out


def _strip_key(dic: str, key: str) -> str:
    return re.sub(r"/" + key + r"\s*(?:\((?:[^()\\]|\\.)*\)|<[^>]*>)\s*", "", dic)


def write_meta(pdf: Path, out: Path, fields: dict) -> None:
    data = pdf.read_bytes()
    prev_xref_off, trailer = _last_trailer(data)

    size_m = re.search(rb"/Size\s+(\d+)", trailer)
    size = int(size_m.group(1)) if size_m else None
    root = _dict_get(trailer, "Root")
    if size is None or root is None:
        raise ValueError("trailer 缺 /Size 或 /Root")

    old = _extract_old_info(data)

    # 组装新 Info 字典
    pairs: list[str] = []
    title_val = fields.get("Title") or old.get("Title")
    if title_val:
        pairs.append("/Title " + title_val)
    for k in ("Author", "Subject", "Keywords"):
        v = fields.get(k)
        if v:
            pairs.append("/%s %s" % (k, _pdf_text(v)))
    if "Creator" in old:
        pairs.append("/Creator " + old["Creator"])
    pairs.append("/Producer " + (old.get("Producer") or _pdf_text("md-print-pdf (Chromium print)")))
    if "CreationDate" in old:
        pairs.append("/CreationDate " + old["CreationDate"])
    else:
        # D:YYYYMMDDHHmmSS
        pairs.append("/CreationDate (D:%s)" % time.strftime("%Y%m%d%H%M%S"))
    if not pairs:
        print(TAG + " 无可写元数据字段，跳过。")
        return
    info_dict = "<< " + " ".join(pairs) + " >>"

    new_num = size                     # 新对象号 = 原 /Size
    add = []
    add.append(b"\n")
    obj_offset = len(data) + len(add[0])
    add.append(("%d 0 obj\n" % new_num).encode("latin-1") + info_dict.encode("latin-1") + b"\nendobj\n")
    xref_off = len(data) + sum(len(x) for x in add)
    add.append(b"xref\n%d 1\n%010d 00000 n \n" % (new_num, obj_offset))
    add.append(("trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R /Prev %d >>\n"
                % (new_num + 1, root, new_num, prev_xref_off)).encode("latin-1"))
    add.append(("startxref\n%d\n%%%%EOF\n" % xref_off).encode("latin-1"))

    new_data = data + b"".join(add)

    # 回读自校验：新 trailer 能被解析且 /Info 指向新对象
    off2, tr2 = _last_trailer(new_data)
    assert _dict_get(tr2, "Info") == new_num, "回读校验失败：/Info 指向错误"
    assert _dict_get(tr2, "Root") == root, "回读校验失败：/Root 丢失"

    # 先写临时文件，成功后替换（写坏不污染原件）
    if out.resolve() == pdf.resolve():
        fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=str(out.parent))
        with open(fd, "wb") as f:
            f.write(new_data)
        out.write_bytes(Path(tmp).read_bytes())
        Path(tmp).unlink()
    else:
        out.write_bytes(new_data)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="PDF 元数据增量写入（零依赖）")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", default=None, help="默认原地更新")
    ap.add_argument("--title", default=None)
    ap.add_argument("--author", default=None)
    ap.add_argument("--subject", default=None)
    ap.add_argument("--keywords", default=None)
    a = ap.parse_args(argv)

    pdf = Path(a.pdf)
    out = Path(a.out) if a.out else pdf
    if not pdf.exists():
        print(TAG + " 错误：PDF 不存在：%s" % pdf, file=sys.stderr)
        return 2
    fields = {k.title(): v for k, v in
              {"title": a.title, "author": a.author,
               "subject": a.subject, "keywords": a.keywords}.items() if v}
    try:
        write_meta(pdf, out, fields)
    except ValueError as e:
        print(TAG + " 告警：跳过元数据写入（%s）。文档本身不受影响。" % e)
        return 0
    except AssertionError as e:
        print(TAG + " 错误：%s，未落盘。" % e, file=sys.stderr)
        return 1
    print(TAG + " 元数据已写入：%s（%s）"
          % (out, "、".join(fields.keys()) if fields else "仅保留原标题"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
