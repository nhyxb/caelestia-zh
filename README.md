# Caelestia 中文本地化

面向 **Arch Linux（及 EndeavourOS 等 Arch 系发行版）+ Caelestia** 用户的简体中文汉化项目。

[caelestia-shell](https://github.com/caelestia-dots/shell) 2.5.0 虽然引入了 `Tr.tr()` 翻译运行时，
但它只从编译进插件的资源里加载 `.mo` catalog，普通用户无法直接投放翻译文件。
本项目采用**非侵入式、可回滚**的方案：只把 QML 中传给 `Tr.*` 辅助函数的字符串字面量替换为中文，
不修改任何代码结构；安装前自动备份，卸载后可还原为字节级一致的原始文件。

## 功能

| 组件 | 是否支持 | 说明 |
| --- | --- | --- |
| 顶栏 / 状态图标 / 弹出面板 | 支持 | 音量、电池、蓝牙、网络、键盘布局、托盘菜单 |
| 启动器 | 支持 | 搜索、计算器、配色方案、壁纸列表 |
| 通知与横幅（toast） | 支持 | 通知标题、分组、超时、事件开关 |
| 仪表盘（Dashboard） | 支持 | 媒体、性能、天气、日历标签页 |
| Nexus 设置窗口 | 支持 | 所有设置页（网络、蓝牙、音频、面板、服务、语言区域、关于） |
| 电源 / 会话菜单 | 支持 | 图标按钮的辅助文本与面板标签 |
| 锁屏 | 部分支持 | 提示文本、密码/指纹/面部错误信息、天气；PAM 自身输出除外 |
| 侧边栏 / 通知坞 | 支持 | 空状态、分组计数 |
| 录屏 / 工具卡片 | 支持 | 状态、按钮、录像列表、删除确认 |
| 窗口信息（windowinfo） | 支持 | 详情字段、按钮 |
| 文件选择对话框 | 支持 | 筛选、按钮、空目录提示 |
| 天气描述 | 支持 | 天气状况文本来自 `services/Weather.qml`，可直接汉化 |
| `caelestia` 命令行输出 | 不支持 | Python CLI 的系统通知与终端输出，属于另一套程序 |
| 第三方程序动态输出 | 不支持 | SSID、设备名、媒体元数据、`nmcli`/`pw-dump` 等命令输出 |
| 编译进 C++ 插件的调试信息 | 不支持 | 仅面向开发者，正常 UI 不显示 |

## 截图

> 待补充。欢迎通过 PR 提交汉化后的界面截图。
>
> 建议放在 `docs/screenshots/` 下，并在此处引用。

## 环境要求

- **Arch Linux** 或 Arch 系发行版（项目使用 `pacman` 检测版本，但不是硬依赖）
- **caelestia-shell 2.5.0**（翻译表针对该版本生成）
- **Bash 5+**
- **Python 3.8+**（`caelestia-cli` 已依赖 Python，通常无需额外安装）
- `flock`（`util-linux`，Arch 基础系统自带）
- 可选：`shellcheck` 用于开发检查

不需要 root 权限（除非你选择汉化 `/etc/xdg/quickshell/caelestia` 系统目录）。

## 安装

```bash
git clone https://github.com/nhyxb/caelestia-zh.git
cd caelestia-zh
./caelestia-zh.sh install
```

安装脚本会自动探测正在使用的 shell 配置目录：

1. `~/.config/quickshell/caelestia`（存在时优先，因为它会覆盖系统目录）
2. `/etc/xdg/quickshell/caelestia`

也可以手动指定：

```bash
./caelestia-zh.sh install --shell-dir /path/to/caelestia
./caelestia-zh.sh install --target system          # 需要 sudo
sudo ./caelestia-zh.sh install --target system
```

先用 dry-run 预览改动：

```bash
./caelestia-zh.sh install --dry-run --verbose
```

完成后重新加载 shell：

```bash
caelestia shell -r
```

## 卸载

```bash
./caelestia-zh.sh uninstall
```

卸载默认从安装时建立的字节级备份恢复，因此可以精确还原。
如果安装后你手动编辑过某个文件，脚本会保留你的修改并给出提示；确认要放弃这些修改时：

```bash
./caelestia-zh.sh uninstall --force
```

如果状态目录丢失（例如手动删除了 `~/.local/share/caelestia-zh`），可以按翻译表反向恢复：

```bash
./caelestia-zh.sh uninstall --revert-from-map
```

## 更新

Caelestia 升级后：

```bash
cd caelestia-zh
git pull
./caelestia-zh.sh update
```

`update` 会以「尽力而为」模式重新应用汉化：

- 仍然存在的字符串继续翻译；
- 上游新增或改写的字符串保持英文，并在结束时报告数量；
- 不会因为版本变化就盲目替换。

如果翻译表还没有适配你的 Caelestia 版本，`status` 会列出与支持版本不一致的文件。

## 命令参考

```text
./caelestia-zh.sh install     应用汉化（自动备份）
./caelestia-zh.sh uninstall   恢复原始文件
./caelestia-zh.sh status      查看汉化状态
./caelestia-zh.sh update      Caelestia 更新后重新应用
./caelestia-zh.sh verify      校验已汉化文件是否与记录一致

选项:
  --dry-run            只演示，不修改文件
  --shell-dir DIR      手动指定 shell 配置目录
  --target user|system 选择用户副本或系统目录（默认自动）
  --map FILE           使用其它翻译表
  --data-dir DIR       指定状态与备份目录
  --force              卸载时强制恢复备份
  --force-version      版本不匹配时继续
  --strict             版本/哈希不匹配或有未翻译字符串时中止
  --revert-from-map    没有备份时按翻译表反向恢复
  --quiet / --verbose
```

退出码：`0` 成功，`1` 失败，`3` 成功但有警告（例如存在未翻译字符串）。

## 工作原理

1. **分析**：`tools/apply.py` 用字符串感知的扫描器解析 QML，只识别
   `Tr.tr` / `Tr.trCtx` / `Tr.trN` / `Tr.trCtxN` / `Tr.mark*` 调用中的字面量参数；
   注释、图标名、动态参数、拼接表达式一概不碰。
2. **兼容性检查**：把目标目录每个文件与翻译表中记录的原始 SHA-256 比对；
   版本不匹配且哈希也无法确认时，默认停止（可用 `--force-version` 覆盖）。
3. **备份**：`tools/state.py` 把将要修改的文件复制到
   `~/.local/share/caelestia-zh/backup/<时间戳>/`，并记录原始/安装后哈希。
4. **应用**：按 `文件 → 原文 → 译文` 映射替换字面量；已翻译的自动跳过（幂等）；
   写入采用「临时文件 + 原子替换」，任何一步失败都会回滚本次全部改动。
5. **记录**：状态写入 `state.json`，卸载时据此精确恢复。

## 目录结构

```text
caelestia-zh/
├── caelestia-zh.sh          # 主脚本（Bash）
├── tools/
│   ├── apply.py             # 扫描 / 替换 / 分析引擎
│   ├── state.py             # 备份、状态、恢复
│   └── make_map.py          # 由 Caelestia 源码树生成/刷新翻译表
├── translations/
│   └── zh_CN.json           # 简体中文翻译表（含文件哈希与调用序列）
├── tests/
│   ├── run-tests.sh         # 自包含测试套件
│   └── fixtures/            # 测试用迷你 shell 树与词典
├── docs/
│   ├── analysis.md          # 文本来源与方案分析
│   └── translation-guide.md # 翻译表维护指南
├── .github/workflows/ci.yml
├── CHANGELOG.md
├── VERSION
├── LICENSE
└── README.md
```

## 已知问题

- **上游未用 `Tr.*` 包裹的文本无法汉化**。Caelestia 2.5.0 已把绝大多数 UI 文本接入 `Tr.*`，
  但仍可能有漏网字符串；发现后欢迎提交 issue 或 PR。
- **界面语言选择器没有中文选项**。上游的 `Tr.language` 只认识编译进插件的 catalog；
  本项目直接替换字符串，因此「设置 → 语言与区域 → 界面语言」仍显示「自动」。这不影响汉化效果。
- **C++ / PAM / 系统命令输出保持英文**，例如指纹识别失败原因、`nmcli` 报错等。
- **用户副本会与系统目录脱节**。若你使用 `~/.config/quickshell/caelestia` 这份完整副本，
  升级 `caelestia-shell` 后副本不会自动跟进；`status` 会显示文件漂移。
  可以定期用新版文件同步副本后再 `update`。
- 上游若重写了某条字符串，该条翻译会暂时失效并保持英文，直到翻译表更新。

## 翻译规范

- 目标语言为**准确、自然、统一的简体中文**，拒绝逐词硬译。
- 保留专有名词：`Caelestia`、`Quickshell`、`Qt`、`Hyprland`、`Wi-Fi`、`VPN`、
  `WireGuard`、`DHCP`、`DNS`、`CIDR`、`SSID`、`XKB`、`CPU`、`GPU`、程序名与路径。
- 保留占位符：`%1`、`%2`、`%n`、`%L1` 必须原样保留，位置可按中文语序调整。
- 标点跟随中文习惯：标签用全角冒号「：」，列表分隔用「、」。
- 不翻译动态数据与第三方输出。
- 同一英文词在不同上下文含义不同时，使用 `contexts` 或 `overrides` 单独指定，
  不用一个译文硬套所有场景。

## 贡献

欢迎提交 issue 与 PR：

1. Fork 仓库并新建分支。
2. 修改 `translations/zh_CN.json` 中的 `global` / `contexts` / `overrides`。
3. 如果是适配新版本，先运行：

   ```bash
   python3 tools/make_map.py --update translations/zh_CN.json \
       --root /etc/xdg/quickshell/caelestia --version <新版本>
   ```

   该命令会重建文件哈希与调用序列，并列出所有还没有翻译的字符串。
4. 运行检查：

   ```bash
   shellcheck -x caelestia-zh.sh tests/run-tests.sh
   ./tests/run-tests.sh
   ```
5. 提交 PR，说明改动范围与测试结果。

新增语言（例如 `zh_TW`）：复制 `translations/zh_CN.json`，
保留 `global` / `contexts` / `overrides` 结构（可先置空），
用 `make_map.py` 重新生成派生字段即可。

## License

本项目以 [GPL-3.0-only](LICENSE) 发布，与上游 caelestia-shell 的许可证保持一致。

翻译内容基于上游界面文本，上游版权归 Caelestia 项目所有。

## 致谢

- [Caelestia](https://github.com/caelestia-dots) 项目与所有贡献者
- 所有提交翻译、测试与反馈的使用者
