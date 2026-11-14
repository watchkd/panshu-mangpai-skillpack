#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盘叔盲派 · 命例四柱校验器（ps-anli-ku）

录入扫描案例集时，书上的「四柱」与「出生日期」**经常互相矛盾**——排印错、
扫描错、识读错、或日期本是农历却按公历理解。本器把两者都过一遍，
告诉你哪一柱对不上，**不替你改书，只报差**。

## 为什么必须有这一步

《盲派批命案例集》第一单元 22 例里，凡给出生日的 8 例，按公历排**一例都对不上**；
按农历排 6 例四柱全合（含时柱）——即该书日期为农历。若不查，整批应期全错。

## 用法

    # 单例：书四柱 + 书上日期（默认按农历解释）
    python verify_case.py --pillars 丙申 辛丑 戊戌 甲寅 --date 1956-12-26 --time 04:00

    # 按公历解释
    python verify_case.py --pillars 甲子 乙亥 庚戌 癸未 --date 1984-12-05 --time 22:00 --solar

    # 只给四柱、不给日期：反查 1880–2030 年间所有可能的出生日
    python verify_case.py --pillars 戊午 乙丑 庚戌 壬午 --resolve

## 退出码
0 相符 · 1 不符（打印逐柱差异） · 2 无法判断（缺日期且未反查）
"""
import argparse
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PAIPAN_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "ps-zonglun", "tools"))
sys.path.insert(0, PAIPAN_DIR)
try:
    import paipan as P            # noqa: E402
except ImportError:
    sys.exit("找不到排盘器：%s\nps-anli-ku 须与 ps-zonglun 同级。" % PAIPAN_DIR)

SHI = {"子": "00:30", "丑": "02:30", "寅": "04:30", "卯": "06:30",
       "辰": "08:30", "巳": "10:30", "午": "12:30", "未": "14:30",
       "申": "16:30", "酉": "18:30", "戌": "20:30", "亥": "22:30"}
POS = ["年", "月", "日", "时"]


def hour_to_hh(h):
    """把「午时／午／12:00」都收成 HH:MM。"""
    if not h:
        return "12:00"
    h = h.strip()
    if ":" in h:
        return h
    return SHI.get(h.replace("时", ""), "12:00")


def calc(date_obj, hh):
    return P.paipan(date_obj, hh, "男")["pillars"]


def compare(book, got):
    rows = []
    for i in range(4):
        rows.append((POS[i], book[i], got[i], "✓" if book[i] == got[i] else "✗"))
    diff = [r for r in rows if r[3] == "✗"]
    return rows, diff


def resolve(book, y0, y1):
    """按年柱锁定年份、逐日反查前三柱（时柱另核）。"""
    out = []
    for y in range(y0, y1 + 1):
        if P.JIAZI[(y - 1984) % 60] != book[0]:
            continue
        d = datetime.date(y, 1, 1)
        while d < datetime.date(y + 1, 2, 10):
            if calc(d, "12:00")[:3] == book[:3]:
                out.append(d)
            d += datetime.timedelta(days=1)
    return out


def main():
    ap = argparse.ArgumentParser(description="命例四柱校验：书上的柱与日期对不对得上")
    ap.add_argument("--pillars", nargs=4, required=True, metavar="柱",
                    help="书上四柱，按年 月 日 时")
    ap.add_argument("--date", help="书上生日 YYYY-MM-DD")
    ap.add_argument("--time", default="12:00", help="时辰，如 午时／午／12:00")
    ap.add_argument("--solar", action="store_true", help="日期按公历解（默认农历）")
    ap.add_argument("--resolve", action="store_true", help="不给日期，反查可能生日")
    ap.add_argument("--from", dest="y0", type=int, default=1880)
    ap.add_argument("--to", dest="y1", type=int, default=2030)
    a = ap.parse_args()

    book = a.pillars
    for g in book:
        if g not in P.JIAZI:
            sys.exit("「%s」不是合法干支" % g)

    if a.resolve or not a.date:
        if not a.resolve:
            print("未给日期，自动转入反查（--from %d --to %d）" % (a.y0, a.y1))
        hits = resolve(book, a.y0, a.y1)
        if not hits:
            print("四柱：%s" % "　".join(book))
            print("结论：**全区间无解**——四柱本身不自洽，或有一二字识读错。"
                  "此类须回原页放大重读，不得直接入库。")
            return 1
        print("四柱：%s" % "　".join(book))
        print("反查得 %d 个可能生日（前三柱相符）：" % len(hits))
        for d in hits[:12]:
            try:
                from lunardate import LunarDate
                lun = LunarDate.fromSolarDate(d.year, d.month, d.day)
                lun_s = "农历 %d-%02d-%02d" % (lun.year, lun.month, lun.day)
            except Exception:
                lun_s = ""
            print("   %s　%s" % (d, lun_s))
        if len(hits) > 12:
            print("   ……（余 %d 个）" % (len(hits) - 12))
        print("\n提示：命中多个时，用书上「大运起岁」与「时辰」再收窄。")
        return 0

    y, m, dd = map(int, a.date.split("-"))
    hh = hour_to_hh(a.time)
    src = "公历" if a.solar else "农历"
    if a.solar:
        sol = datetime.date(y, m, dd)
    else:
        try:
            from lunardate import LunarDate
        except ImportError:
            sys.exit("农历换算需 lunardate：pip install lunardate "
                     "-i https://mirrors.aliyun.com/pypi/simple/")
        sol = LunarDate(y, m, dd, 0).to_solar_date()

    got = calc(sol, hh)
    rows, diff = compare(book, got)
    print("书　四柱：%s" % "　".join(book))
    print("日期　　：%s %d-%02d-%02d %s（%s）→ 公历 %s" % (
        src, y, m, dd, a.time, hh, sol))
    print("器　四柱：%s" % "　".join(got))
    print("-" * 34)
    for p, b, g, ok in rows:
        print("%s柱　书 %s　器 %s　%s" % (p, b, g, ok))
    if not diff:
        print("\n结论：**相符**（四柱全合）")
        return 0
    print("\n结论：**不符**，差在 %s 柱。三种可能，须逐条排除：" %
          "、".join(r[0] for r in diff))
    print("  ① 日期历法搞错（农历／公历混用）——换 --solar 再跑一次")
    print("  ② 书上排印错，或扫描／识读错——回原页放大重读那一柱")
    print("  ③ 案例本身如此（作者按自己的口径排）——入库时标「书柱存疑」，不改书")
    return 1


if __name__ == "__main__":
    sys.exit(main())
