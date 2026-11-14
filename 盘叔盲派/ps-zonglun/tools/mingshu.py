#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盘叔盲派 · 命书排印器（ps-mingshu）：把批词排成一本「纸墨命书」HTML。

**本器只排印，不断命。** 形制取盲派原书的命稿排法：乾坤造起头、四柱干支分两行横排、
大运按起运虚岁横排；章节走盲派七段（体例见 `references/命书体例.md`）。 断语一个字都不产——正文全部来自 `--prose` 给的批词；
本器只负责：① 把排盘结果排成「命式」；② 把结构事实排成「已知因」；
③ 把大运、流年排成表；④ 给整本配版面、编号、纸墨、页尾。

为什么要有它：`ps-zonglun` 的统一报告带规则编号、置信度、命例编号，那是**批者底稿**；
交给命主的那一本，必须一条编号都不见——这是两件东西，不能混。（规矩见 `references/命书体例.md`）

用法：
    # 0. 先排盘（四柱入口或生日入口均可）
    python tools/paipan.py --pillars 甲子 乙亥 庚戌 癸未 --gender 男 \
        --birth-year 1984 --start-age 10 --json > pan.json

    # 1. 排印命书（批词先按体例写好）
    python tools/mingshu.py --pan pan.json --prose 批词.md \
        --calib "实证校准版：命主提供 7 项实况，推翻 2 处" --out 命书_甲子乙亥庚戌癸未.html

    # 2. 只验收批词，不出 HTML（交付前必跑）
    python tools/mingshu.py --pan pan.json --prose 批词.md --lint

    # 3. 自检
    python tools/mingshu.py --self-test
