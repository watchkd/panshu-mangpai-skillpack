#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_ganduan.py — 敢断纪律体检（v1.9.1 · 承 v1.0／v1.1 风格）

`ps-zonglun/SKILL.md`「敢断纪律」四条是软约束，靠人记记不住。本脚本把它落成机检，
只管「写法有没有软掉」，**不管断语对错**——吉凶判得对不对是断法层的事。

    G1 三词作主干    「可能」「倾向」「视情况」占了断语主干位（纪律 1）
    G2 灰止断        写了「不断／不作实断／难以断定」，却没落进四种合法举证情形之一（纪律 2）
                     合法情形：四柱不全／时辰存疑且校不出／规则库无对应条（≥3 条比对）／实况冲突（≥2 项反向）
    G3 多重软化      同一句里软词 ≥3 个、且无硬断词——典型「或有起伏、宜谨慎、不排除」（提示项，不进 strict）
    G4 但书止断      拿空亡／神煞／五行空／库墓当真去止断（纪律 4）——这是硬错，务必为零

**不检查**：断法口径、规则适用、吉凶对错。脚本只读、纯标准库。

用法：
    python tools/check_ganduan.py               # 只扫断语文档（批词／命书／体例／范例／话术／报告）
    python tools/check_ganduan.py --all         # 扫全包 md（纪律说明段落自动降级为巡检提示）
    python tools/check_ganduan.py --only output
    python tools/check_ganduan.py --strict      # G1／G2／G4 任一非零则非零退出
    python tools/check_ganduan.py --verbose     # 连 G3 明细也打印
    python tools/check_ganduan.py --self-test   # 造 4 个错例须全抓 + 包内断语文档零误报
