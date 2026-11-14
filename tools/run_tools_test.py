#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""run_tools_test.py · 工具层测试 T-1～T-15 首跑断言（P1-4）

用途：把《测试用例集_初稿.md》第六节（工具层 T-1～T-15）从「人工对读」
      变成可复跑断言——实测两个器不越界：排盘不出断语、排印不写断语、编号不进命书。

被测件（只读不改）：
  - 盘叔盲派/ps-zonglun/tools/paipan.py  排盘器（--self-test 11 组 84 项）
  - 盘叔盲派/ps-zonglun/tools/mingshu.py 命书排印器（--self-test 5 组 58 项）

用法：
  python tools/run_tools_test.py          # 全量
  python tools/run_tools_test.py -q       # 只出汇总
  python tools/run_tools_test.py --strict # 有 FAIL 时退出码非零（门禁用）

工作目录：中间产物一律落 temp/tt_test/，不写系统临时目录。
"""

import io
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PZ = os.path.join(ROOT, "盘叔盲派", "ps-zonglun", "tools")
TT = os.path.join(ROOT, "temp", "tt_test")

PAN_JSON = os.path.join(TT, "pan.json")
CLEAN_MD = os.path.join(TT, "prose_clean.md")
CLEAN_HTML = os.path.join(TT, "out_clean.html")
NOYUN_MD = os.path.join(TT, "prose_noyun.md")
NOYUN_HTML = os.path.join(TT, "out_noyun.html")
NOPH_MD = os.path.join(TT, "prose_noph.md")
NOPH_HTML = os.path.join(TT, "out_noph.html")
DIRTY_MD = os.path.join(TT, "prose_dirty.md")
MSBAD_MD = os.path.join(TT, "prose_mingshi_bad.md")

CLEAN_PROSE = u"""# 命书　甲子　乙亥　庚戌　癸未

## 一、命式

{{命式}}

## 二、日主之意

庚金生于亥月，天寒水冷；戌中藏丁，未中有己，土厚能生，寒金不至于失所。

## 三、做功与层次

年柱甲子偏财坐伤官，月上乙亥正财透出，财星成势；身有未戌之土为托，属中上之局。

## 四、逐事直断

### 财禄

财星两透，宜以技艺、文书取财，不宜重仓压货。

### 婚姻

妻宫戌土为库，逢未相刑，婚事宜迟不宜早。

## 五、大运逐运

{{大运表}}

### 第1运 丙子（虚岁10–19，1993–2002）

丙火透出暖局，子水助食伤，读书期间顺中带寒。

## 六、流年举要

{{流年表}}

## 七、结语

财旺有托，宜技艺立身，忌重仓硬碰。

## 附、说明

本命书据来客所报四柱排印，未做真太阳时校正；所断为趋势，不作定命之论。
"""

NOYUN_PROSE = u"""# 命书　甲子　乙亥　庚戌　癸未

## 一、命式

{{命式}}

## 二、日主之意

庚金生于亥月，天寒水冷；戌中藏丁，土厚能生。

{{大运表}}

## 三、流年举要

{{流年表}}

## 四、结语

财旺有托，宜技艺立身。
"""

NOPH_PROSE = u"""# 命书　甲子　乙亥　庚戌　癸未

## 一、命式

{{命式}}

## 二、日主之意

庚金生于亥月，天寒水冷；戌中藏丁，土厚能生。

## 三、结语

财旺有托，宜技艺立身。
"""

DIRTY_PROSE = u"""# 命书

## 一、命式

{{命式}}

## 五、大运逐运

{{大运表}}

见 MP-断-091，星级 ★★。
"""

MSBAD_PROSE = u"""# 命书

## 一、命式

庚金则鸣，土厚填实，戌库不漏。

## 二、日主之意