"""
import argparse
import datetime
import json
import os
import re
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

CN = "〇一二三四五六七八九十"
STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
JIAZI = [STEMS[i % 10] + BRANCHES[i % 12] for i in range(60)]

# 命书里一个都不许出现的「工程标记」。命主看的本子只讲判断与实事，
# 台账留给底稿。命中即报警，不许静默放过。
FORBIDDEN = [
    (r"MP-[^\s，。；]{1,12}", "规则编号（MP-）"),
    (r"U-\d{3,}", "命例编号（U-####）"),
    (r"[瑰珍真][-－]\d{1,3}", "子技能规则编号"),
    (r"★", "星级符号"),
    (r"〔?[确倾存]\S{0,2}断〕?", None),   # 分寸语允许，不拦（占位，不报）
    (r"置信度", "置信度字样"),
    (r"证据等级", "证据等级字样"),
    (r"E[1-6]\b", "证据等级代号"),
    (r"仲裁\s*#?\s*\d", "仲裁编号"),
    (r"块号", "出处块号"),
    (r"规则集|规则库|规则索引", "规则集字样"),
    (r"router|skill|SKILL\.md", "实现层字样"),
    (r"待批|TODO|占位", "未清占位"),
]

# 命式一节只许摆结构事实（四柱／十神／藏干／纳音／旬空／关系／宾主）。
# 「金空则鸣」「木空则朽」「填实」这类是断法层的活，混进命式＝把结论当事实。
# 只在「命式」节内查，正文别处该说照说。
MINGSHI_FORBID = [
    (r"则[鸣发流朽陷飞]", "五行空取象（则鸣／则朽…）"),
    (r"[鸣朽]", "五行空取象字（鸣／朽）"),
    (r"填实", "取象断语（填实）"),
    (r"主[贵富凶贫贱祸福]", "吉凶断语（主贵／主凶…）"),
    (r"必[发达贵凶败]", "吉凶断语（必发／必贵…）"),
]

_MINGSHI_HEAD = re.compile(r"^#{1,4}\s*[一二三四五六七八九十\d]*[、.．:：\s]*命式\s*$")


def _mingshi_span(text):
    """定位批词里手写的「命式」节，返回 (起行, 止行)，行号 1-based，含止行。找不到返 None。"""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines, 1):
        if _MINGSHI_HEAD.match(line.strip()):
            start = i
            continue
        if start is not None and re.match(r"^#{1,2}\s", line.strip()):
            return start, i - 1
    if start is not None:
        return start, len(lines)
    return None


HTML_CSS = """
  :root{
    --paper:#fbf9f3; --ink:#1b1a17; --ink2:#4a463f; --red:#8c1c13;
    --line:#c9c1ae; --soft:#efe9db;
  }
  *{box-sizing:border-box;}
  body{
    margin:0; padding:0 0 60px;
    background:#e8e4da;
    font-family:"Songti SC","SimSun","Source Han Serif SC","Noto Serif CJK SC",serif;
    color:var(--ink); line-height:1.9; font-size:15.5px;
  }
  .sheet{
    max-width:820px; margin:28px auto; background:var(--paper);
    padding:56px 62px 72px; box-shadow:0 2px 24px rgba(0,0,0,.14);
    border-top:6px solid var(--red);
  }
  header{text-align:center; margin-bottom:8px;}
  .kicker{font-size:12.5px; letter-spacing:.5em; color:var(--red); margin-bottom:18px;}
  h1{font-size:40px; letter-spacing:.18em; margin:0 0 6px; font-weight:600;}
  /* 命稿抬头：盲派原书排法（乾坤造／干支两行／大运横排），不加边框、不加底色 */
  .minggao{margin:16px 0 4px; text-align:center;}
  table.mg{margin:0 auto; width:auto; border:none; background:none; border-collapse:collapse;}
  table.mg th{border:none; background:none; padding:0 14px 0 0; text-align:right;
    width:3em; font-weight:normal; font-size:12.5px; color:var(--ink2); letter-spacing:.12em;
    white-space:nowrap; vertical-align:middle;}
  table.mg td{border:none; background:none; width:2.5em; text-align:center; padding:1px 0;
    font-size:27px; line-height:1.5; letter-spacing:0; vertical-align:middle;}
  table.mg td.gz{font-weight:600;}
  .tbl table.lly td:nth-child(-n+4), .tbl table.lly th:nth-child(-n+4){white-space:nowrap;}
  .tbl table.lly td:nth-child(5){text-align:left;}
  .note.jy{color:var(--ink); border-left:2px solid var(--red); padding-left:9px;}
  .klab2{font-size:12.5px; color:var(--red); letter-spacing:.12em;
    margin:22px 0 8px; padding-top:12px; border-top:1px solid var(--line);}
  .mg-yun{font-size:12px; color:var(--ink); letter-spacing:0;
    text-align:center; margin:15px 0 0; word-spacing:0;}
  .mg-yun .yn{display:inline-block; white-space:nowrap; margin:0 .16em;}
  .mg-yun .now{font-style:normal; color:var(--red); font-size:11px;
    vertical-align:super; margin-left:1px; letter-spacing:0;}
  .mg-yun .klab{color:var(--red); letter-spacing:.1em; margin-right:6px;
    white-space:nowrap;}
  .mg-yun b{font-weight:600;}
  .sub{font-size:13px; color:var(--ink2); letter-spacing:.2em;}
  .meta{text-align:center; font-size:13px; color:var(--ink2); margin:10px 0 30px;}
  blockquote{
    margin:0 0 34px; padding:14px 18px; background:#f4efe3;
    border-left:3px solid var(--red); font-size:13.5px; color:var(--ink2);
    line-height:1.85;
  }
  blockquote p{text-indent:0; margin:0 0 6px;}
  blockquote p:last-child{margin-bottom:0;}
  h2{
    font-size:19px; letter-spacing:.14em; margin:46px 0 18px; padding-bottom:8px;
    border-bottom:1px solid var(--line); font-weight:600;
  }
  h2 .no{color:var(--red); margin-right:.6em; font-size:15px;}
  h3{font-size:15.5px; margin:26px 0 8px; letter-spacing:.1em; color:var(--red); font-weight:600;}
  p{margin:0 0 14px; text-align:justify; text-indent:2em;}
  p.flat{text-indent:0;}
  table{width:100%; border-collapse:collapse; margin:18px 0 22px; font-size:13.5px; line-height:1.7;}
  th,td{border:1px solid var(--line); padding:8px 10px; text-align:center;}
  th{background:var(--soft); font-weight:600; letter-spacing:.06em;}
  td.l{text-align:left;}
  .hi{color:var(--red); font-weight:600;}
  .note{font-size:13px; color:var(--ink2);}
  .yun{border-left:2px solid var(--line); padding:2px 0 2px 20px; margin:0 0 22px;}
  .yun > b{display:block; font-size:15px; letter-spacing:.1em; margin-bottom:6px;}
  .yun p{text-indent:0; margin:0 0 10px;}
  .yun.now{border-left:2px solid var(--red); background:#fdf9f2; padding-left:18px;
    border-radius:0 4px 4px 0;}
  ol.yao{margin:0 0 14px; padding-left:0; list-style:none; counter-reset:y;}
  ol.yao li{position:relative; padding-left:2.4em; margin-bottom:14px; text-align:justify;}
  ol.yao li:before{
    counter-increment:y; content:counter(y,upper-roman);
    position:absolute; left:0; top:0; color:var(--red); font-size:13px; letter-spacing:.05em;
  }
  ul.plain{margin:0 0 14px; padding-left:1.6em;}
  ul.plain li{margin-bottom:8px; text-align:justify;}
  ul.kong li{margin-bottom:14px; line-height:1.9;}
  .klab{display:inline-block; width:2.2em; color:var(--ink2); font-size:12px;
    letter-spacing:.1em;}
  .wx .lab{display:inline-block; width:2.2em; font-weight:600;}
  .wx .bar{display:inline-block; height:12px; border-radius:3px; vertical-align:middle;
    margin:0 8px; min-width:5px;}
  .wx .n{font-size:12.5px; color:var(--ink2);}
  .c-jin{background:#cdb03a;} .c-mu{background:#6da35f;} .c-shui{background:#5f8fb4;}
  .c-huo{background:#bf4536;} .c-tu{background:#b08a5a;}
  .tag{display:inline-block; border:1px solid var(--red); color:var(--red); border-radius:3px;
    padding:1px 8px; font-size:12px; letter-spacing:.12em; margin:0 5px; vertical-align:middle;}
  .tag.now{background:var(--red); color:#fff;}
  details{margin:18px 0 10px; border:1px solid var(--line); border-radius:6px;
    overflow:hidden; background:#fdfbf5;}
  details summary{cursor:pointer; padding:10px 16px; font-size:13px; letter-spacing:.1em;
    color:var(--red); background:var(--soft); user-select:none;}
  details table{margin:10px 0;}
  footer{margin-top:52px; padding-top:18px; border-top:1px solid var(--line);
    font-size:12.5px; color:var(--ink2); line-height:1.8; text-align:center; letter-spacing:.2em;}
  .promo{margin-top:46px; border:1px solid var(--line); background:#fdf9f0;
    padding:28px 34px 24px; text-align:center;}
  .promo .ptitle{font-size:12px; color:var(--red); letter-spacing:.5em; margin:0 0 18px;}
  .promo p{font-size:13.5px; line-height:2; color:var(--ink); text-align:center; margin:0 0 10px;}
  .promo p.body{text-align:justify; text-indent:2em; font-size:13px; line-height:1.95;}
  .promo a{color:var(--red); text-decoration:none; border-bottom:1px solid rgba(140,28,19,.35);}
  .promo .qrs{display:flex; justify-content:center; align-items:flex-start;
    gap:30px; margin:16px 0 6px; flex-wrap:wrap;}
  .promo figure{margin:0;}
  .promo figure img{display:block; background:#fff; border:1px solid var(--line); padding:7px;}
  .promo figure.wx img{width:116px;}
  .promo figure.pay img{width:152px;}
  .promo figcaption{font-size:11.5px; color:var(--ink2); letter-spacing:.2em; margin-top:8px;}
  .promo .adbox{margin:22px 0 8px; padding:20px 24px 10px; border:1px solid var(--line);
    background:#fff; text-align:left;}
  .promo .adbox h4{font-size:13.5px; color:var(--red); letter-spacing:.2em; font-weight:normal;
    text-align:center; margin:0 0 12px;}
  .promo .adbox p{text-align:left; font-size:13px; line-height:1.95; margin:0 0 10px;
    text-indent:2em;}
  .promo .adbox p.nind{text-indent:0; text-align:center;}
  .promo .adbox .cta{display:inline-block; margin-top:2px; padding:7px 20px;
    border:1px solid var(--red); border-radius:2px; letter-spacing:.14em; font-size:12.5px;}
  .promo .disc{font-size:11.5px; color:var(--ink2); margin-top:10px; letter-spacing:.1em;}
  .tbl{overflow-x:auto;}
  @media (max-width:720px){
    .sheet{padding:26px 15px 48px; margin:0;}
    .tbl table{font-size:12.5px;}
    .tbl th, .tbl td{white-space:nowrap; padding:7px 6px;}
    /* 流月表：与命局一列文字长，放开换行；前四列仍不拆字 */
    .tbl table.lly th, .tbl table.lly td{white-space:normal; padding:6px 5px;}
    .tbl table.lly td:nth-child(-n+4), .tbl table.lly th:nth-child(-n+4){white-space:nowrap;}
    .tbl table.lly td:nth-child(5){text-align:left; font-size:11.5px;}
    table.mg td{font-size:23px; width:2.3em;}
    table.mg th{font-size:11.5px; width:2.8em; padding-right:10px;}
    .mg-yun{font-size:12px;}
    .promo{padding:20px 16px 16px;}
    .promo .qrs{gap:20px; margin:12px 0 4px;}
    .promo figure.pay img{width:132px;}
    .promo figure.wx img{width:100px;}
    .promo .adbox{padding:15px 15px 8px;}
    .promo p.body, .promo .adbox p{font-size:12.5px; line-height:1.9;}
  }
  @media print{
    body{background:#fff;} .sheet{box-shadow:none; margin:0; max-width:none; padding:22mm 18mm;}
    .tbl{overflow:visible;} .tbl table{min-width:0; font-size:12.5px;}
    details > *{display:block !important;}
  }
"""


# ---------------- 小工具 ----------------
def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _inline(s):
    """行内标记：**粗** → b；==朱红== → span.hi；`代码` → 去标记留字。"""
    s = _esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"==(.+?)==", r'<span class="hi">\1</span>', s)
    s = s.replace("`", "")
    return s


def cn_num(n):
    if n <= 10:
        return CN[n] if n < 10 else "十"
    if n < 20:
        return "十" + CN[n % 10]
    if n < 100:
        return CN[n // 10] + "十" + (CN[n % 10] if n % 10 else "")
    return str(n)


def cn_no(n):
    """章节序号：一、二…十一…"""
    return cn_num(n)


def cn_year(y):
    d = "〇一二三四五六七八九"
    return "".join(d[int(c)] for c in str(y)) + "年"


def year_gz(y):
    return JIAZI[(y - 4) % 60]


def _wx_of_char(c):
    m = {"甲乙": "木", "丙丁": "火", "戊己": "土", "庚辛": "金", "壬癸": "水",
         "寅卯": "木", "巳午": "火", "辰戌丑未": "土", "申酉": "金", "亥子": "水"}
    for k, v in m.items():
        if c in k:
            return v
    return ""


def _fill(pan):
    """把排盘 json 补齐成渲染要用的形状；生日入口与四柱入口都能吃。"""
    a = dict(pan)
    a.setdefault("detail", [])
    a.setdefault("dayun", [])
    a.setdefault("dayun_rows", [])
    a.setdefault("kong_hits", [])
    a.setdefault("kong_judge", [])
    a.setdefault("relations", [])
    a.setdefault("lushen", {})
    a.setdefault("liuyue", None)
    a.setdefault("wuxing", {})
    a.setdefault("missing", [])
    a.setdefault("borders", [])
    a["input"] = a.get("input") or {}
    return a


# ---------------- 结构块（全部 E6，不带断语） ----------------
def _minggao_html(a):
    """命稿抬头：照盲派原书排法——乾坤造起头、四柱干支分两行横排、大运按起运虚岁横排。

    原书即如此：「乾：庚乙癸庚／辰酉卯申」＋「大运：06 丙戌 16 丁亥 26 戊子 36 己丑」。
    这里不加十神、不加纳音，那属于下面的「命式细目」；抬头要的就是干净。
    """
    p = a["pillars"]
    if len(p) < 4:
        return ""
    g = a["input"].get("gender")
    lab = "乾造" if g == "男" else ("坤造" if g == "女" else "四柱")
    rows = ['<div class="minggao">',
            '<table class="mg">',
            '<tr><th>%s</th>%s</tr>' % (lab, "".join('<td class="gz">%s</td>' % x[0] for x in p)),
            '<tr><th></th>%s</tr>' % "".join('<td class="gz">%s</td>' % x[1] for x in p),
            '</table>']
    rows_d = a.get("dayun_rows") or []
    if rows_d:
        seg = []
        for x in rows_d:
            tag = '<i class="now">今</i>' if x["now"] else ""
            seg.append('<span class="yn"><b>%02d</b> %s%s</span>' % (x["xu1"], x["gz"], tag))
        rows.append('<p class="mg-yun"><span class="klab">大运</span>%s</p>' % "".join(seg))
    elif a.get("dayun"):
        rows.append('<p class="mg-yun"><span class="klab">大运</span>%s</p>'
                    % "".join('<span class="yn">%s</span>' % x for x in a["dayun"]))
    rows.append("</div>")
    return "\n".join(rows)


def _keystone_html(a):
    """命式：四柱一张表。十神、藏干、纳音、旬空，逐柱排开。"""
    out = ['<div class="tbl"><table>',
           '<tr><th>柱</th><th>干支</th><th>天干十神</th><th>藏干·十神</th>'
           '<th>纳音</th><th>本柱旬空</th></tr>']
    for d in a["detail"]:
        out.append('<tr><td>%s</td><td><b>%s</b></td><td>%s</td><td class="l">%s</td>'
                   '<td>%s</td><td>%s</td></tr>' % (
                       d["pos"], d["gz"], d["stem_ss"],
                       "／".join("%s·%s" % (c["gan"], c["ss"]) for c in d["cang"]),
                       d["nayin"], "".join(d["kong"])))
    out.append("</table></div>")
    return "\n".join(out)


def _wuxing_html(a):
    wx = a["wuxing"] or {}
    if not wx:
        return ""
    total = sum(wx.values()) or 1
    rows = ['<p class="flat"><b>五行</b>（天干＋藏干等权计，共 %d 字）：</p>' % total,
            '<p class="flat wx">']
    cls = {"木": "c-mu", "火": "c-huo", "土": "c-tu", "金": "c-jin", "水": "c-shui"}
    for e in "木火土金水":
        w = int(180 * wx.get(e, 0) / total) + 5
        rows.append('<span class="lab">%s</span>'
                    '<span class="bar %s" style="width:%dpx"></span>'
                    '<span class="n">%d</span><br>' % (e, cls[e], w, wx.get(e, 0)))
    rows.append("</p>")
    if a["missing"]:
        rows.append('<p class="flat">缺：<span class="hi">%s</span>。</p>' % "、".join(a["missing"]))
    else:
        rows.append('<p class="flat">五行俱全。</p>')
    return "\n".join(rows)


def _near_year(years, now):
    """只取最近一次：今年及以后取最小，否则取最大。底稿留全量，命书只标本轮。"""
    if not years:
        return None
    if now:
        later = [y for y in years if y >= now]
        if later:
            return later[0]
    return years[-1]


def _guanxi_html(a):
    """关系矩阵：刑冲合穿拱、天干五合相冲、干支暗合、禄刃。只摆关系，不下吉凶。

    这一节是给批者用的地网——**漏断多半漏在这里**：批词只写得下三两条，
    但盘上实际有几条，须一次摆齐，批者才知道自己用了几条、漏了几条。
    """
    rels = a.get("relations") or []
    ls = a.get("lushen") or {}
    if not rels and not ls:
        return ""
    out = ['<p class="flat"><b>关系</b>'
           '（刑冲合穿拱、天干合冲、干支暗合、禄刃；只摆结构，不论吉凶）：</p>']
    if rels:
        out.append('<table>')
        out.append('<tr><th>类</th><th>字</th><th>位</th><th>注</th></tr>')
        for x in rels:
            out.append('<tr><td>%s</td><td><b>%s</b></td><td>%s</td>'
                       '<td class="l">%s</td></tr>' % (
                           _esc(x["类"]), _esc(x["字"]),
                           _esc("、".join(x["位"])), _esc(x["注"] or "—")))
        out.append("</table>")
    if ls:
        out.append('<p class="flat"><b>日主 %s</b>　禄：%s　刃：%s</p>' % (
            _esc(ls.get("日主", "")), _esc(ls.get("禄", "—")), _esc(ls.get("刃", "—"))))
    return "\n".join(out)


def _kong_html(a, now_year=None):
    if not a["kong_hits"]:
        return '<p>旬空：年柱、日柱两查，四支无落空。</p>'
    p = a["pillars"]
    yk, rk = "".join(_kong_of(p[0])), "".join(_kong_of(p[2]))
    head = ('<p>空亡两查（年柱定一旬、日柱定一旬，两个都比对四支）：年柱%s旬空%s，'
            '日柱%s旬空%s。</p>' % (p[0], yk, p[2], rk))
    items = "".join("<li>%s柱%s（%s旬）空 %s → <b>%s柱%s 落空</b>。</li>" % (
        k["旬位"], k["旬"], k["旬名"], "".join(k["空"]), k["位"], k["落"])
        for k in a["kong_hits"])
    out = [head, '<ul class="plain">%s</ul>' % items]

    # 查过而无犯的那一旬必须明写：只列落空者，读者不知道另一旬究竟查没查。
    checked = {h["旬"] for h in a["kong_hits"]}
    miss = ["%s%s旬（空%s）四支无犯" % (nm, gz, kw)
            for nm, gz, kw in (("年柱", p[0], yk), ("日柱", p[2], rk)) if gz not in checked]
    if miss:
        out.append('<p class="note">%s。</p>' % "；".join(miss))

    # 空亡细判：四件结构事实——落于主位还是宾位、有无根、有无冲穿刑来击、何年值冲合。
    # 只摆事实。「金空则鸣」鸣不鸣、鸣出什么，属断法层取象，此节一个字不下。
    kj = a.get("kong_judge") or []
    if kj:
        now = now_year or datetime.date.today().year
        rows = []
        for k in kj:
            rows.append("".join([
                "<li><b>%s（%s）</b>　%s支　由 %s" % (
                    k["落"], k["五行"], "、".join(k["位"]), "、".join(k["旬"])),
                '<br><span class="klab">位</span>%s——%s' % (
                    k.get("宾主") or "—", k.get("宾主由") or "—"),
                '<br><span class="klab">根</span>%s——%s' % (k["根"], k["根由"]),
                '<br><span class="klab">击</span>%s' % ("；".join(k["击"]) if k["击"] else "未受冲穿刑"),
                '<br><span class="klab">值</span>%s　<span class="klab">冲</span>%s　'
                '<span class="klab">合</span>%s' % (
                    _near_year(k["值"], now) or "—",
                    _near_year(k["冲"], now) or "—",
                    _near_year(k["合"], now) or "—"),
                "</li>"]))
        out.append('<p class="note">空亡细判（只摆结构，不论吉凶；值冲合只标本轮，'
                   '十二年一值、一冲、一合，不作应期断。同一支可既得同气又受刑穿，'
                   '根与击两栏须合看）</p>')
        out.append('<ul class="plain kong">%s</ul>' % "".join(rows))
    return "".join(out)


def _kong_of(gz):
    i = JIAZI.index(gz) if gz in JIAZI else 0
    return (JIAZI[(i // 10 * 10 + 10) % 60][1], JIAZI[(i // 10 * 10 + 11) % 60][1])


def _dayun_table(a):
    rows = a.get("dayun_rows") or []
    if not rows:
        if not a.get("dayun"):
            return ""
        return '<p class="note">大运：%s。起运岁未定，故只列干支，不标公历年。</p>' % \
               "　".join(a["dayun"])
    out = ['<table>', '<tr><th>运</th><th>干支</th><th>虚岁</th><th>公历</th></tr>']
    for k, x in enumerate(rows, 1):
        tag = ' <span class="tag now">今</span>' if x["now"] else ""
        out.append('<tr><td>第%s运</td><td><b>%s</b>%s</td><td>%d–%d</td><td>%d–%d</td></tr>'
                   % (cn_num(k), x["gz"], tag, x["xu1"], x["xu2"], x["y1"], x["y2"]))
    out.append("</table>")
    return "\n".join(out)


def _liunian_table(a, start_year, n=6):
    by = a["input"].get("birth_year")
    rows = a.get("dayun_rows") or []
    out = ['<table>', '<tr><th>年</th><th>干支</th><th>虚岁</th><th>所行大运</th></tr>']
    for y in range(start_year, start_year + n):
        xu = (y - by + 1) if by else None
        yun = next((x["gz"] for x in rows if x["y1"] <= y <= x["y2"]), None)
        out.append('<tr><td>%d</td><td>%s</td><td>%s</td><td>%s</td></tr>'
                   % (y, year_gz(y), xu if xu else "—", yun or "—"))
    out.append("</table>")
    return "\n".join(out)


def _md(iso, year):
    """月日缩写；跨到次年的加「次年」，免得「01-05」被读成当年正月。"""
    return ("次年" if int(iso[:4]) != int(year) else "") + iso[5:]


def _liuyue_html(a, embedded=True):
    """本年流月表：只摆月建、干支、起止、与命局之关系。

    与命式同一条纪律——**不断吉凶、不作应期断**。流月只回答「哪个月被引动」，
    被引动之后应什么事，归正文。
    """
    lly = a.get("liuyue")
    if not lly or not lly.get("rows"):
        return ""
    head = ('<p class="klab2">本年流月　%s年（%s）　按节分月</p>' % (lly["year"], lly["year_gz"])
            if embedded else "")
    out = [head, '<div class="tbl"><table class="lly">',
           '<tr><th>节</th><th>建</th><th>干支</th><th>起止</th><th>与命局</th></tr>']
    for x in lly["rows"]:
        a1, a2 = _md(x["起"], lly["year"]), _md(x["止"], lly["year"])
        if a1.startswith("次年") and a2.startswith("次年"):
            a2 = a2[2:]                       # 两端同属次年，只标一次
        out.append('<tr><td>%s</td><td>%s</td><td><b>%s</b></td><td>%s—%s</td><td>%s</td></tr>'
                   % (x["节"], x["建"], x["干支"], a1, a2,
                      "；".join(x["系"]) or "—"))
    out.append("</table></div>")
    jy = lly.get("jiaoyun") or {}
    if jy:
        bits = []
        if jy.get("events"):
            for ev in jy["events"]:
                bits.append("本年：<b>%s %s</b>，交第%s运%s（%s段起）" % (
                    ev["日"], ev["时辰"], cn_no(ev["运序"]),
                    ev["干支"], ev["段"]))
        else:
            bits.append("本年无交运")
        if jy.get("下次"):
            nx = jy["下次"]
            bits.append("下一次：%s %s，交第%s运%s（%s段起）" % (
                nx["日"], nx["时辰"], cn_no(nx["运序"]), nx["干支"], nx["段"]))
        out.append('<p class="note jy">交运　%s｜起运 %s 年（虚岁%s）。%s。'
                   '交运时刻按年命纳音定，<b>每五年一交</b>：前五年天干主事、后五年地支主事，'
                   '故运支在支段未起之前只在字上，不算已到。交运月只标换气，'
                   '<b>交运本身不论吉凶</b>。</p>' % (
                       jy.get("基准", ""), jy.get("起运年", ""),
                       cn_no(jy.get("起运虚岁") or 1), "；".join(bits)))
    out.append('<p class="note">月建以「节」为界（立春起寅、小寒起丑），月干五虎遁。'
               '此表只标干支与冲合穿刑拱合、值空冲空，不判轻重——'
               '流月只管「哪个月动」，动出什么事，看上文。</p>')
    return "\n".join(out)


def _yizhiyin_html(a):
    """已知因：只摆结构事实，一句断语都不下——这是命书的诚实处。"""
    i = a["input"]
    ps = a["pillars"]
    if len(ps) < 4:
        return ""
    day = ps[2][0]
    items = [
        "四柱：%s　%s　%s　%s；%s。" % (
            ps[0], ps[1], ps[2], ps[3],
            "乾造" if i.get("gender") == "男" else ("坤造" if i.get("gender") == "女" else "性别未注")),
        "日主「%s」，生于「%s」月；月支本气「%s」。" % (
            day, ps[1][1], (a["detail"][1]["cang"][0]["gan"] if a["detail"] else "")),
        "四柱天干十神：年「%s」、月「%s」、时「%s」。" % (
            a["detail"][0]["stem_ss"], a["detail"][1]["stem_ss"], a["detail"][3]["stem_ss"]),
        "大运%s排。" % ("顺" if a["forward"] else "逆") +
        ("交运虚岁 %d%s。" % (a["start"].get("交运虚岁", 0),
                            "（%d 年交运）" % (i["birth_year"] + a["start"].get("交运虚岁", 0) - 1)
                            if i.get("birth_year") else "")
         if a.get("start") and a["start"].get("交运虚岁") else "起运岁未报。"),
        "旬空：年柱旬空%s，日柱旬空%s。" % ("".join(_kong_of(ps[0])), "".join(_kong_of(ps[2]))),
        "五行：%s。" % ("、".join("%s%d" % (e, v) for e, v in a["wuxing"].items())
                       + ("（缺%s）" % "、".join(a["missing"]) if a["missing"] else "（俱全）")
                       if a["wuxing"] else "未统计。"),
    ]
    body = '<ol class="yao">%s</ol>' % "".join("<li>%s</li>" % _inline(x) for x in items)
    if a["borders"]:
        body += '<p class="note">时辰边界：%s</p>' % "；".join(a["borders"])
    return body


# ---------------- 批词解析 ----------------
def parse_prose(text):
    """md → [(节题, [块…])]。首个 h2 之前的散句挂空题；支持 > 引文、- 列表、### 小标题。

    **首个 h2 之前的内容一律视为元信息，不进命书**——批词抬头的「本件为版面范本」
    「体例：一、命式……」是写给批者自己的，排进命书等于把底稿塞给命主看。
    整篇无 h2 时才退化处理（把 h2 前的内容当作唯一一节）。
    """
    secs = []
    pre = []
    cur = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            t = line[3:].strip()
            t = re.sub(r"^[〇一二三四五六七八九十百千0-9]+\s*[、.．·]\s*", "", t)
            t = re.sub(r"^第[〇一二三四五六七八九十0-9]+[节卷章]\s*", "", t)
            cur = (t, [])
            secs.append(cur)
        elif line.startswith("# "):
            continue
        else:
            if cur is None:
                pre.append(line)
                continue
            cur[1].append(line)
    if not secs:
        return [("", [x for x in pre if x.strip()])] if any(x.strip() for x in pre) else []
    return [(t, b) for t, b in secs if t or any(x.strip() for x in b)]


# 大运小目：批词里的「### 第3运 戊寅（虚岁30–39，2013–2022）」排成左侧竖线的小目，
# 与命书体例的「大运批导」版式一致。识别不出来的一律按普通小标题排。
YUN_RE = re.compile(r"第[〇一二三四五六七八九十0-9]+运|运\s*[（(]\s*虚岁")


def _items_html(lines, blocks, cur_yun=None):
    out = []
    buf_p, buf_ul, buf_ol, buf_quote, buf_yun = [], [], [], [], []
    open_yun = [False]

    def close_yun():
        if open_yun[0]:
            out.append("</div>")
            open_yun[0] = False

    def flush():
        if buf_p:
            out.append("<p>%s</p>" % _inline(" ".join(buf_p)))
            del buf_p[:]
        if buf_ul:
            out.append('<ul class="plain">%s</ul>' % "".join(
                "<li>%s</li>" % _inline(x) for x in buf_ul))
            del buf_ul[:]
        if buf_ol:
            out.append('<ol class="yao">%s</ol>' % "".join(
                "<li>%s</li>" % _inline(x) for x in buf_ol))
            del buf_ol[:]
        if buf_quote:
            out.append("<blockquote>%s</blockquote>" % "".join(
                "<p>%s</p>" % _inline(x) for x in buf_quote))
            del buf_quote[:]
        if buf_yun:
            out.append('<div class="yun">%s</div>' % "".join(buf_yun))
            del buf_yun[:]

    for line in lines:
        s = line.strip()
        # 占位符
        m = re.fullmatch(r"\{\{(.+?)\}\}", s)
        if m:
            flush()
            key = m.group(1).strip()
            if key in blocks:
                out.append(blocks[key])
            elif key.startswith("流年表"):
                out.append(blocks.get("流年表", ""))
            elif key.startswith("大运表"):
                out.append(blocks.get("大运表", ""))
            continue
        if not s:
            flush()
            continue
        if s.startswith("### "):
            flush()
            close_yun()
            if YUN_RE.search(s[4:]):
                now = ' now' if (cur_yun and cur_yun in s[4:]) else ''
                out.append('<div class="yun%s"><b>%s</b>' % (now, _inline(s[4:])))
                open_yun[0] = True
            else:
                out.append("<h3>%s</h3>" % _inline(s[4:]))
            continue
        if s == ">":
            continue          # 引用块内的空行，不得落成 <p>&gt;</p>
        if s.startswith("> "):
            buf_quote.append(s[2:])
            continue
        if re.match(r"^[-*]\s+", s):
            buf_ul.append(re.sub(r"^[-*]\s+", "", s))
            continue
        if re.match(r"^\d+[.)]\s*", s):
            buf_ol.append(re.sub(r"^\d+[.)]\s*", "", s))
            continue
        buf_p.append(s)
    flush()
    close_yun()
    return "\n".join(out)


# ---------------- 验收 ----------------
def dangwei_note(prose, pan):
    """档位自洽：自称「细批」却未附流月，是最容易露的一处。返回提示或空串。"""
    m = re.search(r"「?(简批|小批|中批|大批|细批)」?\s*档", prose)
    if not m:
        return ""
    dw = m.group(1)
    has = bool((pan or {}).get("liuyue"))
    if dw == "细批" and not has:
        return ("批词自称「细批」，但排盘未附流月——细批＝大批＋流月＋校准，缺流月即档位不符。"
                "补 `--liuyue <年>` 重出排盘，或把自称改为「大批」。")
    if dw in ("简批", "小批", "中批") and has:
        return "排盘附了流月，批词却自称「%s」——档位不符，改称「细批」或去掉流月。" % dw
    return ""


def lint(text):
    """命书硬规矩：零工程标记；命式节零断语。返回 [(行号, 命中, 类型)]。"""
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        for pat, name in FORBIDDEN:
            if name is None:
                continue
            m = re.search(pat, line)
            if m:
                hits.append((i, m.group(0), name))
    span = _mingshi_span(text)
    if span:
        lines = text.splitlines()
        for i in range(span[0], min(span[1], len(lines)) + 1):
            line = lines[i - 1]
            for pat, name in MINGSHI_FORBID:
                m = re.search(pat, line)
                if m:
                    hits.append((i, m.group(0), name + "／命式节"))
                    break          # 一行只报一处，够定位，不刷屏
    return hits


WEIXIN_ID = "cpms1988"
CANGPAN_URL = "https://mp.weixin.qq.com/s/9NFaItizyhEpjDzmTyEcPQ"

# 素材随包内置（references/assets/）。路径相对本文件，别改。
ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "references", "assets")

# 档 2 备用：随包素材缺失时才走远程（国内网络常不可达，故不作首选）
QR_REMOTE = {
    "appreciation.jpg": "https://cdn.jsdelivr.net/gh/x3747991-ship-it/"
                        "sanmingtonghui-bazi-skillpack@main/appreciation.jpg",
    "wechat_qr.jpg": "https://cdn.jsdelivr.net/gh/x3747991-ship-it/"
                     "weili-qianli-bazi-skillpack@main/wechat_qr.jpg",
}

# 体积下限：小于这个数多半是坏图或占位符，宁可降级也不出破图
QR_MIN_BYTES = 3072


def _qr_figure(fname, alt, cls):
    """一档：本地素材 base64 内嵌（单文件自包含，拷走／离线／转发都能显示）；
    二档：远程地址；三档：两者皆无 → 返回空串，由调用方只剩纯文字。"""
    p = os.path.join(ASSETS_DIR, fname)
    if os.path.exists(p) and os.path.getsize(p) >= QR_MIN_BYTES:
        import base64
        b64 = base64.b64encode(open(p, "rb").read()).decode("ascii")
        return ('<figure class="%s"><img src="data:image/jpeg;base64,%s" alt="%s">'
                '<figcaption>%s</figcaption></figure>' % (cls, b64, alt, alt))
    u = QR_REMOTE.get(fname)
    if u:
        return ('<figure class="%s"><img src="%s" alt="%s" '
                'onerror="this.parentNode.style.display=\'none\'">'
                '<figcaption>%s</figcaption></figure>' % (cls, u, alt, alt))
    return ""


def _promo_html(now_year=None):
    """页尾推广块：赞赏码／盘叔微信／苍盘命书三件，嵌在「命书终」之后。

    文字是保底，图片是增强：**两条图路都不通时仍要给出微信号与体验链接**，
    不得输出会裂的图片标记，也不得为显示图片反复换图床（规矩见
    `references/推广尾注.md`）。
    """
    pay = _qr_figure("appreciation.jpg", "赞赏码", "pay")
    wx = _qr_figure("wechat_qr.jpg", "盘叔微信", "wx")
    qrs = ('<div class="qrs">%s%s</div>' % (pay, wx)) if (pay or wx) else ""

    sys_txt = ("以上命书由<b>「盘叔盲派」技能包</b>排印，基于段建业盲派体系"
               "（《命理珍宝》《命理真宝》《命理瑰宝》《盲派中级命理学》"
               "《2010 高级面授笔记》《函授教材》）与夏仲奇铁口直断、"
               "苏国圣金口诀、高德臣金口诀四派融会。断语出自七层调度与跨包仲裁，"
               "排盘与版式属结构计算。")
    cp1 = ("如果你对盲派体用做功、或「子平三法合参」的命盘仍有疑惑，"
           "欢迎体验一下盘叔历时半年、用精选的数千当代真人命例投喂训练出的"
           "「苍盘命书」智能体。苍盘命书专注于融合各派优势，通过独创的验盘算法，"
           "三重交叉校验每个命盘人生的真实喜用。")
    cp2 = ("它不靠模棱两可的话术、让你自己去「对号入座」，而是通过十个章节、"
           "数万字的细致分析，配合数据表格与趋势图，把八字结构、性格底层、人生阶段，"
           "以及未来可能的发展方向，尽可能清晰地一步步拆解出来。")
    cp3 = ("如果你也想看看，自己的八字背后，到底隐藏着怎样的人生轨迹——"
           "欢迎报名成为<b>【苍盘命书免费体验官】</b>。")

    return """
<div class="promo">
  <p class="ptitle">命　书　之　外</p>
  <p class="body">%s</p>
  %s
  <p>如果觉得有用，欢迎赞赏支持；想交流命理，<b>微信：%s</b>。</p>
  <p>更多命理玄学相关 AI 技能与干货 SKILL，请关注公众号 <b>【野生你盘叔】</b>。</p>

  <div class="adbox">
    <h4>关于「苍盘命书」</h4>
    <p>%s</p>
    <p>%s</p>
    <p>%s</p>
    <p class="nind"><a class="cta" href="%s">苍盘命书免费体验官 · 直通链接</a></p>
  </div>

  <p class="disc">本节为独立推广内容，不是命理判断，也不是命盘资料。</p>
  <p class="disc">本命书内容源自传统术数体系，供文化研究与参考，
  不构成医疗、法律、投资等任何决策依据。</p>
</div>""" % (sys_txt, qrs, WEIXIN_ID, cp1, cp2, cp3, CANGPAN_URL)


def render_html(a, prose, calib=None, now_year=None, title=None, promo=True):
    i = a["input"]
    g = i.get("gender")
    meta = "乾造" if g == "男" else ("坤造" if g == "女" else "性别未注")
    if i.get("birth_year"):
        meta += "　%s生" % cn_year(i["birth_year"])
    if a.get("start") and a["start"].get("交运虚岁"):
        meta += "　%s岁起运" % cn_num(a["start"]["交运虚岁"])
    elif a.get("start") and a["start"].get("起运日"):
        meta += "　%s交运" % a["start"]["起运日"]

    pillars = [_minggao_html(a)]

    blocks = {
        "命式": _keystone_html(a),
        "五行": _wuxing_html(a),
        "关系": _guanxi_html(a),
        "空亡": _kong_html(a, now_year),
        "大运表": _dayun_table(a),
        "流年表": _liunian_table(a, now_year or datetime.date.today().year, 6),
    }

    head_note = ('<blockquote><p><b>怎么看这份命书</b>　本门不看身强身弱的扶抑平衡，'
                 '不取用神，只看「用哪个体、以什么方式、多高效率去取财官」；'
                 '身旺身弱仅用于判断日主能否承载财官，不作喜忌。</p>')
    if calib:
        head_note += "<p>%s</p>" % _inline(calib)
    head_note += ("<p>断语按本事之结构实据而立，凡结构不足以定者，明写「看结构是」「多半」"
                  "「这一步要留意」，不作必中之断。</p></blockquote>")

    body = ["<!DOCTYPE html>", '<html lang="zh-Hans">', "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<title>%s</title>" % (_esc(title) if title else
                                  "命书　" + "　".join(a["pillars"])),
            "<style>%s</style>" % HTML_CSS, "</head>", "<body>", '<div class="sheet">', "",
            "<header>",
            '<div class="kicker">细　批　终　身</div>',
            "<h1>命　书</h1>",
            '<div class="sub">盘叔盲派 · 体用做功</div>',
            "</header>", "",
            "\n".join(pillars),
            '<div class="meta">%s</div>' % meta,
            head_note, ""]

    # 一、命式（自动）：只摆结构事实，一句断语不下。
    #    抬头已在页首（命稿排法），此处是细目：十神／藏干／纳音／旬空、五行、空亡、时辰边界。
    body += ['<h2 id="s1"><span class="no">%s</span>命式</h2>' % cn_no(1),
             _keystone_html(a),
             _wuxing_html(a),
             _guanxi_html(a),
             _kong_html(a, now_year)]
    if a["borders"]:
        body.append('<p class="note">时辰边界：%s</p>' % "；".join(_inline(b) for b in a["borders"]))
    body.append("")

    cur_yun = (a.get("current") or {}).get("gz")
    fu_liuyue = _liuyue_html(a, embedded=True)
    lly_injected = False
    n = 1          # 「命式」即第一节，批词首节应为「二」
    for t, lines in parse_prose(prose):
        if not t:
            body.append(_items_html(lines, blocks, cur_yun))
            body.append("")
            continue
        if re.fullmatch(r"命式|已知因", t):
            continue      # 自动生成的两节，批词里不再重排
        n += 1
        is_fu = t.startswith("附") or t in ("存疑与边界", "校准与边界")
        raw = "\n".join(lines)
        lead = ""
        # 规范兜底：运章必带大运表、年章必带流年表。批词忘了写占位符，
        # 排印器替他补上——命书少了这张表，命主就不知道自己在第几运。
        if "大运" in t and "{{大运表}}" not in raw:
            lead = _dayun_table(a)
        elif "流年" in t and "{{流年表" not in raw:
            lead = _liunian_table(a, a.get("now_year") or datetime.date.today().year, 6)
        if is_fu:
            body += ['<h2 id="s%d">%s</h2>' % (n, _inline(t)),
                     lead, _items_html(lines, blocks, cur_yun), ""]
        else:
            body += ['<h2 id="s%d"><span class="no">%s</span>%s</h2>' % (n, cn_no(n), _inline(t)),
                     lead, _items_html(lines, blocks, cur_yun), ""]
        if fu_liuyue and not lly_injected and "流年" in t:
            body += [fu_liuyue, ""]
            lly_injected = True

    # 批词没写流年一节时，流月单独成附——宁可多一节，不把表塞进别处
    if fu_liuyue and not lly_injected:
        body += ['<h2 id="s%d">附、本年流月</h2>' % (n + 1),
                 _liuyue_html(a, embedded=False), ""]

    body += ["<footer>命　书　终</footer>", "",
             '<div style="text-align:center; font-size:12px; color:var(--ink2); '
             'letter-spacing:.15em; margin-top:14px;">%s%s月批写</div>'
             % (cn_year((now_year or datetime.date.today().year)),
                cn_num(datetime.date.today().month)),
             _promo_html(now_year) if promo else "", "", "</div>", "</body>", "</html>"]
    return "\n".join(body)


# ---------------- 自检 ----------------
def self_test():
    bad = []
    a = {
        "input": {"mode": "pillars", "pillars": ["甲子", "乙亥", "庚戌", "癸未"],
                  "gender": "男", "birth_year": 1984, "start_age": 10},
        "pillars": ["甲子", "乙亥", "庚戌", "癸未"],
        "detail": [
            {"pos": "年", "gz": "甲子", "stem_ss": "偏财", "branch_ss": "伤官",
             "cang": [{"gan": "癸", "ss": "伤官"}], "nayin": "海中金", "kong": ["戌", "亥"]},
            {"pos": "月", "gz": "乙亥", "stem_ss": "正财", "branch_ss": "食神",
             "cang": [{"gan": "壬", "ss": "食神"}, {"gan": "甲", "ss": "偏财"}],
             "nayin": "山头火", "kong": ["申", "酉"]},
            {"pos": "日", "gz": "庚戌", "stem_ss": "日主", "branch_ss": "偏印",
             "cang": [{"gan": "戊", "ss": "偏印"}], "nayin": "钗钏金", "kong": ["寅", "卯"]},
            {"pos": "时", "gz": "癸未", "stem_ss": "伤官", "branch_ss": "正印",
             "cang": [{"gan": "己", "ss": "正印"}], "nayin": "杨柳木", "kong": ["申", "酉"]},
        ],
        "wuxing": {"木": 4, "火": 2, "土": 2, "金": 2, "水": 3}, "missing": [],
        "forward": True, "dayun": ["丙子"], "start": {"交运虚岁": 10},
        "dayun_rows": [{"gz": "丙子", "xu1": 10, "xu2": 19, "y1": 1993, "y2": 2002, "now": False}],
        "kong_hits": [{"旬": "甲子", "旬位": "年", "旬名": "甲子", "空": ["戌", "亥"],
                       "落": "亥", "位": "月"}],
        "kong_judge": [
            {"落": "亥", "五行": "水", "位": ["月"], "旬": ["年柱甲子旬"],
             "宾主": "宾位", "宾主由": "落于月",
             "根": "有根", "根由": "年子同气相扶；藏干「甲」透于天干", "击": [],
             "值": [1995], "冲": [2001], "合": [1998]},
            {"落": "戌", "五行": "土", "位": ["日"], "旬": ["年柱甲子旬"],
             "宾主": "主位", "宾主由": "落于日",
             "根": "有根", "根由": "时未同气相扶", "击": ["相刑·时未"],
             "值": [1994], "冲": [2000], "合": [1999]},
        ],
        "relations": [
            {"类": "六穿", "位": ["年", "时"], "字": "子未", "注": "穿为暗损，不显于面"},
            {"类": "相刑", "位": ["日", "时"], "字": "戌未", "注": "刑主磨损"},
            {"类": "拱", "位": ["月", "时"], "字": "亥未", "注": "三合木局缺卯"},
        ],
        "lushen": {"日主": "庚", "禄": "申（四支不见）", "刃": "酉（四支不见）"},
        "liuyue": {"year": 2026, "year_gz": "丙午",
                   "jiaoyun": {"基准": "海中金 → 金命 → 处暑当日申时", "起运年": 1993,
                               "起运虚岁": 10,
                               "events": [],
                               "下次": {"日": "2028-08-22", "时辰": "申时",
                                        "运序": 4, "段": "地支", "干支": "己卯"}},
                   "rows": [
            {"建": "卯", "节": "惊蛰", "干支": "辛卯",
             "起": "2026-03-05", "止": "2026-04-05",
             "系": ["三合木局成（亥卯未）", "同运支卯"]},
            {"建": "戌", "节": "寒露", "干支": "戊戌",
             "起": "2026-10-08", "止": "2026-11-07",
             "系": ["同日支戌", "值空"]},
        ]},
        "borders": [], "checks": [], "all_pass": True,
    }
    html = render_html(a, "# 批词 · 甲子乙亥庚戌癸未（乾造）\n"
                          "> 本件为版面范本，不作对该造真实人生的定论。\n\n"
                          "## 二、日主之意\n此造庚金生亥月，日主之意在求财。\n\n"
                          "## 五、大运逐运\n第一运行丙子。\n\n"
                          "## 七、结语\n- 一句\n", now_year=2026)
    for must in ("命书", "命式", "日主之意", "大运逐运", "结语", "庚戌", "丙子", "1993"):
        if must not in html:
            bad.append("HTML 缺 %s" % must)
    # 命稿抬头：乾坤造 + 干支两行 + 大运横排；不得再出现子平式的四柱竖牌
    for must in ('class="minggao"', "乾造", "乙亥", "<b>10</b>"):
        if must not in html:
            bad.append("命稿抬头缺 %s" % must)
    if 'class="pillars"' in html:
        bad.append("不该再出四柱竖牌（盲派用干支两行横排）")
    if "已知因" in html:
        bad.append("「已知因」是子平版旧章，盲派七段不设此章")
    # 编号章须 4（命式/日主之意/大运逐运/结语）；附节（附、本年流月）不占编号
    if html.count('<span class="no">') != 4:
        bad.append("编号章节应为 4（命式/日主之意/大运逐运/结语），实得 %d"
                   % html.count('<span class="no">'))
    if "{{" in html:
        bad.append("有占位符未替换")
    # 空亡细判：三件结构事实须排进「命式」，且一个字断语都不许带
    for must in ("空亡细判", "相刑·时未", "有根", "1994"):
        if must not in html:
            bad.append("命式缺空亡细判字段 %s" % must)
    for forbid in ("金空则鸣", "鸣", "朽", "填实"):
        if forbid in html:
            bad.append("命式不得夹断语「%s」（取象归断法层）" % forbid)
    # 关系矩阵：须进命式，且宾主须标出
    for must in ("关系</b>", "六穿", "子未", "三合木局缺卯", "主位——落于日",
                 "宾位——落于月", "禄：申（四支不见）"):
        if must not in html:
            bad.append("命式缺关系／宾主字段 %s" % must)
    # 批词抬头的元信息不得排进命书（否则命主第一眼读到「本件为版面范本」）
    if "版面范本" in html:
        bad.append("批词 h2 之前的元信息被排进正文（交付事故）")
    if "<p>&gt;</p>" in html:
        bad.append("空引用行被排成 <p>&gt;</p>")
    # 页尾批写年月须完整
    if "月批写" not in html:
        bad.append("页尾「批写」缺「月」字")
    # 流月：须进命书，且只摆结构
    for must in ("本年流月", "三合木局成（亥卯未）", "值空", "月建以「节」为界",
                 "处暑当日申时", "本年无交运", "2028-08-22", "每五年一交"):
        if must not in html:
            bad.append("流月表缺 %s" % must)
    if html.count("<tr><td>惊蛰</td>") != 1:
        bad.append("流月表应排出行，实得 %d" % html.count("<tr><td>惊蛰</td>"))
    # 交运行须钉死「第几运、哪段起」（v1.8 P1-5）
    for must in ("交第四运己卯（地支段起）", "下一次："):
        if must not in html:
            bad.append("交运行缺「第几运／哪段起」：%s" % must)
    # 档位自洽：自称细批而无流月，应被拦
    if not dangwei_note("本件按「细批」档排印。", {}):
        bad.append("自称细批而无流月，档位检查应报")
    if dangwei_note("本件按「细批」档排印。", a):
        bad.append("有流月时，细批不应报档位不符")
    # lint：带编号的批词必须被拦
    hits = lint("见 MP-断-091 与 U-0123，星级 ★★")
    if len(hits) < 3:
        bad.append("lint 应命中规则编号/命例编号/星级，实得 %d" % len(hits))
    if lint("贵造庚金生亥月，财在宾位，合到主位方为我得。"):
        bad.append("干净批词不应被 lint 命中")
    # 命式节零断语：手写命式夹「金空则鸣／填实」须拦；断语写在别处不拦
    if not lint("## 一、命式\n\n甲子 乙亥 庚戌 癸未，金空则鸣，空亡填实。\n"):
        bad.append("命式节夹取象断语未被 lint 拦下")
    if lint("## 二、日主之意\n\n金空则鸣，木空则朽，此造取象在此，不在命式。\n"):
        bad.append("断语写在命式节之外不应被拦")
    if lint("## 一、命式\n\n甲子 乙亥 庚戌 癸未。\n\n## 二、日主之意\n\n金空则鸣。\n"):
        bad.append("命式节无断语时，节外正文的断语不应被报")
    mixed = lint("## 一、命式\n\n甲子 乙亥 庚戌 癸未，金空则鸣。\n\n## 二、日主之意\n\n木空则朽。\n")
    if len(mixed) != 1 or mixed[0][0] != 3:
        bad.append("命式节与正文混排时须只报节内 1 处（实得 %d 处）" % len(mixed))
    # 推广块：默认必嵌，且必须是「自包含图 + 纯文字保底」
    for must in ("命　书　之　外", WEIXIN_ID, "苍盘", CANGPAN_URL,
                 "十个章节", "免费体验官", "独立推广内容"):
        if must not in html:
            bad.append("推广块缺「%s」" % must)
    if "data:image/jpeg;base64," not in html:
        bad.append("推广块缺 base64 内嵌图（素材应在 references/assets/）")
    if 'src="http' in html.split('class="promo"')[-1]:
        bad.append("有本地素材时不该再引远程图")
    if len(_qr_figure("appreciation.jpg", "赞赏码", "pay")) < 2000:
        bad.append("赞赏码未能 base64 内嵌，须查 references/assets/")
    if len(_qr_figure("wechat_qr.jpg", "盘叔微信", "wx")) < 2000:
        bad.append("微信码未能 base64 内嵌，须查 references/assets/")
    bare = render_html(a, "## 三、总评\n一句话。\n", now_year=2026, promo=False)
    if "class=\"promo\"" in bare or "苍盘" in bare:
        bad.append("--no-promo 时不该出现推广块")
    if bad:
        print("自检 FAIL：")
        for b in bad:
            print("  -", b)
        return 1
    print("自检 PASS（5 组 58 项）")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="盘叔盲派·命书排印器（只排印不断命；正文全部来自批词）")
    ap.add_argument("--pan", help="排盘 json（paipan.py --json 的产物）")
    ap.add_argument("--prose", help="批词 markdown（按 references/命书体例.md 写）")
    ap.add_argument("--out", help="输出 HTML 路径")
    ap.add_argument("--calib", help="页首校准声明，如「实证校准版：命主提供 7 项实况，推翻 2 处」")
    ap.add_argument("--now-year", type=int, help="排印当年（默认今年），用于流年表与批写日期")
    ap.add_argument("--title", help="页面标题（默认「命书　四柱」）")
    ap.add_argument("--lint", action="store_true", help="只验收批词（零工程标记），不出 HTML")
    ap.add_argument("--strict", action="store_true", help="lint 有命中即以非零码退出")
    ap.add_argument("--no-promo", action="store_true",
                    help="不嵌页尾推广块（默认嵌；出给客户的白版用这个）")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()

    if a.self_test:
        sys.exit(self_test())
    if not a.prose:
        ap.error("须给 --prose（批词）。本器不写断语——没有批词，就没有命书。")
    if not os.path.exists(a.prose):
        ap.error("--prose %r 不存在" % a.prose)
    prose = open(a.prose, encoding="utf-8").read()

    hits = lint(prose)
    if hits:
        print("⚠ 命书不许出现工程标记，下列 %d 处须改写（台账留给底稿）：" % len(hits))
        for ln, w, nm in hits[:40]:
            print("  第 %d 行　%s　（%s）" % (ln, w, nm))
        if len(hits) > 40:
            print("  …另有 %d 处" % (len(hits) - 40))

    if a.lint:
        if a.pan and os.path.exists(a.pan):
            note = dangwei_note(prose, json.loads(open(a.pan, encoding="utf-8").read()))
            if note:
                print("⚠ 档位：" + note)
                hits = list(hits) + [(0, "档位", note)]
        if hits:
            print("\n验收：不通过（%d 处）" % len(hits))
            sys.exit(1 if a.strict else 0)
        print("验收：通过（批词无工程标记）")
        sys.exit(0)

    if not (a.pan and a.out):
        ap.error("出 HTML 须给 --pan 与 --out")
    if not os.path.exists(a.pan):
        ap.error("--pan %r 不存在；先跑 paipan.py --json > pan.json" % a.pan)
    pan = json.loads(open(a.pan, encoding="utf-8").read())
    if pan.get("error"):
        ap.error("排盘结果带 error（%s），不得据以出命书" % pan["error"])
    note = dangwei_note(prose, pan)
    if note:
        print("⚠ 档位：" + note)
    html = render_html(_fill(pan), prose, a.calib, a.now_year, a.title,
                       promo=not a.no_promo)
    outdir = os.path.dirname(os.path.abspath(a.out))
    if outdir and not os.path.isdir(outdir):
        os.makedirs(outdir, exist_ok=True)
    open(a.out, "w", encoding="utf-8").write(html)
    print("已排印：%s（%d 字）" % (a.out, len(html)))
    if hits:
        print("⚠ 仍带 %d 处工程标记，请回头改批词" % len(hits))
        sys.exit(1 if a.strict else 0)
    sys.exit(0)


if __name__ == "__main__":
    main()
