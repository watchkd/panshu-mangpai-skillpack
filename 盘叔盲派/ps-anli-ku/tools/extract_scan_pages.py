#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描版命理书的页图抽取器（ps-anli-ku · 入库前置）

用途
    把扫描 PDF 里的**页图**原样抽出来，供逐页识字（OCR 引擎或视觉模型）后按
    `references/扫描集入库规范.md` 入库。本器只抽图，**不识字、不入库、不改原文**。

为什么自己写
    本机常无 PyMuPDF / poppler / Ghostscript，但有需要时又不能等环境；
    JPEG（DCTDecode）流在 PDF 里就是完整 JPEG 文件，按字节切出来即可看，无需任何依赖。

能抽什么、不能抽什么（三种压缩）
    DCTDecode      —— JPEG，本器可抽，抽出即成品图。
    CCITTFaxDecode —— 传真压缩（多为 1-bit 黑白扫描），**本器抽不出可用图**，
                      需 Ghostscript / pdftoppm / PyMuPDF 之一渲染。
    JBIG2Decode    —— 二值压缩，**必须专用解码器**，无替代方案。
    无上述三种   —— 多半有文本层（/Font 有值），直接用 `pdftotext` 或 PDF 阅读器复制，
                      不必走 OCR。

用法
    python extract_scan_pages.py 书.pdf                 # 只体检，报可抽性
    python extract_scan_pages.py 书.pdf -o 页图/         # 抽出全部 JPEG 页图
    python extract_scan_pages.py 书.pdf -o 页图/ --first 40 --last 60

输出
    抽出的页图按页码顺序命名 page001.jpg、page002.jpg …
    末尾打印体检表：/DCTDecode /CCITTFaxDecode /JBIG2Decode /JPXDecode /Font 各多少，
    并给「能抽 / 不能抽 / 有文本层」的结论。
"""

import argparse
import os
import re
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

FILTERS = ["DCTDecode", "CCITTFaxDecode", "JBIG2Decode", "JPXDecode", "FlateDecode"]


def probe(d):
    """体检：各类压缩流与字体的计数。"""
    stat = {k: d.count(("/" + k).encode()) for k in FILTERS}
    stat["Font"] = d.count(b"/Font")
    stat["Image"] = d.count(b"/Image")
    return stat


def verdict(stat):
    """按**占比**判，不能因为零星几页 JPEG 就报「可抽」。

    段氏理象学就是这种情形：266 页 CCITT，只夹了 2 页 JPEG——
    按「有 DCT 就算可抽」会得出全书可抽的错结论。
    """
    if stat["Font"] and not stat["Image"]:
        return "有文本层：直接复制文字，不必 OCR"
    comp = [(stat[k], k) for k in ("DCTDecode", "JBIG2Decode",
                                   "CCITTFaxDecode", "JPXDecode")]
    comp.sort(reverse=True)
    top, k = comp[0]
    if top == 0:
        return "未知：未见图像压缩流，请人工看一眼"
    if k == "DCTDecode":
        return "可抽：JPEG 为主（%d 页，本器直接输出）" % top
    hint = {"JBIG2Decode": "JBIG2 二值压缩，须专用解码器",
            "CCITTFaxDecode": "CCITT 传真压缩，须 Ghostscript／pdftoppm／PyMuPDF 渲染",
            "JPXDecode": "JPEG2000，须专用解码器"}[k]
    extra = ("；另夹 %d 页 JPEG 可抽" % stat["DCTDecode"]) if stat["DCTDecode"] else ""
    return "不可抽：%d 页为 %s%s" % (top, hint, extra)


def extract_jpegs(d):
    """按顺序切出所有 DCTDecode（JPEG）流。返回 [bytes…]。"""
    out = []
    off = 0
    while True:
        m = re.search(rb"/DCTDecode", d[off:])
        if not m:
            break
        s = d.find(b"stream", off + m.start())
        if s < 0:
            break
        q = s + 6
        if d[q:q + 2] == b"\r\n":
            q += 2
        elif d[q:q + 1] in (b"\n", b"\r"):
            q += 1
        e = d.find(b"endstream", q)
        if e < 0:
            break
        blob = d[q:e].rstrip(b"\r\n")
        if blob[:2] == b"\xff\xd8":          # JPEG 文件头，确证是成品图
            out.append(blob)
        off = e + 9
    return out


def main():
    ap = argparse.ArgumentParser(description="扫描版 PDF 页图抽取（只抽图，不识字）")
    ap.add_argument("pdf")
    ap.add_argument("-o", "--out", help="页图输出目录（不给则只体检）")
    ap.add_argument("--first", type=int, default=1, help="起始页序（1 起），用于试抽几页")
    ap.add_argument("--last", type=int, default=0, help="结束页序，0 为到末尾")
    a = ap.parse_args()

    if not os.path.exists(a.pdf):
        sys.exit("找不到文件：%s" % a.pdf)
    d = open(a.pdf, "rb").read()
    stat = probe(d)
    v = verdict(stat)

    print("文件：%s（%.1f MB）" % (os.path.basename(a.pdf), len(d) / 1024 / 1024))
    print("体检：", "　".join("%s %d" % (k, stat[k]) for k in
                             ("Image", "DCTDecode", "CCITTFaxDecode",
                              "JBIG2Decode", "JPXDecode", "Font")))
    print("结论：%s" % v)

    if not a.out:
        return 0
    if stat["DCTDecode"] == 0 or stat["DCTDecode"] * 3 < stat["Image"]:
        print("\n本器抽不出这一本。两条路：")
        print("  ① 装 Ghostscript 后 gs -sDEVICE=png16m -r300 -o 页-%03d.png 书.pdf，再逐页识字；")
        print("  ② 换一本 DCTDecode 扫描的书（如《盲人铁口断》），或找该书的文字版／PDF 文字层。")
        return 2

    pages = extract_jpegs(d)
    os.makedirs(a.out, exist_ok=True)
    last = a.last or len(pages)
    n = 0
    for i, blob in enumerate(pages, 1):
        if i < a.first or i > last:
            continue
        open(os.path.join(a.out, "page%03d.jpg" % i), "wb").write(blob)
        n += 1
    print("已抽 %d 页 → %s（共 %d 页可抽）" % (n, a.out, len(pages)))
    print("下一步：逐页识字后按 references/扫描集入库规范.md 填表；"
          "四柱一律过形近字校正（巳/己/已、戌/戍、未/末、酉/西、卯/印）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
