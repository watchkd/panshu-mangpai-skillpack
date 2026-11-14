#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ocr_cases.py — 扫描集 OCR 文本 → 命例结构化抽取（v1.9 · P1-3）

背景：高德臣案例集全页无文本层。v1.8 走「栅格化 + 视觉模型识读」，批读易漏行、
且视觉模型有编造史。v1.9 改走 Windows 自带 OCR（zh-Hans）取字，本脚本负责：

  1. 按 `=== pNNN ===` 切页，逐页找「例N 乾造/坤造：四柱」；
  2. 去字间空格、跨行合并，凑满八字；
  3. 按六十甲子校验每柱，干支阴阳不配/非法柱标 SUSPECT 并尝试形近纠正；
  4. 按单元核对例号连续性，报缺号（漏识）与重号；
  5. 输出 JSON 与一份可读报告，供人工/视觉复核只盯问题行。

用法：
    python ps-anli-ku/tools/ocr_cases.py temp/u4_ocr.txt --expect 48 --from 112 --json out.json
    python ps-anli-ku/tools/ocr_cases.py temp/u5_ocr.txt --expect 31 --from 160
"""

import argparse
import json
import re
import sys

GAN = '甲乙丙丁戊己庚辛壬癸'
ZHI = '子丑寅卯辰巳午未申酉戌亥'
GAN_IDX = {g: i for i, g in enumerate(GAN)}
ZHI_IDX = {z: i for i, z in enumerate(ZHI)}

# OCR 形近字互校表（键为误识字，值为候选正字）
NEAR = {
    '内': '丙', '两': '丙', '丙': '丙',
    '戊': '戊戌', '戌': '戌戊', '戍': '戌戊', '成': '戌戊', '茂': '戊',
    '末': '未', '朱': '未', '来': '未', '未': '未',
    '已': '己巳', '己': '己', '巳': '巳己', '乙': '乙',
    '王': '壬', '壬': '壬', '葵': '癸', '癸': '癸',
    '康': '庚', '庾': '庚', '庚': '庚', '幸': '辛', '辛': '辛',
    '甲': '甲', '由': '甲申', '申': '申', '牛': '午', '干': '午', '午': '午',
    '纽': '丑', '丑': '丑', '卵': '卯', '卯': '卯', '玄': '亥', '亥': '亥',
    '演': '寅', '寅': '寅', '西': '酉', '酉': '酉', '晨': '辰', '辰': '辰',
    '了': '子丁', '子': '子', '丁': '丁', '也': '巳',
    '于': '子干', '中': '申', '且': '巳且', '小': '子', '寸': '子',
    '屯': '子', '电': '子', '由': '甲申', '田': '申',
}

CASE_CHARS = set(GAN) | set(ZHI) | set(NEAR.keys())


def norm(text):
    """去空白与顿号，保留汉字数字与符号。"""
    return re.sub(r'[\s、，,。·．\.\-—]+', '', text)
# 例头三种写法都要认：
#   例12乾造：… ／ 例13：乾：1947年… ／ 例43（占）乾：… ／ 乾28造… ／ 例4，1坤造：…
HEAD_RE = re.compile(r'例(?:([0-9，,\.]{1,4})|((?!乾|坤)[\u4e00-\u9fa5]))?'
                     r'[（(]?[占]?[）)]?[：:]?[^例]{0,8}?'
                     r'(乾造|坤造|粹造|亁造|男造|女造|乾|坤|八字)'
                     r'|(?:乾|坤)(\d{1,2})造')
BZ_RE = re.compile(r'八字[：:]?')
YMDH_RE = re.compile(r'([甲乙丙丁戊己庚辛壬癸])([子丑寅卯辰巳午未申酉戌亥])年'
                     r'([甲乙丙丁戊己庚辛壬癸])([子丑寅卯辰巳午未申酉戌亥])月'
                     r'([甲乙丙丁戊己庚辛壬癸])([子丑寅卯辰巳午未申酉戌亥])日'
                     r'([甲乙丙丁戊己庚辛壬癸])([子丑寅卯辰巳午未申酉戌亥])时')
BZ_END_RE = re.compile(r'人运|大运|運')
BIRTH_RE = re.compile(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(?:初|廿)?'
                     r'([一二三四五六七八九十]{1,3}|\d{1,2})?\s*日?')
CN_NUM = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7,
          '八': 8, '九': 9, '十': 10, '廿': 20}

def cn2int(t):
    if not t:
        return 0
    if t.isdigit():
        return int(t)
    if t == '廿':
        return 20
    if t.startswith('廿'):
        return 20 + CN_NUM.get(t[1], 0)
    if t.startswith('十'):
        return 10 + CN_NUM.get(t[1:], 0)
    if '十' in t:
        a, _, b = t.partition('十')
        return CN_NUM.get(a, 0) * 10 + (CN_NUM.get(b, 0) if b else 0)
    return CN_NUM.get(t, 0)
HOUR_MAP = {'子': '00:00', '丑': '02:00', '寅': '04:00', '卯': '06:00', '辰': '08:00',
            '巳': '10:00', '午': '12:00', '未': '14:00', '申': '16:00', '酉': '18:00',
            '戌': '20:00', '亥': '22:00'}


def clean_no(raw):
    digits = re.sub(r'[^0-9]', '', raw or '')
    return int(digits) if digits else 0


ALL = GAN + ZHI


def pillars_ok(cand):
    if len(cand) != 8:
        return False
    for k in range(4):
        if not valid_pillar(cand[2 * k], cand[2 * k + 1]):
            return False
    return True


def repair_short(pick):
    """OCR 漏字时：穷举「插入 1 字 / 删 1 字 / 换 1 字」，取唯一合法解。"""
    if len(pick) == 8:
        return pick, ''
    sols = set()
    if len(pick) < 8:
        for need in range(8 - len(pick)):
            pass
        # 只处理缺 1 字
        if len(pick) == 7:
            for i in range(8):
                for ch in ALL:
                    cand = pick[:i] + ch + pick[i:]
                    if pillars_ok(cand):
                        sols.add(cand)
    if len(pick) == 9:
        for i in range(9):
            cand = pick[:i] + pick[i + 1:]
            if pillars_ok(cand):
                sols.add(cand)
    if len(sols) == 1:
        return sols.pop(), 'INSERT'
    return pick, ''


def parse_page(pg, body, expect=0, prev=0):
    """一页内所有命例：先认例头，再判「直接四柱」还是「出生日期」。"""
    flat = norm(body)
    out = []
    marks = list(HEAD_RE.finditer(flat))
    prev_no = prev
    for i, m in enumerate(marks):
        if m.group(4):                       # 「乾28造」形态
            no = int(m.group(4))
            sex = '坤造' if flat[m.start()] == '坤' else '乾造'
        else:
            no = clean_no(m.group(1))
            sex = ('坤造' if m.group(3).startswith('坤') else
                   '乾造' if m.group(3).startswith(('乾', '亁')) else
                   '男造' if m.group(3).startswith('男') else
                   '女造' if m.group(3).startswith('女') else '未标')
        if no == 1 and prev_no > 1:          # 单元起点，例号归 1
            prev_no = 1
        elif (not no or no > (expect or 99)) and prev_no:   # 号被识成汉字/越界
            no = prev_no + 1
        elif no <= prev_no and prev_no:      # 「例4，1」实为 44 这类拆号
            no = prev_no + 1
        if not no:
            continue
        if expect and no > expect:           # 上一单元末例的页首残留，不进本单元
            continue
        prev_no = no
        start = m.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(flat)
        seg = flat[start:end]
        head = seg[:26]
        birth = None
        bm = BIRTH_RE.search(head)
        if bm:
            y, mo = int(bm.group(1)), int(bm.group(2))
            d = cn2int(bm.group(3))
            if d > 31:                        # 「初9 11时」粘连成 91
                d = int(str(d)[0])
            hz = ''
            for ch in head[bm.end():bm.end() + 4]:
                if ch in HOUR_MAP:
                    hz = ch
                    break
            birth = {'year': y, 'month': mo, 'day': d,
                     'branch': hz, 'time': HOUR_MAP.get(hz, '')}
        pick = ''
        ym = YMDH_RE.search(seg)          # 「X年X月X日X时」整串给出
        if ym:
            pick = ''.join(ym.groups())
        bz = BZ_RE.search(seg) if not pick else None
        if bz:                              # 有「八字：」行则以此为准，最可靠
            tail = seg[bz.end():]
            cut = BZ_END_RE.search(tail)
            body_bz = tail[:cut.start()] if cut else tail[:40]
            for ch in body_bz:
                if ch in CASE_CHARS:
                    pick += ch
                if len(pick) >= 8:
                    break
        if len(pick) < 8:                   # 退回例头顺取
            pick = ''
            for ch in seg:
                if ch in CASE_CHARS:
                    pick += ch
                elif pick:
                    break
                if len(pick) >= 8:
                    break
        alt = ''
        for ch in seg:                       # 例头顺取（备用）
            if ch in CASE_CHARS:
                alt += ch
            elif alt:
                break
            if len(alt) >= 8:
                break
        alt, _ = repair_short(alt)
        bad_now = sum(0 if valid_pillar(pick[2 * k:2 * k + 2][:1], pick[2 * k + 1:2 * k + 2]) else 1
                      for k in range(4)) if len(pick) == 8 else 4
        if bad_now >= 2 and len(alt) == 8:
            bad_alt = sum(0 if valid_pillar(alt[2 * k], alt[2 * k + 1]) else 1 for k in range(4))
            if bad_alt < bad_now:
                pick = alt
        pick, rep = repair_short(pick)
        pillars, changed, bad = [], [], []
        if rep:
            changed.append('补字')
        for k in range(4):
            pair = pick[k * 2:k * 2 + 2]
            if len(pair) < 2:
                pillars.append('??')
                bad.append(k)
                continue
            p, ch_flag, still_bad = fix_pillar(pair)
            pillars.append(p)
            if ch_flag:
                changed.append('%s→%s' % (pair, p))
            if still_bad:
                bad.append(k)
        # 生日形态：八字栏不可信，正文可能压根没排八字
        if birth and bad:
            kind = 'BIRTH'
        elif bad:
            kind = 'SUSPECT'
        else:
            kind = 'PILLARS'
        out.append({'page': pg, 'no': no, 'sex': sex, 'pillars': pillars,
                    'birth': birth, 'kind': kind, 'raw': pick[:10], 'fixed': changed,
                    'bad': bad, 'text': seg[:400]})
    return out, prev_no


def valid_pillar(g, z):
    return g in GAN_IDX and z in ZHI_IDX and (GAN_IDX[g] % 2) == (ZHI_IDX[z] % 2)


def fix_pillar(pair):
    """返回 (柱, 是否改过, 是否仍非法)。"""
    g, z = pair[0], pair[1]
    if valid_pillar(g, z):
        return g + z, False, False
    cands = []
    for g2 in NEAR.get(g, g):
        for z2 in NEAR.get(z, z):
            if valid_pillar(g2, z2):
                cands.append(g2 + z2)
    if len(cands) == 1:
        return cands[0], True, False
    return g + z, False, True




def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ocr')
    ap.add_argument('--expect', type=int, default=0, help='本单元应有例数')
    ap.add_argument('--from', dest='start_no', type=int, default=0, help='S-GD 起始编号')
    ap.add_argument('--json', default=None)
    args = ap.parse_args()

    text = open(args.ocr, encoding='utf-8').read()
    parts = re.split(r'=== (p\d+) ===', text)[1:]
    pages = list(zip(parts[0::2], parts[1::2]))

    cases, prev = [], 0
    for pg, body in pages:
        got, prev = parse_page(pg, body, args.expect, prev)
        cases.extend(got)

    print('=' * 70)
    print('OCR 命例抽取 · %s' % args.ocr)
    print('=' * 70)
    print('页数 %d｜抽到命例 %d 条' % (len(pages), len(cases)))

    by_kind = {}
    for c in cases:
        by_kind[c['kind']] = by_kind.get(c['kind'], 0) + 1
    print('  直接四柱 PILLARS %d 条' % by_kind.get('PILLARS', 0))
    print('  生日待换算 BIRTH  %d 条' % by_kind.get('BIRTH', 0))
    print('  仍可疑 SUSPECT    %d 条' % by_kind.get('SUSPECT', 0))
    print('  形近已纠正 %d 条' % len([c for c in cases if c['fixed']]))
    for c in cases:
        if c['kind'] == 'BIRTH':
            b = c['birth']
            print('    %s 例%-3d %s  生日 %s-%s-%s %s时 → %s' % (
                c['page'], c['no'], c['sex'], b['year'], b['month'], b['day'],
                b['branch'], ' '.join(c['pillars'])))
        elif c['kind'] == 'SUSPECT':
            print('    %s 例%-3d %s  %s  (原读 %s)' % (c['page'], c['no'], c['sex'],
                                                     ' '.join(c['pillars']), c['raw']))

    nos = [c['no'] for c in cases]
    dup = sorted({n for n in nos if nos.count(n) > 1})
    if args.expect:
        miss = [n for n in range(1, args.expect + 1) if n not in nos]
        extra = [n for n in nos if n > args.expect]
        print('  编号连续性：应有 1–%d｜缺号 %d 个 %s｜越界 %s' % (
            args.expect, len(miss), miss if miss else '无', extra if extra else '无'))
    if dup:
        print('  ！重号 %s' % dup)

    rows = []
    for i, c in enumerate(cases):
        sid = 'S-GD-%03d' % (args.start_no + i) if args.start_no else ''
        rows.append({'id': sid, 'page': c['page'], 'book_no': c['no'],
                     'sex': c['sex'], 'pillars': c['pillars'],
                     'birth': c['birth'], 'kind': c['kind'], 'text': c['text'],
                     'fixed': c['fixed'], 'suspect': bool(c['bad'])})

    if args.json:
        with open(args.json, 'w', encoding='utf-8') as fh:
            json.dump({'source': args.ocr, 'count': len(rows), 'cases': rows}, fh,
                      ensure_ascii=False, indent=1)
        print('\n[OK] 已写入 %s' % args.json)
    return 0


if __name__ == '__main__':
    sys.exit(main())
