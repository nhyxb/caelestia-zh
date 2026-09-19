# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.0] - 2026-09-19

### 新增

- 首个版本，支持 caelestia-shell 2.5.0（AUR 包版本 2.5.0-1）。
- `install`：受控字面量替换，只改写 `Tr.tr()` 等上游翻译辅助函数的字符串参数。
- `uninstall`：优先从字节级备份恢复；支持 `--force`、`--revert-from-map`。
- `status`：展示目标目录、版本、安装状态与文件漂移。
- `update`：Caelestia 更新后重新应用汉化。
- `verify`：校验已汉化文件是否与安装记录一致。
- 完整备份与状态记录（`~/.local/share/caelestia-zh/`），支持事务式回滚。
- 版本 / 文件哈希兼容性检测，不匹配时默认拒绝修改。
- 独立翻译表 `translations/zh_CN.json`（691 条全局翻译 + 上下文与按文件覆盖）。
- 测试套件 `tests/run-tests.sh`：111 项断言，覆盖装卸载、dry-run、失败回滚、并发锁等场景。

### 说明

- 汉化基于字符串字面量替换，不修改任何代码结构；卸载后可还原为字节级一致。
- 第三方程序（NetworkManager、PipeWire、BlueZ、Hyprland 等）的动态输出不在汉化范围内。