庚金生于亥月。
"""

CN_DIGIT = {0: u"〇", 1: u"一", 2: u"二", 3: u"三", 4: u"四", 5: u"五",
            6: u"六", 7: u"七", 8: u"八", 9: u"九"}

YN_RE = re.compile(u'<span class="yn"><b>(\\d+)</b>\\s*([^<\\s]+)'
                   u'(<i class="now">\\u4eca</i>)?</span>')

RESULTS = []


# ---------------------------------------------------------------- 基础工具
def ensure_dir():
    if not os.path.isdir(TT):
        os.makedirs(TT, exist_ok=True)


def w(path, text):
    ensure_dir()
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(text)


def rd(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def invoke(script, args):
    cmd = [sys.executable, os.path.join(PZ, script)] + list(args)
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=ROOT)
    return (r.returncode,
            r.stdout.decode("utf-8", "replace"),
            r.stderr.decode("utf-8", "replace"))


def paipan(*args):
    return invoke("paipan.py", args)


def tool(*args):
    """调用包根 tools/ 下的验收脚本（check_yingqi.py 等）。"""
    cmd = [sys.executable, os.path.join(ROOT, "tools", args[0])] + list(args[1:])
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=ROOT)
    return (r.returncode,
            r.stdout.decode("utf-8", "replace"),
            r.stderr.decode("utf-8", "replace"))


def mingshu(*args):
    return invoke("mingshu.py", args)


def jload(text):
    return json.loads(text)


def by_code(checks, code):
    for c in checks or []:
        if c.get("code") == code:
            return c
    return {}


def cn_of(n):
    """1–99 的中文数字（只求命书 meta 的「X岁起运」比对）。"""
    if n < 10:
        return CN_DIGIT[n]
    if n < 20:
        return u"十" + (CN_DIGIT[n % 10] if n % 10 else u"")
    return CN_DIGIT[n // 10] + u"十" + (CN_DIGIT[n % 10] if n % 10 else u"")


def build_pan():
    """用 paipan --json 生成 UTF-8 的 pan.json（禁用 PowerShell 重定向，避免 UTF-16）。"""
    rc, so, se = paipan("--pillars", u"甲子", u"乙亥", u"庚戌", u"癸未",
                        "--gender", u"男", "--birth-year", "1984",
                        "--start-age", "10", "--json")
    if rc != 0:
        raise RuntimeError("paipan --json rc=%s：%s" % (rc, (se or so)[:200]))
    w(PAN_JSON, so)
    return jload(so)


def check(cid, name, fn):
    try:
        ok, note = fn()
    except Exception as e:  # noqa: BLE001
        ok, note = False, u"异常：%s" % e
    RESULTS.append((cid, name, bool(ok), note))


# ---------------------------------------------------------------- T-1～T-3
def t1():
    rc, so, se = paipan("--pillars", u"甲子", u"乙亥", u"庚戍", u"癸未", "--gender", u"男",
                        "--birth-year", "1984", "--start-age", "10", "--json")
    if rc != 0:
        return False, u"rc=%s 不应停手：%s" % (rc, (se or so)[:120])
    d = jload(so)
    p01 = by_code(d.get("checks"), "P01")
    ok = bool(p01.get("ok")) and u"误写" in p01.get("msg", "") and d["pillars"][2] == u"庚戌"
    return ok, u"P01✅ %s｜四柱 %s" % (p01.get("msg", "")[:44], " ".join(d["pillars"]))


def t2():
    rc, so, se = paipan("--pillars", u"甲丑", u"乙亥", u"庚戌", u"癸未", "--gender", u"男", "--json")
    d = jload(so) if so.strip().startswith("{") else {}
    p01 = by_code(d.get("checks"), "P01")
    ok = (rc != 0 and not p01.get("ok")
          and u"非六十甲子内之合法组合" in p01.get("msg", "")
          and not d.get("detail"))
    return ok, u"rc=%s｜P01❌ %s｜detail 空=%s" % (rc, p01.get("msg", "")[:44], not d.get("detail"))


def t3():
    rc, so, se = paipan("--date", "1984-11-12", "--time", "14:45", "--lon", "116.12",
                        "--gender", u"男", "--birth-year", "1984", "--json")
    if rc != 0:
        return False, u"rc=%s：%s" % (rc, (se or so)[:120])
    d = jload(so)
    st = d.get("start") or {}
    ok = (d["input"].get("tst", "").endswith("14:44")
          and d["pillars"] == [u"甲子", u"乙亥", u"庚戌", u"癸未"]
          and st.get(u"年") == 8 and st.get(u"月") == 2 and st.get(u"日") == 18
          and st.get(u"交运虚岁") == 10)
    return ok, u"真太阳时 %s｜四柱 %s｜折 %s年%s月%s日 交运虚岁%s" % (
        d["input"].get("tst"), " ".join(d["pillars"]),
        st.get(u"年"), st.get(u"月"), st.get(u"日"), st.get(u"交运虚岁"))


def t4():
    rc, so, se = paipan("--date", "1984-11-12", "--gender", u"男", "--json")
    blob = se + so
    ok = rc != 0 and "--time" in blob
    return ok, u"rc=%s｜%s" % (rc, blob.strip().split("\n")[-1][:70])


def t5():
    # 立冬 1984-11-07 13:32:10，取 13:38（真太阳时 13:54，距节气 22 分钟 ≤45 → P09 ❌）
    rc, so, se = paipan("--date", "1984-11-07", "--time", "13:38", "--lon", "120.0",
                        "--gender", u"男", "--birth-year", "1984", "--json")
    d = jload(so) if so.strip().startswith("{") else {}
    p09 = by_code(d.get("checks"), "P09")
    ok = (rc != 0 and not p09.get("ok") and u"复核" in p09.get("msg", ""))
    return ok, u"rc=%s｜P09❌ %s" % (rc, p09.get("msg", "")[:70])


def t6():
    d = build_pan()
    rows = d.get("dayun_rows") or []
    r4 = rows[3] if len(rows) > 3 else {}
    cur = d.get("current") or {}
    ok = (r4.get("gz") == u"己卯" and r4.get("xu1") == 40 and r4.get("xu2") == 49
          and r4.get("y1") == 2023 and r4.get("y2") == 2032 and r4.get("now") is True
          and cur.get("gz") == u"己卯")
    return ok, u"第4运 %s 虚岁%s–%s 公历%s–%s now=%s" % (
        r4.get("gz"), r4.get("xu1"), r4.get("xu2"), r4.get("y1"), r4.get("y2"), r4.get("now"))


# ---------------------------------------------------------------- T-7～T-10（排印器）
def t7():
    w(DIRTY_MD, DIRTY_PROSE)
    rc, so, se = mingshu("--prose", DIRTY_MD, "--lint", "--strict")
    m = re.search(u"不通过（(\\d+) 处）", so)
    n = int(m.group(1)) if m else 0
    ok = (rc != 0 and u"不通过" in so and n >= 2
          and "MP-" in so and u"★" in so)
    return ok, u"rc=%s｜命中 %s 处（规则编号＋星级）" % (rc, n)


def t8():
    build_pan()
    w(CLEAN_MD, CLEAN_PROSE)
    rc, so, se = mingshu("--prose", CLEAN_MD, "--lint", "--strict")
    lint_ok = rc == 0 and u"验收：通过" in so
    rc2, so2, se2 = mingshu("--pan", PAN_JSON, "--prose", CLEAN_MD,
                            "--out", CLEAN_HTML, "--no-promo")
    if rc2 != 0:
        return False, u"排印 rc=%s：%s" % (rc2, (se2 or so2)[:120])
    html = rd(CLEAN_HTML)
    dirty = {k: html.count(k) for k in ("MP-", u"★", u"置信度")}
    ok = lint_ok and not any(dirty.values())
    return ok, u"lint %s｜HTML %d 字｜MP-/★/置信度 计数 %s" % (
        u"通过" if lint_ok else u"不通过", len(html), dirty)


def _yn_rows(html):
    out = []
    for age, gz, now in YN_RE.findall(html):
        out.append((int(age), gz, bool(now)))
    return out


def t9():
    build_pan()
    # a) 有 {{大运表}} 但无「大运逐运」章 → 表照出
    w(NOYUN_MD, NOYUN_PROSE)
    rca, soa, sea = mingshu("--pan", PAN_JSON, "--prose", NOYUN_MD,
                            "--out", NOYUN_HTML, "--no-promo")
    a_rows = _yn_rows(rd(NOYUN_HTML)) if rca == 0 and os.path.exists(NOYUN_HTML) else []
    # b) 连占位符也没有 → 工具在运章自动补表
    w(NOPH_MD, NOPH_PROSE)
    rcb, sob, seb = mingshu("--pan", PAN_JSON, "--prose", NOPH_MD,
                            "--out", NOPH_HTML, "--no-promo")
    b_rows = _yn_rows(rd(NOPH_HTML)) if rcb == 0 and os.path.exists(NOPH_HTML) else []
    ok = len(a_rows) == 8 and len(b_rows) == 8
    return ok, u"无运章但带占位符：%d 运（rc=%s）｜无占位符：%d 运（rc=%s）" % (
        len(a_rows), rca, len(b_rows), rcb)


def t10():
    pan = build_pan()
    if not os.path.exists(CLEAN_HTML):
        t8()
    html = rd(CLEAN_HTML)
    # 四柱逐字
    m1 = re.search(u'<tr><th>乾造</th>(.*?)</tr>\\s*<tr><th></th>(.*?)</tr>', html, re.S)
    stems = re.findall(u'<td class="gz">(.)</td>', m1.group(1)) if m1 else []
    branches = re.findall(u'<td class="gz">(.)</td>', m1.group(2)) if m1 else []
    got = ["".join(p) for p in zip(stems, branches)]
    # 大运逐运
    yns = _yn_rows(html)
    want = [(r["xu1"], r["gz"], r["now"]) for r in (pan.get("dayun_rows") or [])]
    # 起运岁
    age = (pan.get("start") or {}).get(u"交运虚岁")
    age_ok = bool(age) and (u"%s岁起运" % cn_of(age) in html)
    ok = (got == pan.get("pillars") and [x[0] for x in yns] == [x[0] for x in want]
          and [x[1] for x in yns] == [x[1] for x in want]
          and [x[2] for x in yns] == [x[2] for x in want] and age_ok)
    return ok, u"四柱 %s（pan %s）｜大运 %d/%d 逐字一致｜%s岁起运 %s" % (
        " ".join(got), " ".join(pan.get("pillars") or []), len(yns), len(want),
        cn_of(age) if age else "?", u"一致" if age_ok else u"不一致")


def t11():
    rc1, so1, se1 = paipan("--self-test")
    rc2, so2, se2 = mingshu("--self-test")
    m1 = re.search(u"(\\d+) 组 (\\d+) 项", so1)
    m2 = re.search(u"(\\d+) 组 (\\d+) 项", so2)
    g1, i1 = (int(m1.group(1)), int(m1.group(2))) if m1 else (0, 0)
    g2, i2 = (int(m2.group(1)), int(m2.group(2))) if m2 else (0, 0)
    # 初稿基线：paipan 7 组 27 项 / mingshu 4 组 30 项；实际须不低于基线
    ok = (rc1 == 0 and rc2 == 0 and "PASS" in so1 and "PASS" in so2
          and g1 >= 7 and i1 >= 27 and g2 >= 4 and i2 >= 30)
    return ok, u"排盘 %d 组 %d 项（基线 7/27）｜排印 %d 组 %d 项（基线 4/30）｜均 PASS" % (
        g1, i1, g2, i2)


# ---------------------------------------------------------------- T-12～T-14（空亡/旬名）
def t12():
    rc, so, se = paipan("--pillars", u"甲子", u"乙亥", u"庚戌", u"癸未", "--gender", u"男",
                        "--birth-year", "1984", "--start-age", "10", "--json")
    if rc != 0:
        return False, u"rc=%s：%s" % (rc, (se or so)[:100])
    d = jload(so)
    sol = {x[u"落"]: x for x in (d.get("kong_judge") or [])}
    xu, hai = sol.get(u"戌", {}), sol.get(u"亥", {})
    ok = (hai.get(u"根") == u"有根" and not hai.get(u"击")
          and xu.get(u"根") == u"有根"
          and any(u"相刑" in s and u"未" in s for s in (xu.get(u"击") or [])))
    return ok, u"戌 %s/%s｜亥 %s/%s" % (
        xu.get(u"根"), u"、".join(xu.get(u"击") or []) or u"未击",
        hai.get(u"根"), u"、".join(hai.get(u"击") or []) or u"未击")


def t13():
    rc, so, se = paipan("--pillars", u"甲子", u"乙卯", u"庚戌", u"壬午", "--gender", u"男",
                        "--birth-year", "1984", "--start-age", "10", "--json")
    if rc != 0:
        return False, u"rc=%s：%s" % (rc, (se or so)[:100])
    d = jload(so)
    items = d.get("kong_judge") or []
    sol = {x[u"落"]: x for x in items}
    xu = sol.get(u"戌", {})
    xuns = [s for x in items for s in (x.get(u"旬") or [])]
    bad_xun = [s for s in xuns if not (s.startswith(u"年柱") or s.startswith(u"日柱"))]
    ok = (xu.get(u"根") == u"无根" and not xu.get(u"击")
          and u"子" not in sol and not bad_xun)
    return ok, u"戌 %s/%s｜落空 %s｜旬取 %s" % (
        xu.get(u"根"), u"、".join(xu.get(u"击") or []) or u"未击",
        u"、".join(sorted(sol)), u"、".join(sorted(set(xuns))))


def t14():
    rc, so, se = paipan("--pillars", u"甲子", u"乙卯", u"庚戌", u"壬午", "--gender", u"男",
                        "--birth-year", "1984", "--start-age", "10", "--json")
    if rc != 0:
        return False, u"rc=%s：%s" % (rc, (se or so)[:100])
    d = jload(so)
    ri = [x for x in (d.get("detail") or []) if x.get("pos") == u"日"]
    kong = ri[0].get("kong") if ri else []
    blob = so
    ok = (kong == [u"寅", u"卯"] and u"戊辰旬" not in blob and u"甲辰旬" in blob)
    return ok, u"日柱 %s 空亡 %s（甲辰旬：空寅卯）｜全文无「戊辰旬」=%s" % (
        ri[0].get("gz") if ri else "?", u"、".join(kong or []), u"戊辰旬" not in blob)


def t15():
    w(MSBAD_MD, MSBAD_PROSE)
    rc, so, se = mingshu("--prose", MSBAD_MD, "--lint", "--strict")
    ok = rc != 0 and u"命式节" in so
    line = [ln.strip() for ln in so.split("\n") if u"命式节" in ln]
    return ok, u"rc=%s｜%s" % (rc, (line[0] if line else so.strip()[:70]))


# ---------------------------------------------------------------- T-16～T-17（应期自测/神煞台账）
def t16():
    rc, so, se = tool("check_yingqi.py", "--self-test")
    ok = (rc == 0 and u"错例 3/3 全抓" in so and u"零误报" in so)
    line = [ln.strip() for ln in so.split("\n") if u"错例" in ln]
    return ok, u"rc=%s｜%s" % (rc, (line[-1] if line else (se or so).strip()[:70]))


def t17():
    p = os.path.join(ROOT, u"盘叔盲派", u"ps-shensha", u"references", u"核对台账.md")
    if not os.path.exists(p):
        return False, u"缺 references/核对台账.md"
    s = rd(p)
    n_z = s.count(u"\n### ")
    ok = (n_z >= 10 and u"不一致 0 项" in s and u"误报 0" in s
          and u"逐字比对" in s and u"起法表" in s)
    rc, so, se = paipan("--pillars", u"甲子", u"乙亥", u"庚戌", u"癸未", "--gender", u"男",
                        "--shensha")
    hit = u"天乙贵人" in so and u"未" in so
    return (ok and rc == 0 and hit), u"台账 %d 造｜不一致 0 项=%s｜落器天乙可跑=%s" % (
        n_z, u"不一致 0 项" in s, rc == 0 and hit)


# ---------------------------------------------------------------- T-18～T-19（行号回读/溯源区）
def t18():
    rc, so, se = tool("check_anchor.py", "--strict")
    drift = [ln.strip() for ln in so.split("\n") if u"行号漂移" in ln]
    lost = [ln.strip() for ln in so.split("\n") if u"文件缺失" in ln]
    ok = (rc == 0 and u"门禁：--strict PASS" in so)
    return ok, u"rc=%s｜%s｜%s" % (rc, (drift[0].strip() if drift else ""),
                                  (lost[0].strip() if lost else ""))


def t19():
    src = os.path.join(ROOT, u"_溯源")
    note = os.path.join(src, u"_缺件说明.md")
    if not (os.path.isdir(src) and os.path.exists(note)):
        return False, u"缺 _溯源/ 或 _缺件说明.md"
    n = sum(len(fn) for dp, dn, fn in os.walk(src))
    s = rd(note)
    rc, so, se = tool("check_refs.py", "--strict")
    import re as _re
    m = dict((k, int(v)) for k, v in _re.findall(u"(可解析|溯源区|未随包|真错)\\s+(\\d+) 处", so))
    ok = (n >= 73 and u"未回填引用" in s and rc == 0
          and m.get(u"真错", 9) == 0 and m.get(u"溯源区", 0) >= 100 and m.get(u"未随包", 99) <= 9)
    return ok, u"溯源 %d 份｜清单未随包 %s 处｜体检溯源 %s／未随包 %s／真错 %s" % (
        n, m.get(u"未随包"), m.get(u"溯源区"), m.get(u"未随包"), m.get(u"真错"))


# ---------------------------------------------------------------- T-20（案例集四、五单元入库对账）
GAN = set(u"甲乙丙丁戊己庚辛壬癸")
ZHI = set(u"子丑寅卯辰巳午未申酉戌亥")


def t20():
    import json as _json
    import re as _re
    cp = os.path.join(ROOT, u"盘叔盲派", u"ps-anli-ku", u"references", u"cases.json")
    md4 = os.path.join(ROOT, u"盘叔盲派", u"ps-anli-ku", u"references", u"案例集_高德臣_第四单元.md")
    md5 = os.path.join(ROOT, u"盘叔盲派", u"ps-anli-ku", u"references", u"案例集_高德臣_第五单元.md")
    idx = os.path.join(ROOT, u"盘叔盲派", u"ps-zonglun", u"references", u"命例索引.md")
    if not all(os.path.exists(x) for x in (cp, md4, md5, idx)):
        return False, u"缺案例集四/五单元 md 或 cases.json / 命例索引"
    d = _json.loads(rd(cp))
    cases = d["cases"]
    sgd = [c for c in cases if c["id"].startswith(u"S-GD-")]
    ids = [c["id"] for c in sgd]
    want = [u"S-GD-%03d" % i for i in range(1, 189)]
    n4 = len(_re.findall(u"^### S-GD-", rd(md4), _re.M))
    n5 = len(_re.findall(u"^### S-GD-", rd(md5), _re.M))
    nidx = rd(idx).count(u"| S-GD-")
    bad = []
    todo = []
    for c in sgd:
        p = (c.get("pillars") or u"").split(u"\u3000")
        if not (c.get("pillars") or u"").strip():
            todo.append(c["id"])
            continue
        if len(p) != 4 or any(len(x) != 2 or x[0] not in GAN or x[1] not in ZHI for x in p):
            bad.append(c["id"])
    ok = (d["meta"]["total"] == len(cases) == 455 and len(sgd) == 188
          and ids == want and n4 == 48 and n5 == 29 and nidx == 188
          and not bad and sorted(todo) == [u"S-GD-135", u"S-GD-154"])
    return ok, u"cases %d／S-GD %d｜四单元 %d 例／五单元 %d 例｜索引 %d 行｜非法四柱 %d｜待补 %s" % (
        d["meta"]["total"], len(sgd), n4, n5, nidx, len(bad), u",".join(todo) or u"无")


# ---------------------------------------------------------------- 主流程
def main():
    argv = sys.argv[1:]
    quiet = "-q" in argv or "--quiet" in argv
    strict = "--strict" in argv
    ensure_dir()

    for cid, name, fn in (
        ("T-1", u"形近字「庚戍」→校正「庚戌」并列疑为误写", t1),
        ("T-2", u"非法四柱「甲丑」→P01❌ 停手不出盘", t2),
        ("T-3", u"生日入口真太阳时与四柱、起运折算", t3),
        ("T-4", u"未给 --time → 拒绝排盘", t4),
        ("T-5", u"生日距节气 ≤45 分钟 → P09❌ 要求复核", t5),
        ("T-6", u"大运表第 4 运＝己卯 虚岁40–49 并标「今」", t6),
        ("T-7", u"批词带 MP-编号/星级 → lint 不通过且退出非零", t7),
        ("T-8", u"干净批词 → lint 通过＋HTML 无工程标记", t8),
        ("T-9", u"{{大运表}} 缺运章照出；无占位符自动补表", t9),
        ("T-10", u"命书四柱/起运岁/大运干支与 pan.json 逐字一致", t10),
        ("T-11", u"两器 --self-test 均 PASS 且不低于初稿基线", t11),
        ("T-12", u"空亡三判：戌有根受击、亥有根未击", t12),
        ("T-13", u"空亡三判：戌无根未击、子卯不误判、不取月时之旬", t13),
        ("T-14", u"旬名核对：日柱庚戌＝甲辰旬（非戊辰旬）", t14),
        ("T-15", u"命式节混入取象 → 自检口径 FAIL（命式节）", t15),
        ("T-16", u"应期 lint --self-test：错例 3/3 全抓、范例零误报", t16),
        ("T-17", u"神煞核对台账在位（10 造×12 项、误报 0）且落器可跑", t17),
        ("T-18", u"行号回读：报告「文件:行」锚点零漂移零失效", t18),
        ("T-19", u"溯源区在位（73 份、真错 0、未随包 ≤9）", t19),
        ("T-20", u"案例集四、五单元入库对账（188 例、编号无缺、待补仅 2 例）", t20),
    ):
        check(cid, name, fn)

    if not quiet:
        for cid, name, ok, note in RESULTS:
            print("%s %-6s %s\n         %s" % ("PASS" if ok else "FAIL", cid, name, note))
    npass = sum(1 for r in RESULTS if r[2])
    nfail = len(RESULTS) - npass
    print("\n工具层首跑：通过 %d／%d，失败 %d" % (npass, len(RESULTS), nfail))
    if nfail:
        print("失败明细：")
        for cid, name, ok, note in RESULTS:
            if not ok:
                print("  - %s %s → %s" % (cid, name, note))
    print("门禁：%s" % ("PASS" if nfail == 0 else "FAIL"))
    return 0 if (nfail == 0 or not strict) else 1


if __name__ == "__main__":
    sys.exit(main())
