---
name: linux-gui-automation
description: "Use when automating Linux X11 GUI apps (xdotool+OCR)."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [GUI-Automation, xdotool, OCR, X11, Wine, Desktop, RustDesk-free]
    related_skills: [tdx-wine-auto-download, cdp-browser-integration, system-restore-recovery]
---

# Linux X11 GUI 自动化（xdotool + 像素判据 + OCR）

## When to Use

**什么时候用**：目标软件没有 API/CLI，只能像人一样点它。典型场景是 Wine/玲珑打包的国产客户端
（通达信、QMT、各种行情/交易终端）、老式 Java/Qt 内部系统、没有命令行开关的安装向导。

**什么时候不要用**：

- 有官方 API / 命令行开关 → 先用那个，GUI 自动化永远是最后手段；
- Web 应用 → 用 CDP/Playwright（见 `cdp-browser-integration`）；
- **Wayland 会话 → `xdotool` 进不去**（只能用 `ydotool`/uinput 或切回 X11）。动手前先 `echo $XDG_SESSION_TYPE`。

本文所有规则都来自真机跑通的样本：`/home/admin/tdx_auto_download.py`（562 行，无人值守让通达信自己下盘后数据）。
可复用骨架：`scripts/guiauto.py`；离线自测：`scripts/selftest.py`。

## 五步循环（每一步都要有判据）

```
侦察  →  定位  →  聚焦  →  操作  →  校验
 |        |        |        |        |
 列窗口   量几何   确认焦点  合成事件  几何/像素/OCR
 xprop    相对偏移 getactivewindow  xdotool  失败则重试或回退
```

**核心心法：不要"点了就当成功"。** 每个动作后面必须挂一个程序可验证的信号——窗口几何变了、
像素占比超阈值、OCR 认出了预期的字。三者至少用一个。

## 起步：给一个新软件写自动化（照着做）

```bash
# 1. 会话/工具自检（Wayland 直接放弃）
echo $XDG_SESSION_TYPE; xdotool getactivewindow   # 报错=DISPLAY 不对

# 2. 侦察：列出所有可见窗口，看谁是谁
python3 -c "import sys; sys.path.insert(0,'<skill>/scripts'); import guiauto as g; g.recon()"

# 3. 截图 + OCR 出所有词框（文字 + 坐标），把控件偏移一次性量出来
python3 -c "import guiauto as g; w=g.find_window('^我的软件'); print(g.ocr_map(w.shot()))"

# 4. 把偏移写成常量表（相对窗口左上角），不要写屏幕绝对坐标
```

把量出来的东西记成表（示例来自通达信）：

| 控件 | 相对偏移 | 判据 |
|---|---|---|
| 顶部「选项」/「设置」 | `(右边缘-419, 顶+12)` + OCR 定位优先 | OCR 读到含「选」且 x > 宽/2 |
| 下拉菜单第 N 项 | `(右边缘-370, 顶+231)`，带 y 漂移回退阶梯 | 目标对话框出现 |
| 复选框 | `(29, 91)` | 9×9 区域暗像素占比 > 0.02（实测 0.065） |
| 主按钮 | 像素定位红色实心块 | 块面积/尺寸合理（实测 258×26 / 6775） |

## 硬规则（每条都是踩出来的，别跳）

1. **合成点击打的是屏幕绝对坐标，谁在最上层就点谁。** 每次点击/截图前
   `windowactivate --sync` + `windowraise`，再校验 `getactivewindow == 目标窗口`；校验失败**绝不点击**，
   退回重试。浏览器、控制中心、终端都能悄悄盖住目标。
2. **窗口尺寸可变 → 坐标绝不能硬编码。** 每次操作前先最大化到 `_NET_WORKAREA`（自动避开任务栏/dock），
   再用"活几何 + 相对偏移"算坐标。**固定尺寸的对话框会拒绝 `windowsize`**：尺寸没变就承认它固定、
   用当前几何继续（对话框内部控件偏移是相对它自己的）。
3. **弹窗菜单（Wine/老式 Qt）打开后不能再 `activate`/`raise` 任何窗口** —— 会立刻把菜单关掉。
   开菜单前先 `key Escape` 清场，**只点一次**触发菜单（点两次 = 开→关），从开菜单到点中菜单项之间不做任何聚焦操作。
4. **别用 `_NET_WM_PID` 认窗口**：Wine 窗口的 pid 实测都是 20（不是真 pid）；容器/沙箱同理。
   按**标题**匹配，再按内容复核。
5. **标题模糊匹配会点到别的软件上。** 实测：Yandex/Chrome 的页面标题里带「通达信金融终端」，
   于是 `xdotool search --name 通达信` 把点击送到了浏览器。两道闸：① 严格前缀 `^软件名.*版本`；
   ② **OCR 复核窗口内容**（标题栏里必须出现该软件独有的字）。
6. **OCR 别要求整串精确匹配。** tesseract 会把「金融」认成「和/爹」、`scale=2` 时把「选项」读成「选页」。
   挑"即使认错也唯一且稳定"的字做判据（如只认「通达信」+「选」），并固定参数：小字 **`scale=3` + `--psm 6`**。
   还有个更隐蔽的：**中文会被切成单字 token**（`下` `载` `完毕` 三个词框），所以
   `"下载" in word["text"]` 永远不成立 —— 要按"同一行相邻词拼接"再匹配（`find_word()` 已内置该逻辑）。
