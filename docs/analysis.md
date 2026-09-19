# 环境分析与方案设计

本文记录项目立项时的调查结论，供维护者与贡献者参考。

## 分析环境

- 发行版：EndeavourOS（Arch 系），内核 7.x，Bash 5.3
- 桌面：Hyprland + Caelestia
- 相关包：
  - `caelestia-shell` 2.5.0-1（QML shell，安装于 `/etc/xdg/quickshell/caelestia`，
    C++ 插件安装于 `/usr/lib/qt6/qml/Caelestia/`）
  - `caelestia-cli` 1.1.3-1（Python CLI，安装于 `/usr/lib/python3.14/site-packages/caelestia`）
- 实际生效的 shell 目录：`~/.config/quickshell/caelestia`（用户完整副本，
  Quickshell 的 `qs -c caelestia` 会优先使用 XDG 配置目录中的同名配置）

## 文本来源盘点

| 来源 | 位置 | 是否汉化 | 方式 |
| --- | --- | --- | --- |
| Caelestia QML UI 字符串 | `/etc/xdg/quickshell/caelestia/**/*.qml` 或用户副本 | 是 | 替换 `Tr.*(...)` 的字面量参数 |
| 天气状况文本 | `services/Weather.qml` | 是 | 同上（天气代码到文本的映射在 QML 中） |
| 桌面通知文案 | QML `services/*.qml` 中的 `Tr.mark*` | 是 | 同上（`mark` 文本最终由 `trMarked` 翻译） |
| 设置项名称与描述 | `modules/nexus/**` | 是 | 同上 |
| 应用名 / 窗口标题 / SSID / 设备名 | 运行时数据 | 否 | 动态数据 |
| 媒体元数据、歌词 | MPRIS / LRCLIB / NetEase | 否 | 第三方数据 |
| `nmcli` / `pactl` / `hyprctl` 等输出 | 系统命令 | 否 | 第三方输出 |
| PAM / `fprintd` / `howdy` 错误 | PAM 模块 | 否 | 第三方输出 |
| Python CLI 通知与终端输出 | `caelestia-cli` | 否 | 属于另一套程序，且位于 `/usr/lib` |
| C++ 插件内的报警/调试信息 | `libcaelestia-*.so` | 否 | 正常 UI 不展示 |

## 上游 i18n 机制调查（caelestia-shell 2.5.0）

- 上游提供 `Caelestia.I18n` QML 模块，含 `Tr` 单例与 `Translator` C++ 类型。
- `Tr.tr()/trCtx()/trN()/trCtxN()/mark*()` 从 gettext 风格的 **二进制 `.mo` catalog** 查询。
- catalog 只能通过构建期资源嵌入：`plugin/src/Caelestia/I18n/CMakeLists.txt` 中的
  `po_files` 列表为空，`translator.cpp` 仅从 `:/qt/qml/Caelestia/I18n/<lang>.mo` 读取。
- `supportedLanguages` 由资源目录中实际存在的 `.mo` 决定；当前为空，因此
  「界面语言」选择器没有可选项。
- 结论：**不重新编译插件就无法向上游机制添加翻译**。

## 方案对比

| 方案 | 优点 | 缺点 | 结论 |
| --- | --- | --- | --- |
| A. 重编译 caelestia-shell，注入 `zh_CN.mo` | 使用上游原生机制 | 需要 base-devel + CMake + Qt6，编译慢；每次升级都要重打包；普通用户门槛高 | 不采用（在 docs 中说明为进阶方向） |
| B. 用 `QML_IMPORT_PATH` 影子模块替换 `Caelestia.I18n` | 不修改 shell 文件 | 必须重写 `Tr`/`Units`（含 mark 编码、复数、绑定失效），依赖环境变量注入，随上游改动易碎 | 不采用 |
| C. 受控替换 QML 字符串字面量 | 不改代码结构；卸载可字节级还原；对上游实现变化不敏感；纯用户权限 | 修改文件数量多（105 个）；上游新增字符串需更新翻译表 | **采用** |

方案 C 的关键依据：`Tr.tr("中文")` 在 catalog 为空时**原样返回输入**，
因此把字面量换成中文即可生效，且不依赖任何运行时机制。

## 安全设计

- 仅改写 `Tr.*` 调用的字面量参数；扫描器带注释/字符串掩码，绝不触碰代码。
- 修改前进行版本 + 逐文件 SHA-256 兼容性检查，不匹配默认拒绝执行。
- 事务式写入：临时文件 + `os.replace`，失败自动回滚，并留下诊断信息。
- 备份与状态持久化在 `~/.local/share/caelestia-zh/`，卸载优先从备份恢复。
- `flock` 防止并发执行；`--dry-run` 可预览全部改动。
- 不执行 `sudo`（除非用户主动选择 `--target system`），不访问网络。

## 已知边界

- 上游没有用 `Tr.*` 包裹的字符串无法被本项目处理。
- 若用户副本与系统目录版本脱节，`status` 会报告漂移；需要用户自行同步副本。
- 翻译表与具体上游版本绑定；升级后由 `update` / `make_map.py` 辅助适配。
