# tinyskill

个人**轻量技能集**：一个仓库放多个小技能，每个技能一个目录、**各自一份说明**（`README.md` 给人看，`SKILL.md` 给 AI agent 看）。

定位：解决具体问题的**小而能跑**的工具/流程，不追求大而全。后续有新技能直接加目录。

## 技能列表

| 目录 | 技能 | 说明 | 依赖 | 状态 |
|---|---|---|---|---|
| [`linux-gui-automation/`](linux-gui-automation/) | Linux X11 GUI 自动化 | 用 `xdotool` 真鼠标键盘 + 像素判据 + OCR 驱动**没有 API 的 GUI 软件**（Wine/玲珑版国产客户端、老式 Qt/Java 内部系统），可挂 cron 无人值守 | xdotool, scrot, xprop, tesseract(+chi_sim), pytesseract, Pillow, numpy | ✅ 自测全绿（离线 + 真实 X11） |

## 安装到 Hermes

```bash
git clone https://github.com/tkrd126/tinyskill.git
# 每个技能目录直接就是一个 Hermes 技能
cp -r tinyskill/linux-gui-automation ~/.hermes/skills/devops/
```

（也可以把本仓作为 tap 指向 `~/.hermes/skills`，见 `skills-repository-management` 技能。）

## 目录约定

```
tinyskill/
└── <skill-name>/
    ├── README.md       # 人读：解决什么问题、装什么依赖、怎么用、API 速览、已踩的坑
    ├── SKILL.md        # agent 读：带 YAML frontmatter（name/description/version/tags）+ 硬规则
    └── scripts/        # 可复用脚本（必须能独立跑，带自测最好）
```

新增技能的检查清单：

1. 目录名小写连字符；`SKILL.md` 的 `description` **首 57 字符是自包含触发条件**（`Use when ...`）；
2. `scripts/` 里的东西**必须真跑通过**，优先带一个不依赖外部环境的 `selftest.py`；
3. `README.md` 写清**装什么、怎么跑、坑在哪**，附真实输出而不是"应该可以"；
4. 根 `README.md` 的技能表格加一行；
5. commit message 说明**根因/来由**。

## License

MIT（见 [LICENSE](LICENSE)）
