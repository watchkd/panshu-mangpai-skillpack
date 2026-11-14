#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_refs.py — 技能包引用体检（v1.8 · P0-1）

扫全包 .md 里的反引号路径引用，按**三级解析**判定能不能真翻到：

    一级：同目录        —— 相对引用所在 md 的目录
    二级：包内同名      —— 包内任意位置存在同名文件（唯一才算，多义单列）
    三级：包根          —— 相对技能包根目录

三类结果：
    可解析   OK         三级任一命中
    未随包   WORKSPACE  命中原蒸馏期工作区路径（候选/ 、_draft/ 、骨架.md 等），
                        这类引用不是写错，是文件从来没随包发布
    真错     BROKEN     三级皆不命中，且不像工作区路径 —— 这才是要清零的

用法：
    python tools/check_refs.py                  # 全包体检，打印汇总与前 30 条真错
    python tools/check_refs.py --strict         # 真错 > 0 时非零退出（CI/出门验收用）
    python tools/check_refs.py --verbose        # 逐条列出，不分层折叠
    python tools/check_refs.py --only 盘叔盲派/ps-anli-ku   # 只体检某个子包
    python tools/check_refs.py --json refs_report.json      # 落一份机读报告

纯标准库、不联网、只读，不改任何文件。
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

REF_RE = re.compile(r'`([^`\n]+)`')

EXTS = ('.md', '.py', '.json', '.html', '.txt', '.csv', '.jpg', '.jpeg', '.png', '.svg', '.rar', '.zip')

# 蒸馏期工作区目录名（首段命中即算「未随包」）
WORKSPACE_DIRS = {'候选', '_draft', '工作区', '_工作区', 'draft', '_融合工作区', 'mingxue-zhendian', '其他参考书目'}

# 溯源区目录名（v1.9 增）：收录蒸馏期工作稿，引用命中即算「已随包可核对」
SRC_DIR = '_溯源'

# 本工具自身产出的清单文件，扫描时排除（否则清单表格会被当成正文引用扫成真错）
SKIP_FILES = {'引用未随包清单.md'}

# 工作区散装文件（basename 命中即算「未随包」）
WORKSPACE_FILES = {
    # 复核/裁决/清单类
    '原文复核报告.md', '冲突裁决记录.md', '跨包冲突仲裁表_v2.md',
    '命例库_合一_全体系.md', '骨架.md', '清单.md', '状态.md', '候选规则清单.md',
    '命例去重报告.md', '规则去重报告.md', '差异表.md',
    # 蒸馏器与提取规范（工作区工具，未随包）
    'bazi-model.md', 'extractor-bazi-case.md', 'extractor-bazi-pattern.md',
    '_validate_report.txt',
    # 分批验证产物
    '验证_规则_批1.md', '验证_规则_批2.md', '验证_规则_批34.md', '验证_规则_批5.md',
    # 原书全文（版权原因不随包）
    '中级命理学_全文.txt', '高级面授笔记_全文.txt',
}

# 明显不是路径的字符（含空格、标签箭头、书名号、中文标点等一律跳过）
NOT_PATH_CHARS = set(' \t>｜|《》「」【】（）()：:；;，,、！!？?“”"\'*~=\u3000')


def looks_like_ref(s):
    """判断反引号里的内容是不是一个路径引用。"""
    s = s.strip()
    if not s or len(s) > 160:
        return False
    if any(ch in NOT_PATH_CHARS for ch in s):
        return False
    if s.startswith(('http://', 'https://', 'python ', 'pip ', 'git ', '--')):
        return False
    if any(s.lower().endswith(e) for e in EXTS):
        return True
    if s.endswith('/'):
        return True
    return False


def build_index(root):
    """basename -> [绝对路径, ...]，用于二级解析。"""
    index = defaultdict(list)
    for dp, dn, fn in os.walk(root):
        for f in fn:
            index[f].append(os.path.join(dp, f))
    return index


def _subpkg_of(rel_path):
    """从引用所在文件的相对路径里取所属子技能包名（ps-xxx），取不到返回 _shared。"""
    m = re.search(r'(ps-[a-z0-9\-]+)', rel_path.replace(os.sep, '/'))
    return m.group(1) if m else '_shared'


def resolve_sourced(ref_clean, rel_md, root):
    """溯源区解析（v1.9 增）：_溯源/<子包>/<ref> 或 _溯源/_shared/<ref>。

    溯源区收录的是蒸馏期工作稿，用于「当时的依据从哪来」的核对；
    命中不算未随包，但**也不等同包内正式依据**，故单列 SOURCED。
    """
    src_root = os.path.join(root, SRC_DIR)
    if not os.path.isdir(src_root):
        return None
    for sp in (_subpkg_of(rel_md), '_shared'):
        cand = os.path.normpath(os.path.join(src_root, sp, ref_clean))
        if os.path.exists(cand) and cand.startswith(os.path.normpath(src_root) + os.sep):
            return cand
    return None