"""

import argparse
import os
import re
import sys
from collections import Counter, defaultdict

# ---------------------------------------------------------------- 词表

# 纪律 1：三词
SOFT3 = ('可能', '倾向', '视情况')

# 纪律 2：止断表述（写成不下断，须举证才放行）
# 只认「对命主判断整体不下断」的写法；「只断 A、不断具体 B」「流年不断吉凶」属范围限定与分工口径，
# 不是灰止断，故不列入，另由 SCOPE_WORDS 显式放过。
STOP_PAT = re.compile(
    r'(?:难以|无法|不能|不宜|不敢|无从|不作实|不作确|不做实|不下实|不下确)断(?:定|死|其|此|吉凶|结论)?'
    r'|(?:暂|先|索性)不断论?|断不出|不作断论')

# 纪律 2：四种合法止断情形的举证钩子
JUSTIFY = ('四柱不全', '柱不全', '未核验', '未经核验', '时辰存疑', '校不出', '校不准',
           '规则库无对应', '无对应条', '比对过', '查过', '已核过', '冲突点', '实况冲突',
           '举证', '不适用')

# 纪律 4：但书（只可减等，不可止断）
DANSHU = ('空亡', '神煞', '五行空', '库墓', '入墓', '交运不论吉凶', '但书')

# G1：三词落在主干位（紧跟断语连接词，或直接带结论）
MAIN_SOFT = re.compile(
    r'(?:主|必|定|故|则|即|应|仍|终)\s*(?:可能|倾向|视情况)'
    r'|(?:可能|倾向|视情况)\s*(?:会|要|能|有|无|成|败|破|散|得|失|犯|遭|克|损|发)')

# 范围限定／分工口径：出现这些词，说明是在「划界限」而非「不下断」，G2 放过
SCOPE_WORDS = ('只断', '只作', '仅作', '只记', '只判', '具体', '吉凶', '证明', '免责',
               '分工', '口径', '范围', '概率化', '仲裁', '佐证', '原书', '命例', '不作通例',
               '不作医疗', '不作法律', '不作投资', '依据')

# G4：把但书当成止断理由
DANSHU_STOP = re.compile(
    r'(?:因|缘|以|由于|鉴于)[^。！？\n]{0,8}(?:空亡|神煞|五行[之]?空|库墓|入墓)[^。！？\n]{0,14}'
    r'(?:不断|不下断|不作断|不作实断|难以断|无法断|不宜断|不敢断)'
    r'|(?:空亡|神煞|五行[之]?空|库墓)[^。！？\n]{0,16}(?:故|所以|因此|是以)[^。！？\n]{0,10}'
    r'(?:不断|不下断|不作断|不作实断)')

# G3：多重软化（提示项）
SOFT_WIDE = ('可能', '倾向', '视情况', '或有', '或可', '恐', '未必', '待验',
             '宜谨慎', '大概', '似乎', '不排除', '留有余地')
HARD = ('直断', '结构成立', '断定', '判为', '定论', '铁', '主见', '必见', '定为')

# 纪律说明／禁令本身所在的语境：这类行是在「讲规则」，不是在「写断语」
RULE_CTX = ('不得', '禁用', '勿用', '不作主干', '三词', '红线', '反例', '忌用',
            '止断理由', '四种情形', '敢断纪律', '举证', 'check_ganduan')

# 断语文档识别（与 check_yingqi 同口径）
TARGET_HINTS = ('批词', '命书', '体例', '范例', '话术', '报告')
SKIP_PREFIX = ('升级说明_',)
SKIP_DIRS = ('tools', 'references', '.git', 'node_modules')


def split_sentences(line):
    """按中英文句末与分号断句，够用即可。"""
    return [s for s in re.split(r'[。！？；!?;]', line) if s.strip()]


def check_line(line):
    """单行体检，返回 [(rule, msg)]。"""
    out = []
    stripped = line.strip()
    if not stripped or stripped.startswith('>'):
        return out   # 引用块＝引原文／反例，不判
    is_rule_ctx = any(k in line for k in RULE_CTX)

    # G4 先判（硬错）
    if DANSHU_STOP.search(line):
        out.append(('G4', 'G4 但书止断：拿空亡／神煞／五行空／库墓当真去不下断——但书只回调不撤销，须直断后减弱'))
    elif not is_rule_ctx:
        # G1 三词作主干
        m = MAIN_SOFT.search(line)
        if m:
            out.append(('G1', 'G1 三词作主干：「%s」占了主干位，须改成硬断（孤证才用「倾向」并并写「孤证，作倾向」）'
                        % m.group(0).strip()))
        # G2 灰止断
        sm = STOP_PAT.search(line)
        if sm and not any(k in line for k in JUSTIFY) and not any(k in line for k in SCOPE_WORDS):
            out.append(('G2', 'G2 灰止断：「%s」——未落进四种合法举证情形（四柱不全／时辰校不出／规则库≥3条比对／实况≥2项反向冲突），也没划出断的范围'
                        % sm.group(0)))
    # G3 多重软化（提示）
    for sent in split_sentences(line):
        hits = {w for w in SOFT_WIDE if w in sent}
        if len(hits) >= 3 and not any(h in sent for h in HARD):
            out.append(('G3', 'G3 多重软化：一句内软词 %d 个（%s），无硬断——须先直断再回调'
                        % (len(hits), '／'.join(sorted(hits)))))
            break
    return out


def check_file(path, rel, all_mode=False):
    issues = []
    in_fence = False
    try:
        lines = open(path, encoding='utf-8', errors='replace').read().splitlines()
    except OSError:
        return issues
    for i, line in enumerate(lines, 1):
        if line.lstrip().startswith('```'):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for rule, msg in check_line(line):
            issues.append((rule, rel, i, msg))
    # 全包模式：SKILL／体例等「讲规则的文档」只作巡检提示，不进 strict
    if all_mode and not any(h in rel for h in TARGET_HINTS):
        issues = [(r + 'o', f, l, m) for r, f, l, m in issues if r in ('G1', 'G2', 'G4')]
    return issues


def scan(root, only=None, all_mode=False):
    scan_root = os.path.join(root, only) if only else root
    if not os.path.isdir(scan_root):
        return -1, []
    scanned = 0
    issues = []
    for dp, dn, fn in os.walk(scan_root):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in sorted(fn):
            if not f.endswith('.md'):
                continue
            path = os.path.join(dp, f)
            rel = os.path.relpath(path, root)
            if any(f.startswith(x) for x in SKIP_PREFIX):
                continue
            if not all_mode and not any(h in rel for h in TARGET_HINTS):
                continue
            scanned += 1
            issues.extend(check_file(path, rel, all_mode))
    return scanned, issues


def self_test():
    """自测：4 个错例须全抓；包内断语文档 G1／G2／G4 须零误报。"""
    import tempfile
    bad = []
    cases = [
        ('G1', '此命财星得令，主可能有积蓄，晚景尚可。'),
        ('G2', '此局结构杂，难以断定其财势。'),
        ('G3', '财星或可小成，可能须待晚年，宜谨慎，不排除反复。'),
        ('G4', '财星落空亡，故不断其财。'),
    ]
    tmp = tempfile.mkdtemp(prefix='ganduan_selftest_')
    for want, text in cases:
        p = os.path.join(tmp, '批词_自测错例_%s.md' % want)
        with open(p, 'w', encoding='utf-8') as fh:
            fh.write(text + '\n')
        got = [r for r, *_ in check_file(p, 'self_test/批词_错例_%s.md' % want)]
        if want not in got:
            bad.append('错例 %s 未抓到（实得 %s）：%s' % (want, got or '无', text[:20]))
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    scanned, issues = scan(root)
    if scanned < 0:
        bad.append('包根不存在，无法做零误报检查')
    for rule in ('G1', 'G2', 'G4'):
        hit = [x for x in issues if x[0] == rule]
        if hit:
            bad.append('断语文档误报 %s %d 处，首例 %s:%s  %s'
                       % (rule, len(hit), hit[0][1], hit[0][2], hit[0][3]))
    if bad:
        print('自检 FAIL：')
        for b in bad:
            print('  - %s' % b)
        return 1
    print('自检 PASS（错例 4/4 全抓；断语文档 %d 个，G1／G2／G4 零误报）' % scanned)
    return 0


def main():
    ap = argparse.ArgumentParser(description='敢断纪律体检（G1 三词作主干／G2 灰止断／G3 多重软化／G4 但书止断）')
    ap.add_argument('--root', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help='技能包根目录（默认脚本上一级）')
    ap.add_argument('--only', default=None, help='只扫该子目录（相对包根）')
    ap.add_argument('--all', action='store_true', help='扫全包 md（规则文档自动降级为巡检提示）')
    ap.add_argument('--strict', action='store_true', help='G1／G2／G4 任一非零则非零退出')
    ap.add_argument('--verbose', action='store_true', help='连 G3 明细也逐条打印')
    ap.add_argument('--json', default=None, help='把结果写成 json')
    ap.add_argument('--self-test', action='store_true', help='自测：4 个错例须全抓，断语文档零误报')
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

    gate = sum(by_rule.get(k, 0) for k in ('G1', 'G2', 'G4'))
    print('=' * 70)
    print('敢断纪律体检 · %s' % root)
    print('=' * 70)
    print('扫描文档        %d 个（%s）' % (scanned, '全包' if args.all else '断语文档'))
    print('G1 三词作主干   %3d 处  （须改为硬断）' % by_rule.get('G1', 0))
    print('G2 灰止断       %3d 处  （须补举证或改为直断）' % by_rule.get('G2', 0))
    print('G3 多重软化     %3d 处  （提示项，不进门禁）' % by_rule.get('G3', 0))
    print('G4 但书止断     %3d 处  （硬错，须清零）' % by_rule.get('G4', 0))
    n_ctx = sum(v for k, v in by_rule.items() if k.endswith('o'))
    if n_ctx:
        print('规则文档巡检    %3d 处  （SKILL／体例在讲规则，降级提示，不计门禁）' % n_ctx)
    if args.strict:
        print('门禁：--strict %s' % ('PASS' if gate == 0 else 'FAIL'))

    for rule, title in (('G4', 'G4 但书止断（硬错）'), ('G1', 'G1 三词作主干'),
                        ('G2', 'G2 灰止断'), ('G3', 'G3 多重软化（提示）')):
        items = [x for x in all_issues if x[0] == rule]
        if not items:
            continue
        if rule == 'G3' and not args.verbose:
            print('\n--- %s：%d 处（--verbose 看明细）---' % (title, len(items)))
            continue
        print('\n--- %s：%d 处 ---' % (title, len(items)))
        for it in items[:20]:
            print('  %s:%d  %s' % (it[1], it[2], it[3]))
        if len(items) > 20:
            print('  …… 另有 %d 处' % (len(items) - 20))

    if per_file:
        print('\n--- 按文件 ---')
        for rel, n in sorted(per_file.items(), key=lambda kv: -kv[1])[:15]:
            print('  %3d  %s' % (n, rel))

    if args.json:
        import json as _json
        with open(args.json, 'w', encoding='utf-8') as fh:
            _json.dump({'scanned': scanned, 'summary': dict(by_rule),
                        'issues': [{'rule': r, 'file': f, 'line': l, 'msg': m} for r, f, l, m in all_issues]},
                       fh, ensure_ascii=False, indent=1)
        print('\n[OK] 报告已写入 %s' % args.json)

    if args.strict and gate > 0:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
