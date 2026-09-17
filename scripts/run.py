#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""md-print-pdf · run.py —— 一键编排：md → 打印版 HTML → A4 PDF → 封面留白 → 元数据 → 质检。

用法：
  python run.py --md <输入.md> [--out <输出.pdf>] [--config print.config.json]
                [--work-dir <中间产物目录>] [--keep-html] [--preset <页脚预设>]
                [--no-cover-mask] [--skip-qc] [--quiet]

设计要点：
  · 中间产物（HTML / 诊断 JSON / Edge profile）默认写入系统临时目录，**不落项目仓库**；
  · 各步骤之间以退出码 + 机器可读标记衔接，任一步失败即中止并给出可操作提示；
  · 仅依赖标准库；Node / Python 解释器按「显式环境变量 → PATH → 常见安装位」顺序探测。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TAG = "[md-print-pdf]"


def log(msg: str, quiet: bool = False) -> None:
    if not quiet:
        print(TAG + " " + msg, flush=True)


def warn(msg: str) -> None:
    print(TAG + " 告警：" + msg, file=sys.stderr, flush=True)


def die(msg: str, code: int = 1) -> None:
    print(TAG + " 错误：" + msg, file=sys.stderr, flush=True)
    sys.exit(code)


# --------------------------------------------------------------- 依赖探测
def find_node() -> str:
    cands = [os.environ.get("NODE_EXE"), "node", "node.exe"]
    for c in cands:
        if not c:
            continue
        p = shutil.which(c) if not os.path.isabs(c) else (c if Path(c).exists() else None)
        if p:
            return p
    # 托管环境常见位置（Windows）
    for ver_dir in sorted(Path.home().joinpath(".workbuddy/binaries/node/versions").glob("*"), reverse=True) \
            if Path.home().joinpath(".workbuddy/binaries/node/versions").exists() else []:
        exe = ver_dir / ("node.exe" if os.name == "nt" else "bin/node")
        if exe.exists():
            return str(exe)
    die("未找到 Node.js。\n"
        "  解决方式：安装 Node.js 18+ 并加入 PATH，或设置环境变量 NODE_EXE 指向 node 可执行文件。", 3)


def find_node_modules() -> str:
    """返回需要写入 NODE_PATH 的目录（可为空字符串）。"""
    cands = []
    if os.environ.get("NODE_PATH"):
        cands.append(os.environ["NODE_PATH"])
    cands.append(str(ROOT / "node_modules"))
    home = Path.home()
    for base in (home / ".workbuddy/binaries/node/workspace/node_modules",
                 home / "AppData/Roaming/npm/node_modules",
                 Path("/usr/lib/node_modules"),
                 Path("/usr/local/lib/node_modules")):
        if base.exists():
            cands.append(str(base))
    for c in cands:
        if c and (Path(c) / "playwright-core").exists():
            return c
    return cands[0] if cands else ""


