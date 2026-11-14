#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盘叔盲派 · 扫描 PDF 栅格化器（ps-anli-ku）

把扫描件 PDF 逐页渲染成 PNG，供逐页识读、入库。**只负责出图，不负责识字。**

## 为什么要它

扫描件的页图常是 JBIG2／CCITT 二值压缩。OCR 引擎（PaddleOCR／Tesseract）吃的是位图，
吃不掉这两种压缩流；**卡住入库的从来不是 OCR，是栅格化**。本器补这一步。

## 两条路

1. **主路：PyMuPDF**（`pip install pymupdf -i https://mirrors.aliyun.com/pypi/simple/`）
   ——MuPDF 内核，JBIG2、CCITT、JPEG2000 全解。有它就用它。
2. **零依赖退路**：`extract_scan_pages.py`，只切 JPEG 页图；CCITT 页可用
   `--tiff` 包成 TIFF 交给 ffmpeg（实测可读，见 `references/扫描集入库规范.md`）。

## 用法

    python pdf_render.py 书.pdf                     # 体检：页数、每页图型
    python pdf_render.py 书.pdf -o 页图/            # 全渲染（150 dpi）
    python pdf_render.py 书.pdf -o 页图/ --pages 12-35 --dpi 200
    python pdf_render.py 书.pdf -o 页图/ --pages 12,15,40

页码一律用**物理页序**（从 1 起），不是书内页码——扫描件的书内页码常有错漏，
两者对不上时以物理页为准，入库时把书内页码另记一栏。
"""
import argparse
import os
import sys


def probe(path):
    """体检：页数、页面尺寸、每页图像压缩类型分布。"""
    try:
        import pymupdf
    except ImportError:
        sys.exit("缺 PyMuPDF。装：pip install pymupdf -i https://mirrors.aliyun.com/pypi/simple/\n"
                 "（不想装就用 extract_scan_pages.py，只能切 JPEG 页图）")
    doc = pymupdf.open(path)
    kinds = {}
    for i, pg in enumerate(doc):
        for img in pg.get_images(full=True):
            xref = img[0]
            try:
                info = doc.extract_image(xref)
                k = (info.get("ext") or "?").lower()
            except Exception:
                k = "?"
            kinds.setdefault(k, []).append(i + 1)
    print("文件　%s" % os.path.basename(path))
    print("页数　%d" % doc.page_count)
    print("尺寸　%.1f × %.1f pt（首面）" % (doc[0].rect.width, doc[0].rect.height))
    for k, pages in sorted(kinds.items(), key=lambda x: -len(x[1])):
        head = "、".join(map(str, pages[:8])) + ("…" if len(pages) > 8 else "")
        print("图型　%-6s %3d 页　（第 %s 页）" % (k, len(pages), head))
    return doc


def parse_pages(spec, total):
    if not spec:
        return list(range(1, total + 1))
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    bad = [p for p in out if not (1 <= p <= total)]
    if bad:
        sys.exit("页码越界：%s（共 %d 页）" % (bad, total))
    return out


def main():
    ap = argparse.ArgumentParser(description="扫描 PDF 逐页渲染为 PNG（只出图，不识字）")
    ap.add_argument("pdf")
    ap.add_argument("-o", "--out", help="输出目录；不给则只体检")
    ap.add_argument("--pages", help="页序，如 12-35 或 12,15,40；默认全部")
    ap.add_argument("--dpi", type=int, default=150,
                    help="渲染分辨率，默认 150。识读命例建议 150–200；再高只是变大")
    ap.add_argument("--gray", action="store_true", help="出灰度图（体积小，二值页无差别）")
    a = ap.parse_args()

    doc = probe(a.pdf)
    if not a.out:
        return
    os.makedirs(a.out, exist_ok=True)
    pages = parse_pages(a.pages, doc.page_count)
    for i in pages:
        pix = doc[i - 1].get_pixmap(dpi=a.dpi, colorspace="gray" if a.gray else None)
        fp = os.path.join(a.out, "p%03d.png" % i)
        pix.save(fp)
        print("  p%03d  %4d×%-4d  %6.1f KB" % (i, pix.width, pix.height,
                                               os.path.getsize(fp) / 1024))
    print("\n共 %d 页 → %s" % (len(pages), a.out))


if __name__ == "__main__":
    main()
