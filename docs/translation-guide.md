# 翻译表维护指南

翻译表位于 `translations/zh_CN.json`，由两部分组成：

1. **人工维护的翻译**
   - `global`：全局映射，英文原文 → 中文译文（覆盖绝大多数场景）。
   - `contexts`：按上游 `trCtx` 上下文区分，例如 `"toggle label": {"Enabled": "启用"}`。
   - `overrides`：按文件覆盖，例如某文件里 `Open` 指「打开」而不是「开放」。
2. **自动生成的元数据**（请勿手改）
   - `file_hashes`：每个文件原始内容的 SHA-256，用于兼容性检查。
   - `file_keys` / `file_sequence` / `plural_keys`：用于幂等替换与无备份回退恢复。

解析优先级：`contexts` → `overrides` → `global`。

## 修改一条翻译

直接编辑 `global` 中对应的值即可，例如：

```json
"Bluetooth": "蓝牙"
```

重新运行 `./caelestia-zh.sh install` 使改动生效；已汉化的文件会自动重新应用。

## 处理一词多义

如果同一个英文词在不同页面需要不同译文，优先使用 `contexts`
（上游源码中 `Tr.trCtx("Enabled", "toggle label")` 的第二个参数就是上下文）：

```json
"contexts": {
  "toggle label": { "Enabled": "启用" },
  "panel status": { "Enabled": "已启用" }
}
```

如果该调用没有上下文，则使用 `overrides` 按文件区分：

```json
"overrides": {
  "modules/example/Foo.qml": { "Open": "打开" }
}
```

## 适配新的 Caelestia 版本

```bash
# 1. 确认新版本已安装
pacman -Q caelestia-shell

# 2. 重建哈希与调用序列，并列出未翻译字符串
python3 tools/make_map.py --update translations/zh_CN.json \
    --root /etc/xdg/quickshell/caelestia --version 2.6.0

# 3. 在 global/contexts/overrides 中补全翻译后再次运行（此时应显示 0 条未翻译）
python3 tools/make_map.py --update translations/zh_CN.json \
    --root /etc/xdg/quickshell/caelestia --version 2.6.0
```

`make_map.py` 会保留人工翻译，只重算派生字段；
`--allow-uncovered` 可在翻译暂时不全时先写入（`--update` 模式默认允许）。

## 新增语言

```bash
cp translations/zh_CN.json translations/zh_TW.json
# 清空或替换 global/contexts/overrides 的译文，保留键名
python3 tools/make_map.py --update translations/zh_TW.json \
    --root /etc/xdg/quickshell/caelestia --version 2.5.0 --language zh_TW
```

随后用 `--map translations/zh_TW.json` 运行主脚本。

## 本地验证

```bash
# 预览所有改动（不写盘）
./caelestia-zh.sh install --dry-run --verbose

# 查看待翻译字符串统计
python3 tools/apply.py analyze --root /etc/xdg/quickshell/caelestia \
    --map translations/zh_CN.json --verbose

# 跑测试（使用 fixture，不碰真实配置）
./tests/run-tests.sh

# ShellCheck
shellcheck -x caelestia-zh.sh tests/run-tests.sh
```

## 覆盖检查

`make_map.py` 会报告：

- `untranslated`：扫描到但翻译表中没有的字符串；
- `unused entries`：翻译表中存在但当前版本已不再使用的键（会保留，便于回退版本）；
- `overrides for files without Tr calls`：文件已不存在或已无 `Tr` 调用的覆盖项。

建议在 PR 前确保 `untranslated` 为 0；无法翻译的动态字符串不会被扫描器计入。