# --------------------------------------------------------------- 主流程
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Markdown → A4 打印级 PDF 一键流水线")
    ap.add_argument("--md", required=True, help="输入 Markdown 文件")
    ap.add_argument("--out", default=None, help="输出 PDF（默认与 md 同名同目录）")
    ap.add_argument("--config", default=str(ROOT / "print.config.json"), help="配置文件")
    ap.add_argument("--work-dir", default=None, help="中间产物目录（默认系统临时目录）")
    ap.add_argument("--keep-html", action="store_true", help="保留中间 HTML 并打印其路径")
    ap.add_argument("--preset", default=None, help="覆盖页脚预设：none|pagenum-only|title-pagefooter|chapter-pagefooter")
    ap.add_argument("--no-cover-mask", action="store_true", help="跳过封面页脚留白后处理")
    ap.add_argument("--skip-qc", action="store_true", help="跳过质检")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)

    md = Path(a.md).resolve()
    if not md.exists():
        die("输入文件不存在：%s" % md, 2)
    if md.suffix.lower() not in (".md", ".markdown"):
        warn("输入文件扩展名不是 .md，仍按 Markdown 处理。")

    pdf_out = Path(a.out).resolve() if a.out else md.with_suffix(".pdf")
    if not pdf_out.parent.exists():
        die("输出目录不存在：%s（本工具不自动创建目录）" % pdf_out.parent, 2)

    # ---- 配置 ----
    cfg_path = Path(a.config).resolve()
    cfg: dict = {}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception as e:
            die("配置文件解析失败：%s → %s" % (cfg_path, e), 2)
    else:
        warn("配置文件不存在，使用脚本内置默认值：%s" % cfg_path)
    if a.preset:
        cfg.setdefault("headerFooter", {})["preset"] = a.preset

    # ---- 中间产物目录 ----
    if a.work_dir:
        work = Path(a.work_dir).resolve()
        work.mkdir(parents=True, exist_ok=True)
    else:
        work = Path(tempfile.gettempdir()) / ("md-print-pdf-%s" % time.strftime("%Y%m%d-%H%M%S"))
        work.mkdir(parents=True, exist_ok=True)

    log("输入：%s" % md, a.quiet)
    log("输出：%s" % pdf_out, a.quiet)
    log("中间产物：%s" % work, a.quiet)

    html = work / (md.stem + ".print.html")
    diag = work / (md.stem + ".diag.json")
    cfg_effective = work / "print.config.effective.json"
    cfg_effective.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    py = sys.executable or "python3"
    katex_dir = ROOT / "assets" / "katex"
    katex_arg = str(katex_dir) if (katex_dir / "katex.min.js").exists() else ""

    # ---- 步骤 1：md → HTML ----
    log("步骤 1/5：Markdown → 打印版 HTML", a.quiet)
    cmd1 = [py, str(HERE / "md2html.py"), "--md", str(md), "--out", str(html),
            "--config", str(cfg_effective), "--diag", str(diag)]
    if katex_arg:
        cmd1 += ["--katex-dir", katex_arg]
    if a.quiet:
        cmd1.append("--quiet")
    r1 = subprocess.run(cmd1, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r1.stdout:
        print(r1.stdout, end="")
    if r1.returncode != 0:
        print(r1.stderr, file=sys.stderr)
        die("md2html 转换失败（退出码 %d）" % r1.returncode, 1)
    if not html.exists():
        die("md2html 未产出 HTML：%s" % html, 1)

    # ---- 步骤 2：HTML → PDF ----
    log("步骤 2/5：打印版 HTML → A4 PDF", a.quiet)
    node = find_node()
    nm = find_node_modules()
    env = dict(os.environ)
    if nm:
        env["NODE_PATH"] = nm
    cmd2 = [node, str(HERE / "print_pdf.js"), "--html", str(html), "--pdf", str(pdf_out),
            "--config", str(cfg_effective)]
    if a.quiet:
        cmd2.append("--quiet")
    r2 = subprocess.run(cmd2, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    node_out = (r2.stdout or "") + (r2.stderr or "")
    if r2.returncode != 0:
        print(node_out, file=sys.stderr)
        die("PDF 生成失败（退出码 %d）" % r2.returncode, 1)
    for line in node_out.splitlines():
        if not line.startswith("@@RESULT@@"):
            print(line, file=sys.stderr if "告警" in line else sys.stdout)
    if not pdf_out.exists():
        die("页面打印脚本未产出 PDF：%s" % pdf_out, 1)

    # ---- 步骤 3：封面页脚留白 ----
    cov = cfg.get("cover", {}) or {}
    if cov.get("enabled", True) and cov.get("maskFooter", True) and not a.no_cover_mask:
        log("步骤 3/5：封面页脚留白", a.quiet)
        cmd3 = [py, str(HERE / "pdf_cover_mask.py"), "--pdf", str(pdf_out),
                "--out", str(pdf_out), "--pages", "1"]
        r3 = subprocess.run(cmd3, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r3.returncode != 0:
            warn("封面页脚留白失败（不影响正文）：%s" % (r3.stderr or "").strip()[:200])
        else:
            log((r3.stdout or "").strip() or "已处理", a.quiet)
    else:
        log("步骤 3/5：跳过封面页脚留白", a.quiet)

    # ---- 步骤 4：PDF 元数据（Author/Subject/Keywords；Title 引擎已写） ----
    meta = cfg.get("metadata", {}) or {}
    meta_fields = {k: v for k, v in meta.items()
                   if k in ("author", "subject", "keywords", "title") and v}
    if meta_fields:
        log("步骤 4/5：PDF 元数据写入", a.quiet)
        cmdm = [py, str(HERE / "pdf_meta.py"), "--pdf", str(pdf_out)]
        for k in ("title", "author", "subject", "keywords"):
            if meta_fields.get(k):
                cmdm += ["--" + k, str(meta_fields[k])]
        rm = subprocess.run(cmdm, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if rm.returncode != 0:
            warn("元数据写入失败（不影响文档）： %s" % (rm.stderr or "").strip()[:200])
        else:
            log((rm.stdout or "").strip(), a.quiet)
    else:
        log("步骤 4/5：未配置元数据，跳过", a.quiet)

    # ---- 步骤 5：质检 ----
    qc_code = 0
    if a.skip_qc:
        log("步骤 5/5：跳过质检", a.quiet)
    else:
        log("步骤 5/5：质检", a.quiet)
        qc_json = work / (md.stem + ".qc.json")
        cmd4 = [py, str(HERE / "qc_check.py"), "--diag", str(diag), "--pdf", str(pdf_out),
                "--md", str(md), "--json", str(qc_json)]
        if a.quiet:
            cmd4.append("--quiet")
        r4 = subprocess.run(cmd4, capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(r4.stdout, end="")
        if r4.stderr:
            print(r4.stderr, end="", file=sys.stderr)
        qc_code = r4.returncode

    if a.keep_html:
        log("中间 HTML 保留于：%s" % html, a.quiet)
    print(TAG + " 完成：%s（%.1f KB）" % (pdf_out, pdf_out.stat().st_size / 1024))
    return 1 if qc_code == 1 else 0


if __name__ == "__main__":
    sys.exit(main())