def resolve(ref, md_dir, root, index, skill_dirs, rel_md=''):
    """解析。返回 (状态, 落点, 方式)。"""
    ref_clean = ref.rstrip('/')
    is_dir_ref = ref.endswith('/')
    # 一级：同目录
    p1 = os.path.normpath(os.path.join(md_dir, ref_clean))
    if os.path.exists(p1):
        return 'OK', p1, '同目录'
    # 一级半：所在子技能包根（references/xxx.md 这类写法在 SKILL.md 里极常见）
    for sd in skill_dirs:
        if md_dir == sd or md_dir.startswith(sd + os.sep):
            p1b = os.path.normpath(os.path.join(sd, ref_clean))
            if os.path.exists(p1b):
                return 'OK', p1b, '子包根'
    # 三级：包根
    p3 = os.path.normpath(os.path.join(root, ref_clean))
    if os.path.exists(p3):
        return 'OK', p3, '包根'
    # 溯源区（v1.9 增，须先于「工作区未随包」判定）
    p4 = resolve_sourced(ref_clean, rel_md, root)
    if p4:
        return 'SOURCED', p4, '溯源区'
    # 目录引用（末尾带 /）：指向的是目录而非文件，不参与未随包统计
    if is_dir_ref:
        return 'DIR', '', '目录引用'
    base = os.path.basename(ref_clean)
    # 工作区判定（v1.8 修：须先于「包内同名」）
    # 「候选/命例.md」「_draft/规则清单_全量.md」这类写法，包内多有同名文件；
    # 若先走同名兜底，会被假解析到别家 references/ 的同名文件，把「未随包」伪装成 OK。
    first = ref_clean.split('/')[0]
    if first in WORKSPACE_DIRS or base in WORKSPACE_FILES:
        return 'WORKSPACE', '', '工作区未随包'
    # 二级：包内同名
    hits = index.get(base) or []
    if len(hits) == 1:
        return 'OK', hits[0], '包内同名'
    if len(hits) > 1:
        return 'OK', hits[0], '包内同名(多义%d)' % len(hits)
    return 'BROKEN', '', '无法解析'


