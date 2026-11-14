#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""run_e2e.py · 端到端 3 例首跑（P1-4）

自动判定部分：器能不能把三盘排对（P 系列自检、关系矩阵、神煞十二项），
以及断法包与命例佐证能否在真源里检索到；报告结构与「断语带出处」属人工验收项，
本脚本只把可机检的结论固化下来，不替人下断。

用法：
  python tools/run_e2e.py            # 全量
  python tools/run_e2e.py -q         # 只出汇总
  python tools/run_e2e.py --strict   # 有 FAIL 时退出码非零
"""

import io
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAIPAN = os.path.join(ROOT, "盘叔盲派", "ps-zonglun", "tools", "paipan.py")
IDX = os.path.join(ROOT, "盘叔盲派", "ps-zonglun", "references", "命例索引.md")
CASES = os.path.join(ROOT, "盘叔盲派", "ps-anli-ku", "references", "cases.json")
PKG = os.path.join(ROOT, "盘叔盲派")

CASE_DEFS = [
    {
        "id": "E2E-1",
        "name": "韩寒（职业·取象·学历）",
        "pillars": ["壬戌", "己酉", "己酉", "丁卯"],
        "gender": "男",
        "must": ["六穿", "戌酉", "六合", "戌卯", "自刑", "酉酉", "六冲", "酉卯", "天干五合", "壬丁",
                 "神煞十二项", "天乙贵人", "空亡"],
        "anchor": ["韩寒", "U-0633"],
        "case_kw": ["韩寒"],
        "pkgs": ["ps-duan-zhiye", "ps-duan-xiangfa", "ps-anli-ku", "ps-duan-zhongji"],
        "manual": ["断出写作/传播与赛车/速度双职业面", "断出学历异常（酉穿戌=文库受损）",
                   "报告含【命例佐证】韩寒原型盘"],
    },
    {
        "id": "E2E-2",
        "name": "邓丽君（健康·寿元·应期）",
        "pillars": ["壬辰", "癸丑", "庚辰", "戊寅"],
        "gender": "女",
        "must": ["四柱", "大运", "关系矩阵", "神煞十二项", "日主 **庚**"],
        "anchor": ["邓丽君", "U-0651"],
        "case_kw": ["邓丽君"],
        "pkgs": ["ps-duan-shizhan", "ps-xiazhongqi-jiankang", "ps-minglizhenbao", "ps-duan-zhongji"],
        "manual": ["断出歌唱/舞台事业（伤官才华、印为舞台）", "应期落乙亥年且概率化措辞、不断死",
                   "高风险断语带免责边界"],
    },
    {
        "id": "E2E-3",
        "name": "段氏过河拆桥例（发财·行业）",
        "pillars": ["庚戌", "己卯", "戊子", "癸亥"],
        "gender": "男",
        "must": ["大运", "关系矩阵", "神煞十二项"],
        "anchor": ["过河拆桥", "U-0794"],
        "case_kw": ["过河拆桥", "拆桥"],
        "pkgs": ["ps-tiwei-zuogong", "ps-duan-xiangfa", "ps-tiwei-geju", "ps-anli-ku"],
        "manual": ["断出过河拆桥组合（主位财重生宾位官杀被合住）", "行业定性五金/钢材（庚金取象）",
                   "应期给巳运、甲戌年", "与 ps-tiwei-geju 冲突时按仲裁 #1 附墓开/墓闭"],
    },
]


def run_paipan(pillars, gender):
    cmd = [sys.executable, PAIPAN, "--pillars"] + pillars + ["--gender", gender, "--shensha"]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def grep_idx(*needles):
    with io.open(IDX, encoding="utf-8") as f:
        t = f.read()
    return [(n, n in t) for n in needles]


def grep_cases(keywords):
    """索引级条目的 pillars 多为空，只能按 summary 关键字判有无。"""
    if not os.path.exists(CASES):
        return [], "cases.json 不存在"
    with io.open(CASES, encoding="utf-8") as f:
        data = json.load(f)
    recs = data if isinstance(data, list) else data.get("cases", [])
    hit = []
    for r in recs:
        blob = "%s %s" % (r.get("summary", ""), r.get("source", ""))
        if any(k in blob for k in keywords):
            hit.append(r.get("id", "?"))
    return hit, "cases.json 关键字命中 %d 条（%s）" % (len(hit), "／".join(hit[:5]) or "无")


def manual_stage(quiet, strict):
    """人工验收项的可机核部分（结构与必含证据），交 run_manual_check.py。

    报告未生成时返回 0 并提示；报告在但漏项时返回 1，计入端到端门禁。
    """
    mc = os.path.join(ROOT, "tools", "run_manual_check.py")
    if not os.path.exists(mc):
        print("人工验收项：未找到 run_manual_check.py，跳过")
        return 0
    cmd = [sys.executable, mc]
    if quiet:
        cmd.append("-q")
    cmd.append("--strict")
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=ROOT)
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode == 2:
        print("人工验收项：报告未生成（output/ 下缺 E2E 报告），本轮只验器层")
        return 0
    lines = [ln for ln in out.strip().split("\n") if ln.strip()]
    summary = next((ln for ln in lines if ln.startswith("人工验收项")), "")
    if summary:
        print(summary)
    if r.returncode != 0:
        for ln in lines:
            if ln.lstrip().startswith("❌") or ln.startswith("❌"):
                print("  " + ln.strip())
        return 1
    return 0


def main():
    argv = sys.argv[1:]
    quiet = "-q" in argv
    strict = "--strict" in argv
    results = []

    for c in CASE_DEFS:
        notes = []
        ok = True

        rc, out = run_paipan(c["pillars"], c["gender"])
        if rc != 0:
            ok = False
            notes.append("排盘 rc=%d" % rc)
        else:
            notes.append("排盘 rc=0")

        p_ok = [ln for ln in out.split("\n") if re.search(r"✅\s*P\d\d", ln)]
        p_bad = [ln for ln in out.split("\n") if re.search(r"❌\s*P\d\d", ln)]
        if p_bad:
            ok = False
            notes.append("自检未过：%s" % "／".join(re.search(r"P\d\d", x).group(0) for x in p_bad))
        notes.append("自检 ✅ %d 项" % len(p_ok))

        miss = [s for s in c["must"] if s not in out]
        if miss:
            ok = False
            notes.append("缺：%s" % "、".join(miss))

        for n in c["anchor"]:
            found = n in io.open(IDX, encoding="utf-8").read()
            if not found:
                ok = False
                notes.append("命例索引缺「%s」" % n)

        hit, hitnote = grep_cases(c.get("case_kw", []))
        notes.append(hitnote)

        for pkg in c["pkgs"]:
            d = os.path.join(PKG, pkg)
            if not (os.path.isdir(d) and os.path.exists(os.path.join(d, "SKILL.md"))):
                ok = False
                notes.append("包缺：%s" % pkg)

        results.append((c["id"], c["name"], ok, notes, c["manual"], out))

    if not quiet:
        for cid, name, ok, notes, manual, out in results:
            print("%s %s %s" % ("PASS" if ok else "FAIL", cid, name))
            for n in notes:
                print("    · %s" % n)
            print("    人工验收项（须逐条对报告核）：")
            for m in manual:
                print("      ☐ %s" % m)
            print("")

    npass = sum(1 for r in results if r[2])
    nfail = len(results) - npass
    print("端到端首跑：通过 %d／%d，失败 %d（人工项 %d 条，机检结果见下）"
          % (npass, len(results), nfail, sum(len(r[4]) for r in results)))
    if nfail:
        for cid, name, ok, notes, manual, out in results:
            if not ok:
                print("  - %s %s → %s" % (cid, name, "；".join(notes)))
    nfail += manual_stage(quiet, strict)
    print("门禁：%s" % ("PASS" if nfail == 0 else "FAIL"))
    return 0 if (nfail == 0 or not strict) else 1


if __name__ == "__main__":
    sys.exit(main())
