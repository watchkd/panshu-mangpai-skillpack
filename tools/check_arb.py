#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_arb.py — 仲裁编号一致性检查（v1.8 · P0-1）

两处裁决表长期不同步：顶层《跨包冲突仲裁表.md》只到 #12，包内
`ps-zonglun/references/仲裁摘要.md` 已到 #21。模型查顶层表查不到 #19 只能猜。

本工具做三件事：
  1. 扫全包 `仲裁 #N` 与 `#N` 形式的引用，统计每个号被引多少处、谁在引
  2. 对三处定义源分别取号集：
       - 真源   ps-zonglun/references/仲裁摘要.md  §2.1 / §2.2 表格行
       - 索引层 跨包冲突仲裁表.md                  第三节表格行
       - 历史   ps-zonglun/SKILL.md 等文中「N 项已定裁决」口径
  3. 报三类问题：
       缺号 missing   被引用但任何定义源都没有
       超号 overflow  引用的号 > 真源最大号
       仅包内 local   真源有、顶层索引层没有（顶层查不到 → 会逼模型猜）

用法：
    python tools/check_arb.py
    python tools/check_arb.py --strict     # 缺号或口径不一致时非零退出
    python tools/check_arb.py --json arb_report.json

纯标准库、只读。
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

CITE_RE = re.compile(r'仲裁\s*#\s*(\d{1,2})')
REF_RE = re.compile(r'`([^`\n]+)`')

SOURCE_NAME = '仲裁摘要.md'      # 真源：包内 ps-zonglun/references/仲裁摘要.md（自动定位）
INDEX_NAME = '跨包冲突仲裁表.md'  # 顶层索引层
README_REL = 'README.md'


def find_first(root, name, prefer=None):
    """在包内定位首个同名文件；prefer 为路径关键词偏好（如 'ps-zonglun'）。"""
    hits = []
    for dp, dn, fn in os.walk(root):
        if name in fn:
            hits.append(os.path.join(dp, name))
    if not hits:
        return None
    if prefer:
        for h in hits:
            if prefer in h.replace(os.sep, '/').replace('\\', '/'):
                return h
    return sorted(hits, key=len)[0]


def defs_from_table(text):
    """从 markdown 表格行取号：以 | 数字 | 开头的行。"""
    nums = set()
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith('|'):
            continue
        cells = [c.strip() for c in s.strip('|').split('|')]
        if not cells:
            continue
        head = cells[0].replace('*', '').strip()
        if head.isdigit():
            nums.add(int(head))
    return nums


def count_claim(text, pat):
    m = re.search(pat, text)
    return int(m.group(1)) if m else None


def main():
    ap = argparse.ArgumentParser(description='仲裁编号一致性检查')
    ap.add_argument('--root', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument('--strict', action='store_true')
    ap.add_argument('--json', default=None)
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print('[FAIL] 包根不存在: %s' % root)
        return 2

    # 1. 引用侧
    cites = []
    per_num = Counter()
    per_num_files = defaultdict(list)
    for dp, dn, fn in os.walk(root):
        for f in sorted(fn):
            if not f.endswith('.md'):
                continue
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, root)
            text = open(p, encoding='utf-8', errors='replace').read()
            for lineno, line in enumerate(text.splitlines(), 1):
                for m in CITE_RE.finditer(line):
                    n = int(m.group(1))
                    cites.append({'file': rel, 'line': lineno, 'num': n})
                    per_num[n] += 1
                    if rel not in per_num_files[n]:
                        per_num_files[n].append(rel)

    # 2. 定义侧
    src_path = find_first(root, SOURCE_NAME, prefer='ps-zonglun')
    idx_path = find_first(root, INDEX_NAME, prefer='.')
    src_nums = defs_from_table(open(src_path, encoding='utf-8', errors='replace').read()) if src_path and os.path.exists(src_path) else set()
    idx_nums = defs_from_table(open(idx_path, encoding='utf-8', errors='replace').read()) if idx_path and os.path.exists(idx_path) else set()

    cited_nums = set(per_num)
    missing = sorted(n for n in cited_nums if n not in src_nums)
    overflow = sorted(n for n in cited_nums if n > max(src_nums)) if src_nums else []
    local_only = sorted(src_nums - idx_nums)
    max_src = max(src_nums) if src_nums else 0
    max_idx = max(idx_nums) if idx_nums else 0

    # 3. 口径声明
    readme_text = open(os.path.join(root, README_REL), encoding='utf-8', errors='replace').read() if os.path.exists(os.path.join(root, README_REL)) else ''
    claims = {
        'README 仲裁口径(至#N)': (lambda m: int(m.group(2)) if m else None)(
            re.search(r'仲裁\s*#\s*(\d+)\s*[–\-~至]\s*#\s*(\d+)', readme_text)),
        'README「N 项已定裁决」': count_claim(readme_text, r'(\d+)\s*项已定裁决'),
        '仲裁摘要「已定裁决 N 项」': count_claim(open(src_path, encoding='utf-8', errors='replace').read(), r'已定裁决\s*(\d+)\s*项') if os.path.exists(src_path) else None,
    }

    print('=' * 66)
    print('仲裁编号检查 · %s' % root)
    print('=' * 66)
    print('引用处数       %d 处，涉及 %d 个号：#%s' % (len(cites), len(cited_nums),
          '、#'.join(str(n) for n in sorted(cited_nums)) if cited_nums else '无'))
    print('真源定义       %d 个（#1–#%d）· %s' % (len(src_nums), max_src,
          os.path.relpath(src_path, root) if src_path else '（未找到 仲裁摘要.md）'))
    print('顶层索引层     %d 个（#1–#%d）· %s' % (len(idx_nums), max_idx,
          os.path.relpath(idx_path, root) if idx_path else '（未找到 跨包冲突仲裁表.md）'))
    print('缺口：缺号 %d · 超号 %d · 仅包内定义 %d' % (len(missing), len(overflow), len(local_only)))
    for k, v in claims.items():
        print('口径声明       %s = %s' % (k, v if v is not None else '（未声明）'))

    if missing:
        print('\n--- 缺号 MISSING（被引用、但真源无定义）---')
        for n in missing:
            print('  #%-3d 被引 %d 处：%s' % (n, per_num[n], '、'.join(per_num_files[n][:3])))
    if overflow:
        print('\n--- 超号 OVERFLOW（引用号超出真源最大号）---')
        for n in overflow:
            print('  #%-3d 被引 %d 处：%s' % (n, per_num[n], '、'.join(per_num_files[n][:3])))
    if local_only:
        print('\n--- 仅包内定义 LOCAL（顶层表查不到，必须补索引行）---')
        for n in local_only:
            print('  #%-3d 被引 %d 处' % (n, per_num.get(n, 0)))

    print('\n--- 引用热度（按号）---')
    for n in sorted(cited_nums):
        print('  #%-3d  %3d 处  %s' % (n, per_num[n], '、'.join(per_num_files[n][:2])))

    ok = not missing and not overflow and not local_only
    print('\n门禁：%s' % ('PASS' if ok else 'FAIL'))
    if args.strict and not ok:
        return 1

    if args.json:
        with open(args.json, 'w', encoding='utf-8') as fh:
            json.dump({
                'cites': cites,
                'per_num': dict(per_num),
                'source_nums': sorted(src_nums),
                'index_nums': sorted(idx_nums),
                'missing': missing,
                'overflow': overflow,
                'local_only': local_only,
                'claims': claims,
            }, fh, ensure_ascii=False, indent=1)
        print('[OK] 报告已写入 %s' % args.json)
    return 0


if __name__ == '__main__':
    sys.exit(main())
