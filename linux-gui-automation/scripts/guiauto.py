"""guiauto — Linux/X11 GUI 自动化的最小可复用骨架

    xdotool(合成鼠标/键盘) + scrot(截图) + Pillow/numpy(像素判据) + tesseract(认字)

提炼自真机跑通的 /home/admin/tdx_auto_download.py（无人值守让通达信下盘后数据）。

三条设计原则（都是踩出来的）：
  1. 坐标永不硬编码：每次操作前重新量活窗口几何，全部用「几何 + 相对偏移」算。
  2. 点击前必须确认聚焦：getactivewindow == 目标窗口，否则点的是别的软件。
  3. 每个动作都要有可验证判据：几何 / 像素 / OCR 至少用一个，不要「点了就当成功」。

快速上手：
    import guiauto as g
    print(g.recon())                                  # 侦察：列窗口 + OCR 词框带坐标
    w = g.find_window(r"^我的软件")
    if w.activate():                                  # 聚焦校验通过才动手
        w.click(30, 91); g.wait_for(lambda: w.titlebar().find("已设置") >= 0, 30)

依赖：xdotool scrot xprop tesseract-ocr(-chi-sim) + pytesseract pillow numpy
"""

import os
import re
import subprocess
import time

__all__ = [
    "DISPLAY", "LANG", "sh", "run_detached", "pid_of", "log", "require_x11",
    "workarea", "screen", "dump", "Win", "windows", "find_window", "find_windows",
    "ocr", "ocr_words", "ocr_map", "squash", "find_word", "dark_ratio", "color_ratio", "red_block",
    "wait_for", "watch_text", "recon",
]

DISPLAY = os.environ.get("DISPLAY", ":0")
LANG = os.environ.get("GUIAUTO_LANG", "chi_sim+eng")
# Debian 系常见坑：引擎 5.x 找不到 4.00 目录里的 chi_sim.traineddata，必须把 TESSDATA_PREFIX 给 pytesseract
_TESSDATA = "/usr/share/tesseract-ocr/4.00/tessdata"
if os.path.isdir(_TESSDATA):
    os.environ.setdefault("TESSDATA_PREFIX", _TESSDATA)


# ---------------------------------------------------------------- 日志 / 环境

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def require_x11():
    """Wayland 会话里 xdotool 什么都做不了，早报错比默默失败好"""
    t = os.environ.get("XDG_SESSION_TYPE", "")
    if sh("xdotool", "getactivewindow", timeout=5) == "":
        raise RuntimeError(
            f"xdotool 无法工作（DISPLAY={DISPLAY!r}, XDG_SESSION_TYPE={t!r}）。"
            "Wayland 会话不支持 xdotool，请切到 X11 或用 ydotool。")
    return True


# ---------------------------------------------------------------- 命令层

