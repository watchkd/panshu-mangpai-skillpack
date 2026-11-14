#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_yingqi.py — 应期自洽体检（v1.8 · P1-6）

断语文档最容易出的三类硬伤，全部是「一查就知道」的机械问题，不需要懂命理：

    R1 年份干支不合   文中「1993 年」与「癸酉年」写在一处，干支与年份实际不符
    R2 断语落到日     仲裁 #20：段派到年月、夏派到月，**均不到日**；
                      凡断语给到「某月某日」「初五」，须显式标派系来源（高派／扫描集实录除外）
    R3 交运未说并存   出现「五年一交」却未在同一段说明「前五年天干主事、后五年地支主事」
                      （v1.8 · P1-5 新口径：两段并存，不得只讲一截）

**不检查**：判断吉凶对错、规则是否适用——那是断法层的事，脚本不管。

用法：
    python tools/check_yingqi.py                    # 只扫断语文档（批词／命书／体例）
    python tools/check_yingqi.py --all              # 扫全包 md
    python tools/check_yingqi.py --only 盘叔盲派/ps-zonglun
    python tools/check_yingqi.py --strict           # 有 R1 时非零退出（R2/R3 只提示）
    python tools/check_yingqi.py --verbose

纯标准库、只读。
"""

import argparse
import os
import re
import sys
from collections import Counter, defaultdict

GAN = '甲乙丙丁戊己庚辛壬癸'
ZHI = '子丑寅卯辰巳午未申酉戌亥'

YEAR_NAMED = re.compile(r'(\d{4})\s*年')
YEAR_GANZHI = re.compile(r'([' + GAN + r'])([' + ZHI + r'])\s*年')
# 日期形态（只认明确的「某月某日／初X／廿X」，不认「日主／日支／月日之间」这类术语）
# 同指写法：2005年乙酉年 / 2005 年（乙酉年）
YEAR_THEN_GZ = re.compile(r'(\d{4})\s*年\s*[（(【\[]?\s*([甲乙丙丁戊己庚辛壬癸])([子丑寅卯辰巳午未申酉戌亥])\s*年')
# 反序同指：乙酉年（2005年）
GZ_THEN_YEAR = re.compile(r'([甲乙丙丁戊己庚辛壬癸])([子丑寅卯辰巳午未申酉戌亥])\s*年\s*[（(【\[]\s*(\d{4})\s*年')

DAY_LEVEL = re.compile(
    r'(\d{1,2}\s*月\s*\d{1,2}\s*日)'
    r'|(月\s*[初廿]?[一二三四五六七八九十百\d]{1,3}\s*日)'
    r'|(?<![日月年])(初[一二三四五六七八九十]{1,3}|廿[一二三四五六七八九十]{1,3})')
CALENDAR_WORDS = ('交入', '交运', '交脱', '节气', '立春', '惊蛰', '清明', '立夏', '芒种', '小暑', '立秋',
                  '白露', '寒露', '立冬', '大雪', '小寒', '大寒', '雨水', '春分', '谷雨', '小满', '夏至',
                  '大暑', '处暑', '秋分', '霜降', '小雪', '冬至', '出生', '生于', '排盘', '起运', '换月')
SCHOOL_WORDS = ('夏派', '高派', '铁口', '扫描集', '实录', '反馈', '原书', '书载')
COEXIST_WORDS = ('前五年', '后五年', '天干主事', '地支主事', '前后两截', '两截',
                 '天干段', '地支段', '干段', '支段', '前段', '后段')
# 月建区间写法（卯月：三月五日—四月五日）属历法边界，不算断语到日
MONTH_SPAN = re.compile(
    r'[一二三四五六七八九十\d]{1,3}\s*月\s*[一二三四五六七八九十廿初\d]{1,3}\s*日'
    r'\s*[—–\-~至]\s*'
    r'[一二三四五六七八九十\d]{1,3}\s*月\s*[一二三四五六七八九十廿初\d]{1,3}\s*日')
SKIP_PREFIX = ('升级说明_',)
# 生日／书上生时／命例编号上下文：这里的「某月某日」是排盘输入，不是应期断语
BIRTH_CTX = re.compile(r'(生于|出生|时生|日生|乾造|坤造|例\s*\d{1,3}|生日)')

# 断语文档识别：文件名或路径含这些词的，默认纳入
TARGET_HINTS = ('批词', '命书', '体例', '范例', '话术', '报告')
# 原书命例／扫描集实录：本来就可能断到日，属「引原文」，不计门禁，只作巡检提示
ORIGINAL_HINTS = ('命例', '案例集', '命例库')


def gan_zhi_of_year(y):
    """公历年 → 年干支（以立春为界的近似：公历年按 1984=甲子 计，立春前属前一年，故只作粗校验）。"""
    idx = (y - 1984) % 60
    return GAN[idx % 10] + ZHI[idx % 12]


def check_file(path, rel):
    issues = []
    is_original = any(h in rel for h in ORIGINAL_HINTS)
    lines = open(path, encoding='utf-8', errors='replace').read().splitlines()
    for i, line in enumerate(lines, 1):
        if not line.strip() or line.lstrip().startswith('>'):
            continue
        # R1：只校验「同指」写法（2005年乙酉年 / 乙酉年（2005年））；
        #     不做句内笛卡尔配对——一句里常同时出现多个年份与多个运干支，那样全是误报。
        for m in YEAR_THEN_GZ.finditer(line):
            y, g, z = m.group(1), m.group(2), m.group(3)
            calc = gan_zhi_of_year(int(y))
            if g + z != calc:
                issues.append(('R1', rel, i, 'R1 年份干支不合：「%s 年」应为「%s」，实写「%s」%s'
                               % (y, calc, g + z, '（立春前后可能属相邻年，须人工核）')))
        for m in GZ_THEN_YEAR.finditer(line):
            g, z, y = m.group(1), m.group(2), m.group(3)
            calc = gan_zhi_of_year(int(y))
            if g + z != calc:
                issues.append(('R1', rel, i, 'R1 年份干支不合：「%s 年」应为「%s」，实写「%s」%s'
                               % (y, calc, g + z, '（立春前后可能属相邻年，须人工核）')))
        # R2：断语到日（月建区间写法属历法边界，跳过）
        if DAY_LEVEL.search(line) and any(k in line for k in ('年', '月')) \
                and not MONTH_SPAN.search(line) and not BIRTH_CTX.search(line):
            if not any(k in line for k in CALENDAR_WORDS) and not any(k in line for k in SCHOOL_WORDS):
                issues.append(('R2', rel, i, 'R2 断语疑似落到「日」：仲裁 #20 段派到年月、夏派到月，须标派系来源'))
        # R3：交运并存
        if ('五年一交' in line or '五年一运' in line) and not any(k in line for k in COEXIST_WORDS):
            issues.append(('R3', rel, i, 'R3 提到「五年一交」但未说明「前五年天干／后五年地支」并存（P1-5 口径）'))
    if is_original:
        # 原书命例／扫描集：断到日属「引原文实录」，降级为巡检提示，不进 R1/R2/R3 门禁
        issues = [(r + 'o', f, l, m.replace('断语疑似落到「日」', '原书记录断到日')) for r, f, l, m in issues]
    return issues


def scan(root, only=None, scan_all=False):
    """遍历包内 md，返回 (scanned, issues)；main 与 self_test 共用同一套筛选口径。"""
    scan_root = os.path.join(root, only) if only else root
    if not os.path.isdir(scan_root):
        return -1, []
    scanned = 0
    issues = []
    for dp, dn, fn in os.walk(scan_root):
        for f in sorted(fn):
            if not f.endswith('.md'):
                continue
            path = os.path.join(dp, f)
            rel = os.path.relpath(path, root)
            if any(f.startswith(x) for x in SKIP_PREFIX):
                continue
            if not scan_all and not any(h in rel for h in TARGET_HINTS):
                continue
            scanned += 1
            issues.extend(check_file(path, rel))
    return scanned, issues


def self_test():
    """自测（v1.8 · P1-6）：3 个错例须全抓，包内断语文档（含范例盘）须零误报。"""
    import tempfile
    bad = []
    cases = [
        ('R1', '1993 年丙子年交第一次运，此后每五年一交：前五年天干主事、后五年地支主事。'),
        ('R2', '丁卯运里，1995 年三月十七日见合，事在文书。'),
        ('R3', '这一步五年一交，一交就是一大变。'),
    ]
    tmp = tempfile.mkdtemp(prefix='yingqi_selftest_')
    for want, text in cases:
        p = os.path.join(tmp, '批词_自测错例_%s.md' % want)
        with open(p, 'w', encoding='utf-8') as fh:
            fh.write(text + '\n')
        got = [r for r, *_ in check_file(p, 'self_test/批词_错例_%s.md' % want)]
        if want not in got:
            bad.append('错例 %s 未抓到（实得 %s）：%s' % (want, got or '无', text[:18]))
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    scanned, issues = scan(root)
    if scanned < 0:
        bad.append('包根不存在，无法做零误报检查')
    for rule in ('R1', 'R2', 'R3'):
        hit = [x for x in issues if x[0] == rule]
        if hit:
            bad.append('范例盘误报 %s %d 处，首例 %s:%s' % (rule, len(hit), hit[0][1], hit[0][2]))
    if bad:
        print('自检 FAIL：')
        for b in bad:
            print('  - %s' % b)
        return 1
    print('自检 PASS（错例 3/3 全抓；断语文档 %d 个，R1／R2／R3 零误报）' % scanned)
    return 0


def main():
    ap = argparse.ArgumentParser(description='应期自洽体检（R1 年份干支／R2 到日／R3 交运并存）')
    ap.add_argument('--root', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help='技能包根目录（默认脚本上一级）')
    ap.add_argument('--only', default=None, help='只扫该子目录（相对包根）')
    ap.add_argument('--all', action='store_true', help='扫全包 md（默认只扫断语文档）')
    ap.add_argument('--strict', action='store_true', help='有 R1 时非零退出')
    ap.add_argument('--verbose', action='store_true', help='连 R2／R3 也逐条打印')
    ap.add_argument('--json', default=None, help='把结果写成 json')
    ap.add_argument('--self-test', action='store_true',
                    help='自测：造 R1/R2/R3 三个错例须全抓，包内断语文档须零误报')
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print('[FAIL] 包根不存在: %s' % root)
        return 2
    scanned, all_issues = scan(root, args.only, args.all)
    if scanned < 0:
        print('[FAIL] --only 目录不存在: %s' % os.path.join(root, args.only))
        return 2

    by_rule = Counter(r for r, *_ in all_issues)
    per_file = defaultdict(int)
    for _, rel, _, _ in all_issues:
        per_file[rel] += 1

    print('=' * 70)
    print('应期自洽体检 · %s' % root)
    print('=' * 70)
    print('扫描文档   %d 个（%s）' % (scanned, '全包' if args.all else '断语文档'))
    print('R1 年份干支不合  %3d 处  （硬伤，须清零）' % by_rule.get('R1', 0))
    print('R2 断语落到日    %3d 处  （须标派系来源，可接受但须显式）' % by_rule.get('R2', 0))
    print('R3 交运未说并存  %3d 处  （P1-5 口径，须补一句）' % by_rule.get('R3', 0))
    n_orig = sum(v for k, v in by_rule.items() if k.endswith('o'))
    if n_orig:
        print('原书记录提示    %3d 处  （命例库／扫描集引原文，断到日属实录，不计门禁）' % n_orig)
    if args.strict:
        print('门禁：--strict %s' % ('PASS' if by_rule.get('R1', 0) == 0 else 'FAIL'))

    for rule, title in (('R1', 'R1 年份干支不合'), ('R2', 'R2 断语落到日'), ('R3', 'R3 交运未说并存')):
        items = [x for x in all_issues if x[0] == rule]
        if not items:
            continue
        if rule != 'R1' and not args.verbose:
            print('\n--- %s：%d 处（--verbose 看明细）---' % (title, len(items)))
            for it in items[:5]:
                print('  %s:%d  %s' % (it[1], it[2], it[3]))
            if len(items) > 5:
                print('  …… 另有 %d 处' % (len(items) - 5))
            continue
        print('\n--- %s：%d 处 ---' % (title, len(items)))
        for it in items:
            print('  %s:%d  %s' % (it[1], it[2], it[3]))

    if per_file:
        print('\n--- 按文件 ---')
        for rel, n in sorted(per_file.items(), key=lambda kv: -kv[1])[:15]:
            print('  %3d  %s' % (n, rel))

    if args.json:
        with open(args.json, 'w', encoding='utf-8') as fh:
            import json as _json
            _json.dump({'scanned': scanned, 'summary': dict(by_rule),
                        'issues': [{'rule': r, 'file': f, 'line': l, 'msg': m} for r, f, l, m in all_issues]},
                       fh, ensure_ascii=False, indent=1)
        print('\n[OK] 报告已写入 %s' % args.json)

    if args.strict and by_rule.get('R1', 0) > 0:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
