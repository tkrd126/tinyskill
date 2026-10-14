#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""guiauto 离线自测：不需要任何 GUI 程序，验证 OCR 链 / 像素判据 / 几何解析。

    python3 scripts/selftest.py            # 全离线
    python3 scripts/selftest.py --live     # 额外测真实 X11（列窗口/截图/OCR 标题栏）

退出码 0 = 全绿。合成图里的「下载完毕」+ 红块 + 复选框模拟真实控件。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guiauto as g  # noqa: E402

FAIL = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAIL.append(name)


def synth():
    """造一张像真实控件的图：中文状态行 + 实心红按钮 + 红细边框 + 勾选/未勾选复选框"""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (600, 300), (240, 240, 240))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 20)
    if not os.path.exists("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
        font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc", 20)
    d.text((20, 250), "下载完毕.", fill=(0, 0, 0), font=font)            # 状态行
    d.rectangle([30, 30, 180, 70], outline=(200, 30, 30), width=2)      # 红细边框(干扰项)
    d.rectangle([400, 230, 560, 266], fill=(200, 30, 30))               # 实心红按钮(想要这个)
    # 复选框：左下勾上(画个粗勾)，右上空的；边框故意用浅灰(>128)以免自己计入暗像素
    d.rectangle([30, 120, 48, 138], outline=(170, 170, 170), width=1)
    d.line([(33, 129), (38, 134), (45, 124)], fill=(20, 20, 20), width=3)
    d.rectangle([200, 120, 218, 138], outline=(170, 170, 170), width=1)
    return img


print("== 1. 环境 ==")
check("TESSDATA_PREFIX 已设", bool(os.environ.get("TESSDATA_PREFIX")), os.environ.get("TESSDATA_PREFIX", ""))
import shutil  # noqa: E402
for b in ("xdotool", "scrot", "xprop", "tesseract"):
    check(f"{b} 存在", bool(shutil.which(b)), shutil.which(b) or "")

print("== 2. OCR 链（合成中文图）==")
img = synth()
txt = g.ocr(img, psm=6, scale=2)
check("认出「下载完毕」", "下载完毕" in g.squash(txt), f"raw={txt!r}")
words = g.ocr_words(img, psm=6, scale=2)
check("ocr_words 有结果", len(words) > 0, f"{len(words)} 词")
check("词框带坐标", bool(words and words[0]["left"] >= 0 and words[0]["width"] > 0))
hit = g.find_word(img, "下载", psm=6, scale=2, min_conf=0)
check("find_word 定位到状态行", bool(hit and hit[0] > 10 and hit[1] > 200),
      f"{(hit[0], hit[1]) if hit else None}")

print("== 3. 像素判据 ==")
box_on = (28, 118, 22, 22)      # 勾上的复选框(留一点余量)
box_off = (198, 118, 22, 22)    # 未勾选
on, off = g.dark_ratio(img, box_on), g.dark_ratio(img, box_off)
check("勾选态暗像素占比 > 未勾选态", on > off, f"勾上 {on:.3f} vs 未勾 {off:.3f}")
check("阈值 0.02 能区分", on > 0.02 >= off, f"on>{on:.3f} off={off:.3f}")
red = g.red_block(img, y_from=0.5)
check("red_block 找到实心红块", bool(red), f"{red}")
if red:
    cx, cy, w, h, area = red
    check("定位到按钮而非细边框", 380 < cx < 580 and w > 100 and h > 20, f"中心({cx},{cy}) {w}x{h} 面积{area}")
    check("返回原图比例坐标(非放大后)", cy < 300 and cx < 600, f"{cx},{cy}")

print("== 4. 纯逻辑 ==")
check("squash 去空白", g.squash("下载 完毕 .") == "下载完毕.", repr(g.squash("下载 完毕 .")))
check("wait_for 会超时返回 False", g.wait_for(lambda: False, timeout=1, interval=0.3) is False)
check("wait_for 立即真返回 True", g.wait_for(lambda: True, timeout=5) is True)
check("workarea 解析", len(g.workarea()) == 4, str(g.workarea()))

if "--live" in sys.argv:
    print("== 5. 真实 X11 ==")
    try:
        g.require_x11()
        check("xdotool 可用", True)
    except RuntimeError as e:
        check("xdotool 可用", False, str(e)[:80])
    ws = g.windows()
    check("列出可见窗口", len(ws) > 0, f"{len(ws)} 个")
    if ws:
        # 跳过 1x1 的分割条/边框辅助窗，挑一个真有大小的
        w = next((x for x in ws if x.geom()[2] > 300 and x.geom()[3] > 200), ws[0])
        print(f"       示例: {w!r}")
        check("能取几何", w.geom()[2] > 0 and w.geom()[3] > 0, str(w.geom()))
        check("能截本窗口", w.shot().width > 0)
        tb = g.squash(w.titlebar())
        print(f"       标题栏 OCR: {tb[:60]!r}")
        check("标题栏 OCR 非空", len(tb) > 0)
        print(f"       active={w.active()} workarea={g.workarea()}")

print()
if FAIL:
    print(f"❌ {len(FAIL)} 项失败: {FAIL}")
    sys.exit(1)
print("✅ 全部通过")