7. **给每个外部命令设超时（`subprocess.run(timeout=15)`）。** `xdotool windowactivate --sync`
   在**无法被激活的窗口**（很多启动广告弹窗）上会干等 1 分多钟。广告弹窗只做"尽力点 ×"、不聚焦。
8. **窗口内容随时可能被弹窗遮挡** → 像素判据会被污染。判据优先用"**结果**"（目标对话框是否出现、
   状态文字是否变化），而不是"我猜菜单开着"。
9. **登录/弹窗类中间态要能自己重试。** 实测通达信自动登录偶发失败（显示「查找主站失败，请检查通讯设置」），
   处理模板：**延时 3 秒 → 回车 → 点主按钮 → 循环重试到目标界面出现**（实测第 5 次命中，38 秒）。
   识别"中间态窗口"要有**两个**判据（标题 + 尺寸/内容），因为主窗口刚出现那一瞬间标题还没更新完。
10. **按钮位置用像素找，别估算。** 找"窗口下半部面积最大的实心红色连通块"（用户名输入框聚焦时的红细边
    面积小得多，按"红像素包围盒中心"点会偏 15~40px、毫无反应）。
11. **进度条 100% 不等于完成。** 分阶段任务（多段下载/校验）的计数器会**重置**。
    完成判定优先级：① 状态行 OCR 出现「完成/完毕」→ ② 按钮文字翻转（「取消」→「开始」）
    → ③ 兜底：连续 N 秒没有新文件写入 / 目标文件 mtime 不再变。
12. **截图前也要先聚焦**，否则存下来的是别的窗口（踩过："完成态截图"里是浏览器）。
13. **`--start-only` 与监视分离**：定时任务只负责"把动作启动起来"就退出，别让 cron 守 10 分钟。
14. **幂等**：脚本要能重复跑（先清场 `Escape`、先探测状态再决定点不点），用户随时可能中途撤销/重来。
15. **时间门（可下载/可执行窗口期）**：很多软件在特定时段会拒绝操作（实测通达信盘中点下载直接失败）。
    把"现在能不能干"做成显式函数 + 干跑开关（`--check-only`），并配 `--force`/`--wait`。
    涉及交易日/工作日时查真日历，别只按星期算；**查不到日历要 fail-open**（宁可多跑一次也不能漏一天）。

## cron 挂载（无人值守）

```cron
40 15 * * 1-5 DISPLAY=:0 XAUTHORITY=/home/admin/.Xauthority /usr/bin/python3 /path/to/script.py --start-only >> /home/admin/log.log 2>&1
```

- cron 环境**没有图形会话**：`DISPLAY` 与 `XAUTHORITY` 必须显式给，否则 xdotool 报 `Can't open display`。
- 玲珑/沙箱应用常需要 `XDG_RUNTIME_DIR`、`DBUS_SESSION_BUS_ADDRESS`，在脚本里自己拼齐再拉起。
- 装完用 `diff <(crontab -l 备份) <(crontab -l)` 核对**没动到别的任务**。

## 调试手法（省时间的关键）

| 手法 | 怎么做 |
|---|---|
| 先认字，再写坐标 | `ocr_map(win.shot())` 一口气打印所有词 + 坐标，直接读偏移 |
| 分步截图 | 每步 `win.shot()` 存盘（`dump()`），人眼/助手看图定位，比猜快十倍 |
| 判据校准 | 先量"勾选态 vs 未勾选态"的暗像素占比（实测 0.065 vs ~0.01），再定阈值 0.02 |
| 定位不到就降级 | 像素/OCR 定位失败要有**回退坐标**，别直接报错退出 |
| 日志带时间戳 | 每步打一行（含耗时），事后能从日志还原整条链 |
| 干跑开关 | `--check-only` 只打印"我会怎么做/会不会被过滤"，不碰目标软件 |

## 反模式（会浪费时间）

- 把几十条 `xdotool` 串成一个 shell 脚本一次跑完 → 中途任何一步错位都会"静默成功"，无法定位；
- 用 `sleep 30` 等界面就绪 → 改成**轮询判据**（`wait_for`）；
- 依赖 `wmctrl`/`import`（ImageMagick）→ 目标机器不一定装；`xdotool + scrot + xprop` 是够用的最小集；
- 在 Wayland 上硬试 xdotool；
- 忘了 `pgrep -x`（`pgrep -f name` 会误匹配 `.sh` 包装脚本，实测踩过）。

## 资产

- `scripts/guiauto.py` — 可复用骨架：`sh()` 带超时、`workarea()`、`Win`（geom/activate/maximize/click/key/shot/titlebar）、
  `ocr()`/`ocr_words()`/`ocr_map()`、`dark_ratio()`/`red_block()`、`wait_for()`、`watch_text()` 生成器、`recon()`。
- `scripts/selftest.py` — 离线自测（合成中文图 + 红色块 + 复选框，验证 OCR/像素判据与 TESSDATA 路径），
  不依赖任何 GUI 程序；`python3 scripts/selftest.py` 应全绿。
- 真实样本：`/home/admin/tdx_auto_download.py` + 技能 `tdx-wine-auto-download`（同一套手法的完整工程化版本）。
