#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""case_index.py — 命例检索层（v1.8 · P0-3）

读 `references/cases.json`（索引层，不是正文），按标签／关键词／四柱／性别检索命例，
打印命中的「编号＋摘要＋出处」，由你回出处文件取全文。

设计原则：
    1. **索引层只做定位**，不复制正文——避免同一句话两处维护、两处不一致。
    2. 命例全部为**事后追认**（已知结果倒推），只作佐证／类比，**不作准确率依据**。
    3. ps-anli-ku 267 条为索引级（正文未随包，见包根《引用未随包清单.md》），
       S-GD 22 例为全文入库（可直接回 references/案例集_高德臣_第一单元.md）。

用法：
    python tools/case_index.py                          # 看总量与标签分布
    python tools/case_index.py --tag 婚姻               # 按领域标签（多个=AND）
    python tools/case_index.py --kw 总统                # 摘要关键词（多个=OR，空格分隔）
    python tools/case_index.py --pillars 丙申辛丑戊戌甲寅  # 按四柱（仅全文入库条目有柱）
    python tools/case_index.py --sex 坤 --tag 婚姻 --limit 5
    python tools/case_index.py --id S-GD-016
    python tools/case_index.py --json hit.json          # 落机读结果

纯标准库、只读。
"""

import argparse
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_JSON = os.path.join(os.path.dirname(HERE), 'references', 'cases.json')

GAN = '甲乙丙丁戊己庚辛壬癸'
ZHI = '子丑寅卯辰巳午未申酉戌亥'


def norm(s):
    """去空白与分隔符，用于四柱比对（全角空格、顿号、逗号一律吃掉）。"""
    if not s:
        return ''
    for ch in ' \t\u3000，,、/|':
        s = s.replace(ch, '')
    return s


def load(path):
    if not os.path.exists(path):
        print('[FAIL] 找不到 %s' % path)
        sys.exit(2)
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def match_pillars(case_pillars, want):
    """四柱匹配：先比全串，再比干支集合（顺序无关，容 OCR 柱序差）。"""
    cp, wp = norm(case_pillars), norm(want)
    if not cp or not wp:
        return False
    if cp == wp:
        return True
    if len(wp) == 2:          # 只给一柱：出现在该造四柱里即算
        return wp in cp
    # 干支对集合比对（每柱两位）
    a = {cp[i:i + 2] for i in range(0, min(len(cp), 8), 2)}
    b = {wp[i:i + 2] for i in range(0, len(wp), 2)}
    return bool(b) and b.issubset(a)


def main():
    ap = argparse.ArgumentParser(description='命例检索层（索引级）')
    ap.add_argument('--json', default=DEFAULT_JSON, help='cases.json 路径')
    ap.add_argument('--tag', action='append', default=[], help='领域标签，多个为 AND')
    ap.add_argument('--kw', default=None, help='摘要关键词，空格分隔（OR）')
    ap.add_argument('--pillars', default=None, help='四柱，如 丙申辛丑戊戌甲寅 或单柱 戊戌')
    ap.add_argument('--sex', default=None, choices=['乾', '坤', '乾造', '坤造'], help='性别')
    ap.add_argument('--system', default=None, help='体系（ps-anli-ku / S-GD）')
    ap.add_argument('--id', default=None, help='精确编号，如 S-GD-016 或 GD16')
    ap.add_argument('--limit', type=int, default=15, help='最多打印条数（默认 15）')
    ap.add_argument('--out', default=None, help='把命中结果写成 json')
    args = ap.parse_args()

    data = load(args.json)
    cases = data['cases']
    meta = data.get('meta', {})

    if not any([args.tag, args.kw, args.pillars, args.sex, args.system, args.id]):
        print('=' * 66)
        print('命例索引层 · %s · 共 %d 条' % (meta.get('version', '?'), len(cases)))
        print('=' * 66)
        for k, v in (meta.get('systems') or {}).items():
            print('  %-12s %s' % (k, v))
        print('\n标签分布（多标签，可叠加）：')
        for t, n in Counter(t for c in cases for t in c.get('tags') or []).most_common():
            print('  %-8s %4d' % (t, n))
        print('\n有完整四柱（可做四柱检索）的仅 S-GD 全文入库条目；'
              'ps-anli-ku 速查表只给造与断语，属索引级。')
        print('\n常用：--tag 婚姻 ｜ --kw 总统 ｜ --pillars 戊戌 ｜ --id S-GD-016')
        return 0

    hits = []
    for c in cases:
        if args.id and c['id'].lower() != args.id.lower():
            continue
        if args.system and args.system not in c.get('system', ''):
            continue
        if args.sex and not c.get('sex', '').startswith(args.sex[:1]):
            continue
        if args.tag and not set(c.get('tags') or []).issuperset(set(args.tag)):
            continue
        if args.kw:
            words = [w for w in args.kw.split() if w]
            if words and not any(w in c.get('summary', '') for w in words):
                continue
        if args.pillars and not match_pillars(c.get('pillars', ''), args.pillars):
            continue
        hits.append(c)

    print('=' * 66)
    print('命中 %d 条（共 %d 条）' % (len(hits), len(cases)))
    print('=' * 66)
    for c in hits[:args.limit]:
        tags = '/'.join(c.get('tags') or []) or '-'
        sex = c.get('sex') or '未标'
        pil = c.get('pillars') or '未载柱'
        print('\n[%s] %s · %s · %s' % (c['id'], c.get('system', ''), sex, pil))
        print('  标签：%s' % tags)
        print('  摘要：%s' % c.get('summary', ''))
        print('  出处：%s（%s）' % (c.get('source', ''), c.get('grade', '')))
    if len(hits) > args.limit:
        print('\n…… 另有 %d 条未打印（--limit 调大，或 --out 落 json）' % (len(hits) - args.limit))
    print('\n提醒：命例全部为事后追认，只作佐证／类比，不作准确率依据（仲裁 #18 体系列不得混用）。')

    if args.out:
        with open(args.out, 'w', encoding='utf-8') as fh:
            json.dump({'query': vars(args), 'count': len(hits), 'hits': hits}, fh,
                      ensure_ascii=False, indent=1)
        print('[OK] 结果已写入 %s' % args.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
