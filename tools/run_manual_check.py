# -*- coding: utf-8 -*-
"""P1-4 端到端 10 条人工验收项的机器可核部分。

人工项本义是"人读报告核对"，本脚本把每条的**可机核证据**写成断言：
报告结构与出处密度 + 每条的必含关键词组（AND of ORs）+ 禁用词。
不能替代人读，只保证报告没有漏掉该说的那几句话 —— 漏一句即 FAIL。

用法：
    python tools/run_manual_check.py [-q] [--strict] [--dir <报告目录>]
"""
import glob
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DIR = os.path.join(ROOT, "output")

# 结构要求：六节齐备（一～六），缺节即报告结构不完整
STRUCT = [u"一、盘面", u"二、断法路径", u"三、断语", u"四、【命例佐证】", u"五、边界", u"六、器边角"]
CITE_RE = re.compile(r"\.md:\d+")          # 出处：文件名:行号
CITE_MIN = 6                               # 每份报告至少 6 处可指认的原文位次

# (编号, 用例, 断言说明, [ [任一命中] 组 ... ], [禁用词 ... ])
ITEMS = [
    ("M-01", "E2E-1", u"断出写作/传播与赛车/速度双职业面",
     [[u"写作"], [u"赛车", u"速度"]], []),
    ("M-02", "E2E-1", u"断出学历异常（酉穿戌=文库受损）",
     [[u"酉穿戌", u"酉穿倒戌"], [u"文库"], [u"受损", u"穿坏", u"被穿"]], []),
    ("M-03", "E2E-1", u"报告含【命例佐证】韩寒原型盘锚点",
     [[u"【命例佐证】"], [u"韩寒"], [u"U-0633"]], []),
    ("M-04", "E2E-2", u"断出歌唱/舞台事业（伤官才华、印为舞台）",
     [[u"舞台"], [u"歌唱", u"演艺"], [u"伤官"]], []),
    ("M-05", "E2E-2", u"应期落乙亥年且概率化措辞不断死",
     [[u"乙亥"], [u"倾向", u"概率", u"留意"], [u"不断死", u"不作实断", u"不判"]],
     [u"必死", u"必死于", u"死期已定"]),
    ("M-06", "E2E-2", u"高风险断语带免责边界（不作医疗）",
     [[u"免责"], [u"不作医疗", u"非医学诊断"]], []),
    ("M-07", "E2E-3", u"断出过河拆桥组合与主位/宾位",
     [[u"过河拆桥"], [u"主位"], [u"宾位"], [u"合住"]], []),
    ("M-08", "E2E-3", u"行业定性五金/钢材",
     [[u"五金"], [u"钢材"]], []),
    ("M-09", "E2E-3", u"应期给巳运甲戌年",
     [[u"巳运"], [u"甲戌"]], []),
    ("M-10", "E2E-3", u"与 ps-tiwei-geju 冲突时按仲裁 #1 附墓开/墓闭两说并列",
     [[u"仲裁 #1", u"仲裁#1"], [u"墓开"], [u"墓闭"], [u"并列"]], []),
]

CASE_FILE = {
    "E2E-1": u"E2E-1_韩寒_端到端报告.md",
    "E2E-2": u"E2E-2_邓丽君_端到端报告.md",
    "E2E-3": u"E2E-3_段氏过河拆桥_端到端报告.md",
}


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def main(argv):
    quiet = "-q" in argv
    strict = "--strict" in argv
    rdir = DEFAULT_DIR
    if "--dir" in argv:
        rdir = argv[argv.index("--dir") + 1]

    results = []

    def check(cid, desc, fn):
        ok, msg = fn()
        results.append((cid, desc, ok, msg))
        if not quiet:
            print(u"%s %s %s%s" % ("✅" if ok else u"❌", cid, desc,
                                   "" if ok else u"｜" + msg))

    texts = {}
    missing = []
    for case, fn in CASE_FILE.items():
        p = os.path.join(rdir, fn)
        if os.path.exists(p):
            texts[case] = read(p)
        else:
            missing.append(fn)
    if missing:
        print(u"❌ 缺报告：%s" % u"、".join(missing))
        return 2

    # 结构与出处密度
    for case in sorted(texts):
        t = texts[case]

        def mk(t=t):
            lack = [s for s in STRUCT if s not in t]
            cites = len(CITE_RE.findall(t))
            if lack:
                return False, u"缺节：%s" % u"、".join(lack)
            if cites < CITE_MIN:
                return False, u"出处仅 %d 处（<%d）" % (cites, CITE_MIN)
            return True, u"六节齐备，出处 %d 处" % cites
        check("%s-结构" % case, u"报告结构完整且断语带出处", mk)

    # 十条人工项的可机核证据
    for cid, case, desc, groups, forbid in ITEMS:
        def mk(cid=cid, case=case, groups=groups, forbid=forbid):
            t = texts[case]
            miss = []
            for alts in groups:
                if not any(a in t for a in alts):
                    miss.append(u"/".join(alts))
            hit_forbid = [w for w in forbid if w in t]
            if miss:
                return False, u"缺：%s" % u"、".join(miss)
            if hit_forbid:
                return False, u"出现禁用措辞：%s" % u"、".join(hit_forbid)
            return True, u""
        check(cid, desc, mk)

    total = len(results)
    passed = sum(1 for r in results if r[2])
    print(u"\n人工验收项（机检）：%d/%d PASS" % (passed, total))
    for cid, desc, ok, msg in results:
        if not ok:
            print(u"  ❌ %s %s｜%s" % (cid, desc, msg))
    print(u"门禁：%s" % (u"PASS" if passed == total else u"FAIL"))
    return 0 if (passed == total or not strict) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
