#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_anchor.py — 行号回读校验（v1.9 · P1-4）

v1.8 出门验收留了一条尾巴：报告与文档里写了「某文件:某行」作证据，但没回读过——
行号可能因后续改动而漂移，读者按号翻过去会翻到别的段落。

本工具把这类「文件:行」锚点全扫出来，逐条回读，判三档：

    HIT     文件在包内、行号在该文件行数范围内 —— 可回读
    DRIFT   文件在、行号越界（超出总行数或为 0）—— 行号漂了，须改
    LOST    文件在包内找不到 —— 锚点失效

用法：
    python tools/check_anchor.py                       # 全包体检（默认扫 .md）
    python tools/check_anchor.py --sample 20           # 随机抽 20 条回显该行原文
    python tools/check_anchor.py --strict              # LOST+DRIFT > 0 时非零退出
    python tools/check_anchor.py --only output         # 只体检某个子目录
    python tools/check_anchor.py --json anchor.json    # 落机读报告

纯标准库、只读、不联网。
"""

import argparse
import json
import os
import random
import re
import sys
from collections import Counter, defaultdict

# 形如 `盘叔盲派/ps-zhenjue-duanju/SKILL.md:247`、`tools/check_refs.py:12`
ANCHOR_RE = re.compile(r'`([^`\n]*?\.(?:md|py|json|txt|html|yml|yaml)):(\d{1,5})`')

# 只看包内文件作为锚点目标，排除自身产出报告
SKIP_DIRS = {'_溯源', 'temp', '.git'}


def read_lines(path):
    try:
        with open(path, encoding='utf-8') as fh:
            return fh.read().splitlines()
    except (UnicodeDecodeError, OSError):
        return None


def build_index(root):
    """basename -> [路径...]，用于「只写文件名」的简写锚点。"""
    idx = defaultdict(list)
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fn:
            idx[f].append(os.path.join(dp, f))
    return idx


def locate(target, md_dir, root, index):
    """按人类回读习惯逐级找目标文件，返回 (绝对路径 或 None, 解析方式)。"""
    for base, how in ((root, '包根'), (os.path.join(root, '盘叔盲派'), '盘叔盲派/'),
                      (md_dir, '同目录')):
        p = os.path.normpath(os.path.join(base, target))
        if os.path.exists(p):
            return p, how
    hits = index.get(os.path.basename(target)) or []
    if len(hits) == 1:
        return hits[0], '包内同名'
    return None, ('包内同名多义%d' % len(hits) if hits else '找不到')


def main():
    ap = argparse.ArgumentParser(description='行号回读校验')
    ap.add_argument('--root', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument('--only', default=None)
    ap.add_argument('--strict', action='store_true')
    ap.add_argument('--sample', type=int, default=0, help='抽样回显条数')
    ap.add_argument('--json', default=None)
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    scan_root = os.path.join(root, args.only) if args.only else root
    if not os.path.isdir(scan_root):
        print('[FAIL] 目录不存在: %s' % scan_root)
        return 2

    rows, lost, drift = [], [], []
    index = build_index(root)
    for dp, dn, fn in os.walk(scan_root):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in sorted(fn):
            if not f.endswith('.md'):
                continue
            md = os.path.join(dp, f)
            text = read_lines(md)
            if text is None:
                continue
            rel_md = os.path.relpath(md, root).replace(os.sep, '/')
            for lineno, line in enumerate(text, 1):
                for m in ANCHOR_RE.finditer(line):
                    target, num = m.group(1).strip(), int(m.group(2))
                    status, total, content = 'HIT', 0, ''
                    cand, how = locate(target, dp, root, index)
                    tl = read_lines(cand) if cand else None
                    if tl is None:
                        # 「同理 `命例.md:319`」这类只写文件名的简写，包内同名多份时
                        # 无法自动消歧——不是断链，但也回读不到唯一目标，单列 AMBIG。
                        status = 'AMBIG' if how.startswith('包内同名多义') else 'LOST'
                    else:
                        total = len(tl)
                        if num <= 0 or num > total:
                            status = 'DRIFT'
                        else:
                            content = tl[num - 1].strip()[:100]
                    row = {'file': rel_md, 'line': lineno, 'anchor': m.group(0),
                           'target': target, 'target_line': num, 'total': total,
                           'status': status, 'how': how,
                           'resolved': os.path.relpath(cand, root).replace(os.sep, '/') if cand else '',
                           'content': content}
                    rows.append(row)
                    if status == 'LOST':
                        lost.append(row)
                    elif status == 'DRIFT':
                        drift.append(row)

    by = Counter(r['status'] for r in rows)
    print('=' * 66)
    print('行号回读校验 · %s' % root)
    print('=' * 66)
    print('扫描锚点 %d 处（去重 %d）' % (len(rows), len({r['anchor'] for r in rows})))
    print('  可回读 HIT    %5d 处' % by.get('HIT', 0))
    print('  行号漂移 DRIFT %4d 处  （越界，须改）' % by.get('DRIFT', 0))
    print('  简写多义 AMBIG %4d 处  （只写文件名、包内同名，须补全路径才能回读）' % by.get('AMBIG', 0))
    print('  文件缺失 LOST  %4d 处  （锚点失效）' % by.get('LOST', 0))
    if args.strict:
        ok = not lost and not drift
        print('  门禁：--strict %s' % ('PASS' if ok else 'FAIL'))

    for title, items in (('行号漂移', drift), ('文件缺失', lost)):
        if not items:
            continue
        print('\n--- %s（%d 处）---' % (title, len(items)))
        for r in items[:20]:
            print('  %s:%d  %s  (总行数 %d)' % (r['file'], r['line'], r['anchor'], r['total']))
        if len(items) > 20:
            print('  …… 另有 %d 处' % (len(items) - 20))

    if args.sample and rows:
        n = min(args.sample, len(rows))
        picks = random.sample([r for r in rows if r['status'] == 'HIT'], n) if by.get('HIT', 0) >= n else \
            random.sample(rows, n)
        print('\n--- 抽样回读 %d 条 ---' % len(picks))
        for r in picks:
            print('  %s:%d  %s' % (r['file'], r['line'], r['anchor']))
            print('      └ 第 %d 行：%s' % (r['target_line'], r['content']))

    if args.json:
        with open(args.json, 'w', encoding='utf-8') as fh:
            json.dump({'root': root, 'summary': dict(by), 'rows': rows}, fh,
                      ensure_ascii=False, indent=1)
        print('\n[OK] 报告已写入 %s' % args.json)

    if args.strict and (lost or drift):
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
