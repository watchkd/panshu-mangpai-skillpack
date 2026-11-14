#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""run_router.py · 总控路由/边界/仲裁 首跑断言（P1-4）

用途：把《测试用例集_初稿.md》第一（20 组路由）、三（8 组边界）、四（8 组仲裁）
      从「人工对读」变成可复跑断言——核对真源文件里是否真有支撑该判定的条目。
真源（单一真源原则，只读不改）：
  - 盘叔盲派/ps-zonglun/SKILL.md            （入口判定、第 2 层路由、六·失效场景、通用前置）
  - 盘叔盲派/ps-zonglun/references/路由表.md （主题→主断包真源）
  - 盘叔盲派/ps-zonglun/references/仲裁摘要.md（#1–#22 真源）

用法：
  python tools/run_router.py          # 全量
  python tools/run_router.py -q       # 只出汇总
  python tools/run_router.py --strict # 有 FAIL 时退出码非零（门禁用）
"""

import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, "盘叔盲派", "ps-zonglun", "SKILL.md")
ROUTER = os.path.join(ROOT, "盘叔盲派", "ps-zonglun", "references", "路由表.md")
ARB = os.path.join(ROOT, "盘叔盲派", "ps-zonglun", "references", "仲裁摘要.md")


def load(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def rows(text):
    """按行切，去空行——便于「同一行内共现」式断言。"""
    return [ln for ln in text.split("\n") if ln.strip()]


def row_has(text, *subs):
    """存在某一行同时含全部 subs。"""
    for ln in rows(text):
        if all(s in ln for s in subs):
            return ln
    return None


def has(text, *subs):
    return all(s in text for s in subs)


RESULTS = []


def check(cid, name, fn):
    try:
        ok, note = fn()
    except Exception as e:  # noqa: BLE001
        ok, note = False, "异常：%s" % e
    RESULTS.append((cid, name, bool(ok), note))


def main():
    argv = sys.argv[1:]
    quiet = "-q" in argv
    strict = "--strict" in argv

    sk, rt, ar = load(SKILL), load(ROUTER), load(ARB)

    # ---------- 一、触发路由 20 组（主断须在真源同一行与主题共现） ----------
    def R(topic, pkg, where="rt"):
        def f():
            src = {"rt": rt, "sk": sk, "both": rt + "\n" + sk}[where]
            ln = row_has(src, topic, pkg)
            if ln is None:
                return False, "未找到同一行含「%s」与「%s」" % (topic, pkg)
            return True, ln.strip()[:70]
        return f

    check("R-1", "整体看命→全流程七层", lambda: (
        True, row_has(sk, "整体看命", "全流程七层").strip()[:60])
        if row_has(sk, "整体看命", "全流程七层") else (False, "入口表缺「整体看命→全流程七层」"))
    check("R-2", "官级→ps-duan-zhiye(军官)", R("官运", "ps-duan-zhiye", "both"))
    check("R-3", "财→ps-duan-shizhan(财运)", R("财命", "ps-duan-shizhan", "both"))
    check("R-4", "婚→ps-duan-shizhan(婚姻)", R("婚姻", "ps-duan-shizhan", "both"))
    check("R-5", "职业→ps-duan-zhiye", R("职业", "ps-duan-zhiye", "both"))
    check("R-6", "疾病→ps-duan-shizhan", R("疾病", "ps-duan-shizhan", "both"))
    check("R-7", "牢狱→ps-duan-shizhan(官灾)", R("灾祸", "ps-duan-shizhan", "both"))
    check("R-8", "六亲→ps-duan-shizhan(六亲)", R("六亲", "ps-duan-shizhan", "both"))
    check("R-9", "学历→E1 十一章＋E2 六章", lambda: (
        True, row_has(rt, "学历", "ps-duan-zhongji", "ps-duan-mianshou").strip()[:60])
        if row_has(rt, "学历", "ps-duan-zhongji", "ps-duan-mianshou") else (False, "路由表学历行缺双包"))
    check("R-10", "性格→ps-xiazhongqi-bufa", R("性格", "ps-xiazhongqi-bufa", "both"))
    check("R-11", "应期→ps-duan-zhongji(应期四法)", lambda: (
        True, row_has(rt, "应期", "ps-duan-zhongji").strip()[:60])
        if row_has(rt, "应期", "ps-duan-zhongji") else (False, "路由表应期行主断非 zhongji"))
    check("R-12", "单字取象→ps-duan-xiangfa", lambda: (
        True, row_has(rt, "这字什么意思", "ps-duan-xiangfa").strip()[:60])
        if row_has(rt, "这字什么意思", "ps-duan-xiangfa") else (False, "特殊路由缺「这字什么意思→xiangfa」"))
    check("R-13", "神煞→ps-shensha 只作佐证", lambda: (
        row_has(rt, "神煞查询", "ps-shensha") is not None and has(sk, "神煞只作佐证"),
        "路由表神煞查询行＋通用前置「神煞只作佐证」"))
    check("R-14", "用神→ps-minglizhenbao 元规则层", lambda: (
        row_has(rt, "取什么用神", "ps-minglizhenbao") is not None and has(rt, "不路由其他包"),
        "特殊路由「取什么用神→minglizhenbao 元规则层，不路由其他包」"))

    # ---------- 一、触发路由第 15–20 组（拒绝／让位型，落在 §六） ----------
    check("R-15", "#15 帮我排盘→拒绝/让位", lambda: (
        row_has(sk, "出盘工具", "不是教人排盘") is not None,
        "§六「排盘器是出盘工具，不是教人排盘」"))
    check("R-16", "#16 教排大运→拒绝（问「怎么排」仍让位）", lambda: (
        row_has(sk, "怎么排", "仍让位") is not None,
        "§六「问怎么排仍让位」"))
    check("R-17", "#17 紫微斗数→拒绝（其他术数）", lambda: (
        row_has(sk, "紫微", "拒绝／让位") is not None, "§六 其他术数行"))
    check("R-18", "#18 蒸馏技能包→让位蒸馏技能", lambda: (
        row_has(sk, "蒸馏", "让位蒸馏技能") is not None, "§六 蒸馏行"))
    check("R-19", "#19 什么是空亡→拒绝（概念查询）", lambda: (
        row_has(sk, "单一术语含义", "概念查询，非断命") is not None, "§六 单一术语行"))
    check("R-20", "#20 未给四柱→先补四柱不起手", lambda: (
        row_has(sk, "未给四柱", "无法起手") is not None, "§六 未给四柱行"))

    # ---------- 边界（失效场景 §六） ----------
    def B(cid, name, *subs):
        def f():
            ln = row_has(sk, *subs)
            return (True, ln.strip()[:60]) if ln else (False, "§六 缺条目：%s" % "/".join(subs))
        check(cid, name, f)

    B("B-1", "天气→不受理（非命理）", "与命理无关", "不受理")
    B("B-2", "身强身弱→让位子平", "身强身弱", "让位子平")
    B("B-3", "帮我排盘→拒绝排盘教学", "排盘教学", "拒绝／让位")
    B("B-4", "蒸馏→让位蒸馏技能", "蒸馏", "让位蒸馏技能")
    B("B-5", "什么是串宫→概念查询", "单一术语含义", "概念查询")
    B("B-6", "只给生肖→要求补四柱", "只给生肖", "要求补四柱")
    B("B-7", "无性别问婚→只断无关维度", "无性别", "性别无关维度")
    B("B-8", "问死期→概率化＋免责", "确定死期", "概率化措辞")

    # ---------- 四、冲突仲裁 8 组（对仲裁摘要真源） ----------
    def C(cid, name, *subs):
        def f():
            ln = row_has(ar, *subs)
            return (True, ln.strip()[:60]) if ln else (False, "仲裁摘要缺：%s" % "/".join(subs))
        check(cid, name, f)

    C("C-1", "#1 入墓·墓开判吉", "| 1 |", "墓开", "刑冲破穿开库")
    C("C-2", "#1 入墓·墓闭判凶", "| 1 |", "墓闭", "凶")
    C("C-3", "#2 空库遇冲两说并存", "| 2 |", "两说并存", "实际反馈")
    C("C-4", "#7 官杀为夫·无官看财两见", "| 7 |", "官杀为夫", "无官看财", "E1")
    C("C-5", "#6 男命子女官杀为星位（已改判）", "| 6 |", "官杀为星位主断", "误记")
    C("C-6", "#5 流年只管应期", "| 5 |", "流年只管应期")
    C("C-7", "#10 神煞只作佐证", "| 10 |", "佐证", "不作唯一依据")
    C("C-8", "女命旧语境断语降级", "| 23 |", "女命旧语境断语", "降级不采用")
    check("C-8b", "降级表述落在通用前置不混用清单", lambda: (
        has(sk, "女命断语", "降级"),
        "SKILL 通用前置第 5 条「不混用清单」含女命断语（降级）"))

    # ---------- 汇总 ----------
    if not quiet:
        for cid, name, ok, note in RESULTS:
            print("%s %-42s %s" % ("PASS" if ok else "FAIL", cid + " " + name, note))
    npass = sum(1 for r in RESULTS if r[2])
    nfail = len(RESULTS) - npass
    print("\n路由/边界/仲裁 首跑：通过 %d／%d，失败 %d" % (npass, len(RESULTS), nfail))
    if nfail:
        print("失败明细：")
        for cid, name, ok, note in RESULTS:
            if not ok:
                print("  - %s %s → %s" % (cid, name, note))
    print("门禁：%s" % ("PASS" if nfail == 0 else "FAIL"))
    return 0 if (nfail == 0 or not strict) else 1


if __name__ == "__main__":
    sys.exit(main())