def main():
    ap = argparse.ArgumentParser(description='技能包引用体检（三级解析）')
    ap.add_argument('--root', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help='技能包根目录（默认脚本上一级）')
    ap.add_argument('--only', default=None, help='只体检该子目录（相对包根）')
    ap.add_argument('--strict', action='store_true', help='真错 > 0 时非零退出')
    ap.add_argument('--verbose', action='store_true', help='逐条打印')
    ap.add_argument('--json', default=None, help='把完整结果写成 json')
    ap.add_argument('--emit-md', default=None,
                    help='把「未随包」引用写成登记清单（默认包根 引用未随包清单.md）')
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print('[FAIL] 包根不存在: %s' % root)
        return 2
    scan_root = os.path.join(root, args.only) if args.only else root
    if not os.path.isdir(scan_root):
        print('[FAIL] --only 目录不存在: %s' % scan_root)
        return 2

    index = build_index(root)
    skill_dirs = sorted({dp for dp, dn, fn in os.walk(root) if 'SKILL.md' in fn}, key=len, reverse=True)

    rows = []
    for dp, dn, fn in os.walk(scan_root):
        dn[:] = [d for d in dn if d != SRC_DIR]          # 溯源区是收进来的原件，不参与体检
        for f in sorted(fn):
            if not f.endswith('.md') or f in SKIP_FILES:
                continue
            md_path = os.path.join(dp, f)
            rel_md = os.path.relpath(md_path, root)
            try:
                text = open(md_path, encoding='utf-8').read()
            except UnicodeDecodeError:
                text = open(md_path, encoding='utf-8', errors='replace').read()
            for lineno, line in enumerate(text.splitlines(), 1):
                for m in REF_RE.finditer(line):
                    raw = m.group(1)
                    if not looks_like_ref(raw):
                        continue
                    status, hit, how = resolve(raw, dp, root, index, skill_dirs, rel_md)
                    rows.append({
                        'file': rel_md,
                        'line': lineno,
                        'ref': raw,
                        'status': status,
                        'how': how,
                        'hit': os.path.relpath(hit, root) if hit else '',
                    })

    total = len(rows)
    by_status = Counter(r['status'] for r in rows)
    uniq_broken = Counter(r['ref'] for r in rows if r['status'] == 'BROKEN')
    uniq_ws = Counter(r['ref'] for r in rows if r['status'] == 'WORKSPACE')
    uniq_src = Counter(r['ref'] for r in rows if r['status'] == 'SOURCED')
    n_file_ref = total - by_status.get('DIR', 0)      # 目录引用不计入分母

    print('=' * 66)
    print('引用体检 · %s' % root)
    print('=' * 66)
    print('扫描引用   %5d 处（去重 %d；其中目录引用 %d 处不计）'
          % (total, len({r['ref'] for r in rows}), by_status.get('DIR', 0)))
    print('  可解析   %5d 处  %.1f%%' % (by_status.get('OK', 0), 100.0 * by_status.get('OK', 0) / max(n_file_ref, 1)))
    print('  溯源区   %5d 处  （蒸馏期工作稿已随包，可核对但不作依据）' % by_status.get('SOURCED', 0))
    print('  未随包   %5d 处  （工作区文件，非笔误，须改造或回填）' % by_status.get('WORKSPACE', 0))
    print('  真错     %5d 处  （必须清零）' % by_status.get('BROKEN', 0))
    if args.strict:
        print('  门禁：--strict %s' % ('PASS' if by_status.get('BROKEN', 0) == 0 else 'FAIL'))

    def dump(title, counter, limit=30):
        if not counter:
            return
        print('\n--- %s（去重 %d 个，共 %d 处）---' % (title, len(counter), sum(counter.values())))
        for i, (ref, n) in enumerate(counter.most_common(limit), 1):
            print('  %2d. %-3d  %s' % (i, n, ref))
        if len(counter) > limit:
            print('  …… 另有 %d 个未列（--json 看全量）' % (len(counter) - limit))

    dump('真错 BROKEN', uniq_broken)
    dump('未随包 WORKSPACE', uniq_ws)
    if not args.verbose:
        print('\n溯源区命中 %d 处 / %d 个文件（明细见 --json 或 --verbose）' % (by_status.get('SOURCED', 0), len(uniq_src)))

    if args.verbose:
        print('\n--- 逐条明细 ---')
        for r in rows:
            print('  [%-9s] %s:%d  `%s`  -> %s' % (r['status'], r['file'], r['line'], r['ref'], r['how']))

    if args.json:
        payload = {
            'root': root,
            'total': total,
            'summary': dict(by_status),
            'broken': dict(uniq_broken),
            'workspace': dict(uniq_ws),
            'sourced': dict(uniq_src),
            'rows': rows,
        }
        with open(args.json, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        print('\n[OK] 报告已写入 %s' % args.json)

    if args.emit_md:
        out = args.emit_md if args.emit_md is not True else os.path.join(root, '引用未随包清单.md')
        if not os.path.isabs(out):
            out = os.path.join(root, out)
        locs = defaultdict(list)
        for r in rows:
            if r['status'] == 'WORKSPACE':
                locs[r['ref'].strip()].append('%s:%d' % (r['file'].replace(os.sep, '/'), r['line']))
        lines = [
            '# 引用未随包清单',
            '',
            '> 由 `python tools/check_refs.py --emit-md` 生成，**每次改动引用后重跑一次**。',
            '> 本清单登记包内正文引用、但**文件从未随包发布**的原蒸馏期工作区文件。',
            '> 这些引用**不是断链，也不是依据**——读到时不得当作"已有原文支持"，只能当作"作者当时的工作稿去向"。',
            '> 需要其中内容时：向作者索取回填，或在包内另设专章重写，**不得凭文件名推测内容**。',
            '',
            '统计：未随包引用 %d 处，涉及 %d 个文件；已入溯源区 %d 处；真错 %d 处。'
            % (by_status.get('WORKSPACE', 0), len(locs), by_status.get('SOURCED', 0), by_status.get('BROKEN', 0)),
            '',
            '| 未随包文件 | 被引次数 | 引用位置（文件:行） |',
            '| --- | --- | --- |',
        ]
        for name, ps in sorted(locs.items(), key=lambda kv: -len(kv[1])):
            shown = '、'.join(ps[:4]) + ('……等 %d 处' % len(ps) if len(ps) > 4 else '')
            lines.append('| `%s` | %d | %s |' % (name, len(ps), shown))
        lines += ['', '---', '',
                  '**回填口径（v1.9）**：能找到蒸馏期原稿的，按 `_溯源/<子包>/<原引用路径>` 收进包内，'
                  '**正文引用路径一个字不改**；重跑本工具后这些条目应从「未随包」转为「溯源区」。',
                  '找不到原稿的（本清单剩余项）不得凭文件名推测内容，须向作者索取或另设专章重写。', '']
        with open(out, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(lines))
        print('\n[OK] 未随包清单已写入 %s（%d 个文件）' % (out, len(locs)))

    if args.strict and by_status.get('BROKEN', 0) > 0:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
