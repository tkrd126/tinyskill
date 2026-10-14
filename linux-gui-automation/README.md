# linux-gui-automation

在 Linux（X11）上把**没有 API 的 GUI 软件**变成可自动化、可无人值守的流程。

真鼠标/真键盘（`xdotool` 往 X11 注入事件）+ 像素判据（Pillow/numpy）+ 认字（tesseract OCR），
每一步都用程序可验证的信号卡住——**不靠猜、不靠 sleep**。

源起：无人值守让 Wine/玲珑版**通达信**每天收盘后自己完成「盘后数据下载」（562 行工程化脚本）。
本目录把它抽象成可复用的通用骨架。

## 适合 / 不适合

| 场景 | 结论 |
|---|---|
| Wine/玲珑打包的国产客户端（行情/交易终端）、老式 Java/Qt 内部系统、无 CLI 开关的安装向导 | ✅ 用本技能 |
| 有官方 API / 命令行开关的软件 | ❌ 先用 API，GUI 自动化是最后手段 |
| Web 应用 | ❌ 用 CDP/Playwright |
| **Wayland 会话** | ❌ `xdotool` 进不去（先 `echo $XDG_SESSION_TYPE`） |

## 安装依赖

```bash
sudo apt install xdotool scrot xprop tesseract-ocr tesseract-ocr-chi-sim python3-pil python3-numpy
pip install pytesseract
```

> `chi_sim` 在 Debian 系常装在 `/usr/share/tesseract-ocr/4.00/tessdata`，而引擎 5.x 去别处找 →
> 模块导入时已自动 `os.environ.setdefault("TESSDATA_PREFIX", "/usr/share/tesseract-ocr/4.00/tessdata")`。

## 快速上手

```bash
# 0. 自测（不需要任何 GUI 程序；加 --live 则额外测真实 X11）
python3 scripts/selftest.py --live

# 1. 侦察：列出所有可见窗口 + 几何 + 标题，并对匹配窗口 OCR 所有词框（带坐标）
GUIAUTO_TARGET='^我的软件' python3 scripts/guiauto.py
```

```python
import guiauto as g

g.require_x11()                                   # Wayland 里早报错
w = g.find_window(r"^我的软件")                     # 标题务必用 ^ 严格前缀
if w.activate():                                  # 聚焦校验通过才敢点
    w.maximize()                                  # 固定尺寸对话框会返回 False，用当前几何继续
    w.click(162, 53)                              # 窗口内相对坐标
    w.click_frac(0.85, 0.95)                      # 比例坐标（窗口尺寸变了也不怕）
    if g.dark_ratio(w.shot(), (29, 91, 9, 9)) > 0.02:
        print("复选框已勾上")
    for txt in g.watch_text(w, box=(0, 470, 655, 60), timeout=600, interval=5):
        if "下载完毕" in g.squash(txt):
            print("完成"); break
```

## API 速览

| 分组 | 接口 | 说明 |
|---|---|---|
| 环境 | `require_x11()` | 自检 DISPLAY/会话类型（Wayland 直接报错） |
| 命令 | `sh(*cmd, timeout=15)` | 跑外部命令，**永远带超时**（`--sync` 会干等 1 分钟） |
| | `run_detached(*cmd)` / `pid_of(name)` | 拉起 GUI 程序 / `pgrep -x` 探进程 |
| 屏幕 | `workarea()` / `screen()` / `dump(img)` | `_NET_WORKAREA`（避开任务栏）/ 全屏截图 / 存图复核 |
| 窗口 | `windows()` / `find_window(re)` / `Win` | 列窗口 / 找窗口 / 几何·聚焦·最大化·点击·键盘·截图 |
| OCR | `ocr(img)` / `ocr_words(img)` / `ocr_map(img)` | 认字 / 词框+坐标 / 侦察打印 |
| | `find_word(img, needle)` | 按行内相邻词拼接定位（**中文会被切成单字 token**） |
| 像素 | `dark_ratio(img, box)` | 暗像素占比 → 判复选框勾没勾上 |
| | `red_block(img, y_from=0.5)` | 找面积最大的实心红色块 → 彩色主按钮 |
| | `color_ratio(img, box, pred)` | 自定义颜色判据 |
| 等待 | `wait_for(fn, timeout)` / `watch_text(win, box)` | 轮询判据 / 生成器持续 OCR 看完成 |
| 侦察 | `recon(title_re=None)` | 一步列出工作区 + 窗口 + 目标 OCR + 所有词框坐标 |

约定：**所有 `box` / 点击坐标都是 `(x, y, w, h)` 或窗口内相对坐标**，绝对坐标一律运行时算。

## 自测输出（本机实测）

```
== 2. OCR 链（合成中文图）==
  [PASS] 认出「下载完毕」
  [PASS] ocr_words 有结果 5 词
  [PASS] find_word 定位到状态行 (86, 266)
== 3. 像素判据 ==
  [PASS] 勾选态暗像素占比 > 未勾选态 勾上 0.143 vs 未勾 0.000
  [PASS] red_block 找到实心红块 (480, 248, 161, 37, 5957)
  [PASS] 定位到按钮而非细边框 中心(480,248) 161x37 面积5957
== 5. 真实 X11 ==
  [PASS] 列出可见窗口 14 个
  [PASS] 标题栏 OCR 非空
✅ 全部通过
```

## 十条最重要的坑（完整版见 SKILL.md）

1. 合成点击打的是屏幕坐标 —— 点前必须 `getactivewindow` 校验，否则点到别的软件；
2. 坐标不硬编码：每次操作前最大化 + 活几何 + 相对偏移；
3. 弹出菜单打开后不可再 `activate`（Wine 会立刻关掉菜单）；
4. 别用 `_NET_WM_PID` 认窗口（Wine 实测全是 20）；标题模糊匹配会点到浏览器上；
5. OCR 判据挑"认错也唯一"的字，小字固定 `scale=3 + --psm 6`；中文是单字 token；
6. 给每条外部命令设超时（不可激活的广告窗能让 `--sync` 干等 1 分钟）；
7. 进度条 100% ≠ 完成（分阶段任务计数器会重置）→ 用状态文本 / 控件翻转 / 无新写入三层判据；
8. 截图前先聚焦，否则拍到别的窗口；
9. 中间态（登录/弹窗失败）要能自己重试：延时 → 回车 → 点按钮 → 循环到目标界面出现；
10. 时间门：很多软件特定时段拒服务（实测盘中点下载直接失败）→ 显式过滤 + `--check-only` 干跑 + 日历 fail-open。

## 文件

```
linux-gui-automation/
├── SKILL.md            # agent 读：硬规则/流程/调试手法/反模式
├── README.md           # 本文件：人读：安装/快速上手/API
└── scripts/
    ├── guiauto.py      # 可复用骨架（PIL/numpy/pytesseract 懒加载）
    └── selftest.py     # 离线自测：合成中文图 + 红块 + 复选框，验证 OCR 链与像素判据
```

## 真实案例（完整工程化版本）

同一套手法在通达信盘后数据下载上的落地脚本（562 行）：登录失败重试链、主窗口 OCR 复核、
完成三层判据、交易时段+非交易日双层过滤、cron 无人值守。
实测基线：冷启动到进主界面 38 秒；一轮下载 10 分 32 秒、18750 个文件落盘。
（该脚本及对应技能目前在 `hermes-skills` 仓，未收录于本仓。）

## License

MIT
