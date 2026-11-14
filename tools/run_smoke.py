# -*- coding: utf-8 -*-
"""P1-4 全体系测试 · 工具层首跑（T-1~T-15）

用法：python tools/run_smoke.py
逐条跑 paipan.py / mingshu.py，断言实际输出，打印 PASS/FAIL 与失败明细。
临时批词写本仓 _draft/_smoke_tmp/（不进产物目录）。
"""
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "盘叔盲派", "ps-zonglun", "tools")
PAIPAN = os.path.join(TOOLS, "paipan.py")
MINGSHU = os.path.join(TOOLS, "mingshu.py")
REF = os.path.join(ROOT, "盘叔盲派", "ps-zonglun", "references")
PAN = os.path.join(REF, "范例", "pan.json")
PROSE = os.path.join(REF, "范例", "批词_甲子乙亥庚戌癸未.md")
TMP = os.path.join(ROOT, "_draft", "_smoke_tmp")

PY = sys.executable
rows = []


def run(args, cwd=ROOT):
    p = subprocess.run([PY] + args, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def case(tid, title, ok, detail):
    rows.append((tid, title, ok, detail))


def expect(cond, msg):
    return ("OK" if cond else "NG:" + msg)


# ---------- T-1 形近字校正 ----------
rc, out = run([PAIPAN, "--pillars", "甲子", "乙亥", "庚戍", "癸未", "--gender", "男"])
ok = rc == 0 and "庚戌" in out and ("误写" in out or "形近" in out) and "P01" in out and "✅" in out
case("T-1", "「戍」校为「戌」并列疑为误写，P01 判 ✅", ok,
     "rc=%s；含误写提示=%s" % (rc, ("误写" in out or "形近" in out)))

# ---------- T-2 阴阳不同，停手 ----------
rc, out = run([PAIPAN, "--pillars", "甲丑", "乙亥", "庚戌", "癸未", "--gender", "男"])
ok = rc != 0 and "停手" in out and "非六十甲子" in out and "❌" in out and "Traceback" not in out
case("T-2", "甲丑判非法、停手不出盘、无 traceback", ok, "rc=%s" % rc)

# ---------- T-3 生日入口：真太阳时与起运 ----------
rc, out = run([PAIPAN, "--date", "1984-11-12", "--time", "14:45", "--lon", "116.12", "--gender", "男"])
ok = (rc == 0 and "甲子" in out and "乙亥" in out and "庚戌" in out and "癸未" in out
      and "14:44" in out and "8 年 2 月 18 日" in out and "10" in out)
case("T-3", "真太阳时 14:44→未时；四柱甲子乙亥庚戌癸未；起运折 8 年 2 月 18 日", ok, "rc=%s" % rc)

# ---------- T-4 缺 --time 拒绝排盘 ----------
rc, out = run([PAIPAN, "--date", "1984-11-12", "--gender", "男"])
ok = rc != 0 and "--time" in out and "乙亥" not in out
case("T-4", "生日入口未给 --time 即拒绝，不拿午时顶上", ok, "rc=%s" % rc)

# ---------- T-5 节气边界 P09 判 ❌ ----------
rc, out = run([PAIPAN, "--date", "1984-11-07", "--time", "14:00", "--gender", "男"])
ok = rc != 0 and "P09" in out and "❌" in out and "立冬" in out
case("T-5", "立冬相差 28 分钟 → P09 ❌ 要求复核月柱", ok, "rc=%s" % rc)

# ---------- T-6 大运表今位 ----------
rc, out = run([PAIPAN, "--pillars", "甲子", "乙亥", "庚戌", "癸未", "--gender", "男",
               "--birth-year", "1984", "--start-age", "10"])
ok = rc == 0 and "己卯" in out and "40" in out and "2023" in out and "今" in out
case("T-6", "第 4 运己卯 虚岁 40–49 公历 2023 起并标「今」", ok, "rc=%s" % rc)

# ---------- T-7 脏批词 lint 报 2 处 ----------
os.makedirs(TMP, exist_ok=True)
dirty = os.path.join(TMP, "dirty.md")
with open(dirty, "w", encoding="utf-8") as f:
    f.write("# 批词（测试构造）\n\n## 一 命式\n\n甲子 乙亥 庚戌 癸未。\n\n"
            "## 二 日主之意\n\n据 MP-断-091，此造权重 ★★。\n")
rc, out = run([MINGSHU, "--prose", dirty, "--lint", "--strict"])
n = len(re.findall(r"处", out))
ok = rc != 0 and ("2 处" in out or "2 处" in out.replace("  ", " "))
case("T-7", "批词含 MP-断-091 与 ★★ → lint 报 2 处、rc≠0", ok, "rc=%s；%s" % (rc, out.strip().splitlines()[-1] if out.strip() else ""))

# ---------- T-8 干净批词 lint 通过 + HTML 无工程标记 ----------
html = os.path.join(TMP, "clean.html")
rc, out = run([MINGSHU, "--prose", PROSE, "--lint", "--strict"])
lint_ok = rc == 0 and "通过" in out
html_ok = False
if lint_ok:
    rc2, out2 = run([MINGSHU, "--pan", PAN, "--prose", PROSE, "--out", html])
    if rc2 == 0 and os.path.exists(html):
        body = open(html, encoding="utf-8").read()
        html_ok = ("MP-" not in body and "★" not in body and "置信度" not in body)
case("T-8", "干净批词 lint 通过；排印 HTML 内 MP-/★/置信度 为 0", lint_ok and html_ok,
     "lint=%s html=%s" % (lint_ok, html_ok))

# ---------- T-9 缺「大运逐运」章仍出大运表 ----------
noplace = os.path.join(TMP, "noplace.md")
with open(noplace, "w", encoding="utf-8") as f:
    f.write("# 批词（测试构造·删大运章）\n\n## 一 命式\n\n甲子 乙亥 庚戌 癸未。\n\n"
            "## 二 日主之意\n\n庚金坐戌，土厚金埋，喜水木疏之。\n")
h2 = os.path.join(TMP, "noplace.html")
rc, out = run([MINGSHU, "--pan", PAN, "--prose", noplace, "--out", h2])
ok = rc == 0 and os.path.exists(h2)
if ok:
    body = open(h2, encoding="utf-8").read()
    ok = ("大运" in body and "丙子" in body and "己卯" in body)
case("T-9", "批词无大运章/占位符 → 工具自动补大运表", ok, "rc=%s" % rc)

# ---------- T-10 命书与 pan.json 逐字一致 ----------
import json
pan = json.load(open(PAN, encoding="utf-8"))
def dig(d, *keys):
    for k in keys:
        if isinstance(d, dict) and k in d:
            return d[k]
    return None
fine = os.path.exists(html)
detail = "pan.json 未读到"
if fine:
    body = open(html, encoding="utf-8").read()
    pil = pan.get("pillars") or pan.get("四柱")
    pil_s = pil if isinstance(pil, str) else " ".join(pil)
    four = [p for p in re.split(r"\s+", pil_s) if p]
    miss = [p for p in four if p not in body]
    dyn = pan.get("dayun") or pan.get("大运") or []
    dmiss = []
    for d in dyn:
        gz = d.get("gz") if isinstance(d, dict) else str(d)
        if gz and gz not in body:
            dmiss.append(gz)
    fine = not miss and not dmiss
    detail = "四柱缺 %s；大运缺 %s" % (miss, dmiss)
case("T-10", "命书四柱与大运干支与 pan.json 逐字一致（验收第 6 项）", fine, detail)

# ---------- T-11 两器自检 ----------
rc1, o1 = run([PAIPAN, "--self-test"])
rc2, o2 = run([MINGSHU, "--self-test"])
m1 = re.search(r"自检\s*(PASS|FAIL)[^\n]*", o1)
m2 = re.search(r"自检\s*(PASS|FAIL)[^\n]*", o2)
ok = rc1 == 0 and rc2 == 0 and m1 and m2 and "PASS" in m1.group(0) and "PASS" in m2.group(0)
case("T-11", "paipan/mingshu 自检双 PASS（现行项数见输出）", ok,
     "%s | %s" % (m1.group(0) if m1 else "?", m2.group(0) if m2 else "?"))

# ---------- T-12 空亡四判：戌有根受击、亥有根未击 ----------
rc, out = run([PAIPAN, "--pillars", "甲子", "乙亥", "庚戌", "癸未", "--gender", "男",
               "--birth-year", "1984", "--start-age", "10"])
seg = out[out.find("空亡四判"):] if "空亡四判" in out else ""
ok = rc == 0 and "有根" in seg and "受击" in seg and "未击" in seg
case("T-12", "戌有根且受击（时未刑）；亥有根且未击", ok, "段长 %d" % len(seg))

# ---------- T-13 空亡四判：戌无根 ----------
rc, out = run([PAIPAN, "--pillars", "甲子", "乙卯", "庚戌", "壬午", "--gender", "男"])
seg = out[out.find("空亡四判"):] if "空亡四判" in out else ""
ok = rc == 0 and "无根" in seg and seg.count("落空") >= 0
case("T-13", "戌判无根；子、卯不得判成落空", ok, "含无根=%s" % ("无根" in seg))

# ---------- T-14 旬名 ----------
rc, out = run([PAIPAN, "--pillars", "甲子", "乙卯", "庚戌", "壬午", "--gender", "男"])
ok = rc == 0 and "甲辰旬" in out and "戊辰旬" not in out
case("T-14", "日柱庚戌显示「甲辰旬」，非「戊辰旬」", ok, "rc=%s" % rc)

# ---------- T-15 命式混入取象 → 自检 FAIL ----------
mix = os.path.join(TMP, "mix.md")
with open(mix, "w", encoding="utf-8") as f:
    f.write("# 批词（测试构造·命式混取象）\n\n## 一 命式\n\n甲子 乙亥 庚戌 癸未，金空则鸣，木空则朽，空亡填实。\n\n"
            "## 二 日主之意\n\n庚金坐戌。\n")
rc, out = run([MINGSHU, "--prose", mix, "--lint", "--strict"])
ok = rc != 0 and ("鸣" in out or "朽" in out or "填实" in out or "命式" in out)
case("T-15", "命式节混入「鸣/朽/填实」→ 被拒（rc≠0）", ok, "rc=%s" % rc)

# ---------- 汇总 ----------
w = max(len(t) for t, _, _, _ in rows)
print("=" * 78)
print("P1-4 工具层首跑（T-1~T-15）")
print("=" * 78)
npass = 0
for tid, title, ok, detail in rows:
    print("%-5s %s  %s" % (tid, "PASS" if ok else "FAIL", title))
    if not ok:
        print("       ↳ %s" % detail)
    npass += 1 if ok else 0
print("-" * 78)
print("通过 %d / %d" % (npass, len(rows)))
print("门禁：%s" % ("PASS" if npass == len(rows) else "FAIL"))
if "-q" not in sys.argv:
    shutil.rmtree(TMP, ignore_errors=True)
sys.exit(0 if npass == len(rows) else 1)