def sh(*cmd, timeout=15, binary=False, check=False):
    """跑外部命令，**永远带超时**（xdotool --sync 在不可激活的窗口上会干等 1 分多钟）。
    返回 stdout（str 已 strip；binary=True 时返回 bytes）。"""
    env = dict(os.environ, DISPLAY=DISPLAY)
    try:
        r = subprocess.run([str(c) for c in cmd], capture_output=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        log(f"!! 超时 {timeout}s: {' '.join(str(c) for c in cmd)[:90]}")
        if check:
            raise
        return b"" if binary else ""
    if check and r.returncode != 0:
        raise RuntimeError(f"命令失败({r.returncode}): {' '.join(str(c) for c in cmd)[:90]} "
                           f"{r.stderr.decode('utf-8', 'replace')[:160]}")
    return r.stdout if binary else r.stdout.decode("utf-8", "replace").strip()


def run_detached(*cmd, **env_extra):
    """在图形会话里拉起一个 GUI 程序（不阻塞）；玲珑/沙箱应用常需额外环境变量"""
    env = dict(os.environ, DISPLAY=DISPLAY, **env_extra)
    log(f"拉起: {' '.join(str(c) for c in cmd)}")
    return subprocess.Popen([str(c) for c in cmd], env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)


def pid_of(exe_name):
    """进程探测：用 pgrep -x（精确进程名）。pgrep -f 会误匹配 .sh 包装脚本（实测踩过）"""
    return sh("pgrep", "-x", exe_name).split()


# ---------------------------------------------------------------- 屏幕 / 工作区

def workarea():
    """_NET_WORKAREA -> (x, y, w, h)：排掉任务栏/dock 后的真实可用区（最大化要用它）"""
    out = sh("xprop", "-root", "_NET_WORKAREA")
    m = re.search(r"=\s*([\d,\s]+)", out)
    return tuple(int(v) for v in m.group(1).split(",")[:4]) if m else (0, 0, 1920, 1080)


def screen(path=None):
    """全屏截图 -> PIL.Image（scrot 比 ImageMagick import 更常见、更快）"""
    from PIL import Image
    path = path or f"/tmp/guiauto_shot_{os.getpid()}.png"
    sh("scrot", "-o", path, timeout=25)
    img = Image.open(path)
    img.load()
    return img.copy()


def dump(img, path="/tmp/guiauto_dump.png"):
    """把图存盘（人眼/助手复核用），返回路径"""
    img.save(path)
    log(f"图已存: {path} {img.width}x{img.height}")
    return path


# ---------------------------------------------------------------- 窗口

class Win:
    """一个 X11 窗口。所有 click/box 坐标都是**窗口内相对坐标**，绝对坐标运行时算。"""

    def __init__(self, wid):
        self.wid = int(wid)

    def __repr__(self):
        try:
            return f"<Win {self.wid} {self.name()[:40]!r} {self.geom()}>"
        except Exception:
            return f"<Win {self.wid} (已消失)>"

    def __eq__(self, o):
        return isinstance(o, Win) and o.wid == self.wid

    def __hash__(self):
        return hash(self.wid)

    def alive(self):
        return sh("xdotool", "getwindowname", self.wid) != ""

    def name(self):
        return sh("xdotool", "getwindowname", self.wid)

    def geom(self):
        """(x, y, w, h) —— 每次现量，不缓存"""
        out = sh("xdotool", "getwindowgeometry", "--shell", self.wid)
        d = dict(l.split("=", 1) for l in out.splitlines() if "=" in l)
        return (int(d.get("X", 0)), int(d.get("Y", 0)),
                int(d.get("WIDTH", 1)), int(d.get("HEIGHT", 1)))

    def active(self):
        return sh("xdotool", "getactivewindow") == str(self.wid)

    def activate(self, tries=3, wait=0.5):
        """提到最前并**确认真的活动**。返回 False 时绝不能点击（点到的会是别的软件）。"""
        for i in range(tries):
            sh("xdotool", "windowactivate", "--sync", self.wid, timeout=10)
            sh("xdotool", "windowraise", self.wid, timeout=10)
            time.sleep(wait)
            if self.active():
                return True
            log(f"聚焦校验失败(第 {i + 1} 次): 活动窗口不是 {self.wid}")
        return False

    def maximize(self, tries=3):
        """拉到工作区。固定尺寸对话框会拒绝缩放 -> 返回 False，调用方用当前几何继续。"""
        wx, wy, ww, wh = workarea()
        for i in range(tries):
            sh("xdotool", "windowmove", self.wid, wx, wy, timeout=10)
            sh("xdotool", "windowsize", self.wid, ww, wh, timeout=10)
            time.sleep(0.6)
            g = self.geom()
            if abs(g[2] - ww) <= 12 and abs(g[3] - wh) <= 12:
                return True
            if i >= 1:
                log(f"窗口不接受缩放(固定尺寸), 用当前几何 {g} 继续")
                return False
        return False

    def click(self, rx, ry, dt=0.35, button=1):
        """在窗口内 (rx, ry) 点一下；返回实际屏幕坐标（便于日志核对）"""
        x, y, _, _ = self.geom()
        ax, ay = int(x + rx), int(y + ry)
        sh("xdotool", "mousemove", "--sync", ax, ay, timeout=8)
        sh("xdotool", "click", button, timeout=8)
        time.sleep(dt)
        return ax, ay

    def click_frac(self, fx, fy, dt=0.35):
        """比例坐标(0~1)，窗口尺寸变了也不怕"""
        _, _, w, h = self.geom()
        return self.click(w * fx, h * fy, dt)

    def key(self, *keys, dt=0.25):
        for k in keys:
            sh("xdotool", "key", k, timeout=8)
            time.sleep(dt)

    def type(self, text, delay_ms=30):
        sh("xdotool", "type", "--delay", str(delay_ms), text, timeout=25)

    def focus_or_key(self, key="Return"):
        """把键盘送到本窗口：Wine/部分 Qt 需要先 activate"""
        if self.activate():
            self.key(key)
            return True
        return False

    def shot(self, box=None, path=None):
        """截本窗口（或其中 box=(x,y,w,h) 块）-> PIL.Image。截图前先聚焦，否则拍到的是别的窗口。"""
        img = screen(path)
        x, y, w, h = self.geom()
        if box:
            bx, by, bw, bh = box
            x, y, w, h = x + bx, y + by, bw, bh
        return img.crop((int(x), int(y), int(x + w), int(y + h)))

    def titlebar(self, h=34, scale=3, psm=6, lang=None):
        """标题栏文字。小字必须 scale=3 + psm=6（scale=2 会把「选项」读成「选页」）。"""
        return ocr(self.shot(box=(0, 0, self.geom()[2], h)), scale=scale, psm=psm, lang=lang)

    def is_it(self, box=(0, 0, 400, 34), must=(), must_not=(), **ocr_kw):
        """内容复核：标题栏/某块里必须出现哪些字、不能出现哪些字（防点到别的软件）"""
        t = squash(ocr(self.shot(box=box), **ocr_kw))
        return all(w in t for w in must) and not any(w in t for w in must_not), t


def windows(visible_only=True):
    """所有可见窗口 -> [Win]。标题为正则 "." 即任意非空标题。"""
    args = ["xdotool", "search"] + (["--onlyvisible"] if visible_only else []) + ["--name", "."]
    return [Win(w) for w in sh(*args, timeout=10).split()]


def find_windows(title_re, visible_only=True):
    args = ["xdotool", "search"] + (["--onlyvisible"] if visible_only else []) + ["--name", title_re]
    return [Win(w) for w in sh(*args, timeout=10).split()]


def find_window(title_re, **kw):
    """第一个匹配窗口，找不到返回 None。标题正则务必用 ^ 严格前缀（模糊匹配会点到浏览器上）。"""
    ws = find_windows(title_re, **kw)
    return ws[0] if ws else None


# ---------------------------------------------------------------- OCR

def squash(s):
    """去掉所有空白再匹配：OCR 常在字之间塞空格"""
    return re.sub(r"\s+", "", s or "")


def _prep(img, scale):
    from PIL import Image
    if img.mode != "RGB":
        img = img.convert("RGB")
    if scale and scale != 1:
        img = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
    return img


def ocr(img, lang=None, psm=6, scale=3):
    """图像 -> 文字。小字放大 scale 倍；psm 6=整块（6 通常最好，7/11 实测更差）。"""
    import pytesseract
    return pytesseract.image_to_string(_prep(img, scale), lang=lang or LANG,
                                      config=f"--psm {psm}").strip()


def ocr_words(img, lang=None, psm=6, scale=3, min_conf=40):
    """-> [{'text','left','top','width','height','conf'}]，坐标已还原回原图尺度"""
    import pytesseract
    from pytesseract import Output
    d = pytesseract.image_to_data(_prep(img, scale), lang=lang or LANG,
                                 config=f"--psm {psm}", output_type=Output.DICT)
    out = []
    for i, t in enumerate(d["text"]):
        t = t.strip()
        try:
            conf = float(d["conf"][i])
        except (TypeError, ValueError):
            continue
        if t and conf >= min_conf:
            out.append({"text": t, "left": d["left"][i] // scale, "top": d["top"][i] // scale,
                        "width": d["width"][i] // scale, "height": d["height"][i] // scale,
                        "conf": conf})
    return out


def ocr_map(img, **kw):
    """侦察用：OCR 所有词框并打印「文字 @ 中心坐标」——一次性量出控件偏移"""
    words = ocr_words(img, **kw)
    for w in words:
        log(f"  {w['text'][:24]:<26} @ ({w['left'] + w['width'] // 2}, {w['top'] + w['height'] // 2}) "
            f"size {w['width']}x{w['height']} conf {w['conf']:.0f}")
    return words


def _lines(words, tol=8):
    """把词框按 top 归成行（同一行的词才能拼起来看）"""
    lines = []
    for w in sorted(words, key=lambda x: (x["top"], x["left"])):
        for ln in lines:
            if (abs(ln[0]["top"] - w["top"]) <= tol
                    or abs(ln[0]["top"] + ln[0]["height"] - w["top"] - w["height"]) <= tol):
                ln.append(w)
                break
        else:
            lines.append([w])
    return [sorted(ln, key=lambda x: x["left"]) for ln in lines]


def find_word(img, needle, min_conf=0, prefer=None, **kw):
    """在 OCR 结果里找 needle -> (cx, cy, box)，找不到 None。

    **坑（实测）**：tesseract 把中文切成**单字 token**（`下` `载` `完毕` 三个词框），
    所以不能写 `needle in token`，而要把**同一行相邻词拼起来**再找；命中就返回那一段词框的并集中心。
    prefer 收到 (cx, cy) 用于挑候选（如 `prefer=lambda c: -c[0]` 取最靠右的）。
    """
    needle = squash(needle)
    cands = []
    for ln in _lines(ocr_words(img, min_conf=min_conf, **kw)):
        for i in range(len(ln)):
            acc = ""
            for j in range(i, len(ln)):
                acc += squash(ln[j]["text"])
                if needle in acc:
                    grp = ln[i:j + 1]
                    x0 = min(w["left"] for w in grp)
                    y0 = min(w["top"] for w in grp)
                    x1 = max(w["left"] + w["width"] for w in grp)
                    y1 = max(w["top"] + w["height"] for w in grp)
                    cands.append((x0 + (x1 - x0) // 2, y0 + (y1 - y0) // 2,
                                  {"left": x0, "top": y0, "width": x1 - x0, "height": y1 - y0,
                                   "text": acc}))
                    break
    if not cands:
        return None
    if prefer:
        cands.sort(key=lambda c: prefer((c[0], c[1])))
    return cands[0]


# ---------------------------------------------------------------- 像素判据
# 约定：box 一律 (x, y, w, h)（与 click 的相对坐标同一套），内部转 PIL 的 (l, u, r, b)

def _crop(img, box):
    """box 全程统一为 (x, y, w, h) —— 与 click 的相对坐标一致，不是 PIL 的 (l, u, r, b)"""
    x, y, w, h = box
    return img.crop((int(x), int(y), int(x + w), int(y + h)))


def dark_ratio(img, box, thresh=128):
    """区块内暗像素占比 box=(x,y,w,h) —— 判「复选框勾上了没有」：先量勾选态/未勾选态再定阈值
    （实测：勾上 0.065，未勾选 ~0.01，阈值取 0.02）"""
    import numpy as np
    a = np.asarray(_crop(img, box).convert("L"), dtype=np.uint8)
    return float((a < thresh).mean()) if a.size else 0.0


def color_ratio(img, box, pred):
    """自定义颜色判据 box=(x,y,w,h)：pred 收到 (H,W,3) uint8 返回 bool 矩阵，返回占比"""
    import numpy as np
    a = np.asarray(_crop(img, box).convert("RGB"))
    return float(pred(a).mean()) if a.size else 0.0


def _row_runs(row):
    runs, s = [], None
    for j, v in enumerate(row):
        if v and s is None:
            s = j
        elif not v and s is not None:
            runs.append((s, j))
            s = None
    if s is not None:
        runs.append((s, len(row)))
    return runs


def red_block(img, y_from=0.5, min_w=20, min_h=8, r_min=150, g_max=90, b_max=90):
    """找「面积最大的实心红色块」（彩色主按钮）-> (cx, cy, w, h, area) 原图坐标，找不到 None。

    为什么不用「红像素包围盒中心」：输入框聚焦时也有红细边，包围盒会把它和按钮框在一起，
    中心偏 15~40px（实测连点两次没反应）。细边在行/列方向宽度很小，会被 min_w/min_h 过滤掉。
    """
    import numpy as np
    a = np.asarray(img.convert("RGB"))
    m = (a[:, :, 0] > r_min) & (a[:, :, 1] < g_max) & (a[:, :, 2] < b_max)
    if y_from > 0:
        m[: int(m.shape[0] * y_from)] = False
    active, done = [], []
    for i in range(m.shape[0]):
        for x0, x1 in _row_runs(m[i]):
            if x1 - x0 < min_w:
                continue
            hit = next((b for b in active if min(b[1], x1) - max(b[0], x0) > 0.5 * (x1 - x0)), None)
            if hit:
                hit[0], hit[1], hit[3] = min(hit[0], x0), max(hit[1], x1), i
            else:
                active.append([x0, x1, i, i])
        active, rest = [b for b in active if b[3] == i], [b for b in active if b[3] != i]
        done += rest
    done += active
    boxes = [b for b in done if b[1] - b[0] >= min_w and b[3] - b[2] + 1 >= min_h]
    if not boxes:
        return None
    x0, x1, y0, y1 = max(boxes, key=lambda b: (b[1] - b[0]) * (b[3] - b[2] + 1))
    w, h = x1 - x0, y1 - y0 + 1
    return x0 + w // 2, y0 + h // 2, w, h, w * h


# ---------------------------------------------------------------- 等待/监视

def wait_for(fn, timeout=60, interval=2, desc=""):
    """轮询到 fn() 为真 -> True；超时 -> False。**不要用 sleep 硬等界面就绪**。"""
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return True
        time.sleep(interval)
    log(f"等待超时({timeout}s) {desc}")
    return False


def watch_text(win, box=None, timeout=600, interval=5, scale=3, psm=6, lang=None):
    """生成器：每 interval 秒 OCR 一次 win 的 box（默认整个窗口），把文本 yield 给调用方判完成。

        for txt in g.watch_text(w, box=(0, h - 60, ww, 60)):
            if "下载完毕" in g.squash(txt): break
    """
    end = time.time() + timeout
    while time.time() < end:
        yield ocr(win.shot(box=box), scale=scale, psm=psm, lang=lang)
        time.sleep(interval)


# ---------------------------------------------------------------- 侦察

def recon(title_re=None, dump_png="/tmp/guiauto_recon.png"):
    """新目标软件第一步：打印工作区 + 所有可见窗口（几何/标题/是否活动），
    并对匹配窗口 OCR 标题栏与词框（带坐标）。"""
    info = {"workarea": workarea(), "windows": []}
    log(f"工作区 _NET_WORKAREA = {info['workarea']}")
    for w in windows():
        entry = {"wid": w.wid, "geom": w.geom(), "title": w.name(), "active": w.active()}
        info["windows"].append(entry)
        log(f"  {w.wid:<10} {entry['geom']} {'*' if entry['active'] else ' '} {entry['title'][:70]}")
    if title_re:
        w = find_window(title_re)
        if not w:
            log(f"没找到匹配 {title_re!r} 的窗口")
        else:
            log(f"目标窗口 {w.wid} 几何 {w.geom()} | 标题栏 OCR: {squash(w.titlebar())}")
            dump(w.shot(), dump_png)
            ocr_map(w.shot())
            info["target"] = {"wid": w.wid, "geom": w.geom(), "titlebar": squash(w.titlebar())}
    return info


if __name__ == "__main__":
    recon(os.environ.get("GUIAUTO_TARGET"))
